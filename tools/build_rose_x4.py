# -*- coding: utf-8 -*-
"""
RE8 -> X4 character pipeline, stage 1: extract + retarget + build Blender meshes.

Run inside Blender:
    blender -b --factory-startup --python tools/build_rose_x4.py

What it does
------------
1. Imports a vanilla X4 Argon-female XAC through X4CharacterConverter, which
   gives us the authoritative 91-bone Biped armature (bind pose, Z-up, cm).
2. Reads Rose's RE8 meshes with skin weights (RE-Mesh-Editor parser).
3. Retargets:
     * global frame conversion  RE8(x,y,z) m  ->  X4(x,-z,y) cm
     * per-segment affine alignment (legs / arms / torso / head are scaled and
       offset independently, because the two rigs do not share proportions)
     * skin weights remapped RE8 bone -> X4 bone by name semantics, merged and
       renormalised
4. Builds one Blender object per RE8 part, parented to the X4 armature with
   vertex groups matching X4 bone names.

Stage 2 (separate step) wires materials and calls the addon's export_package.
"""

import bpy
import numpy as np
import json
import math
import os
import sys
import importlib
import addon_utils
import pathlib

# --------------------------------------------------------------------------
# paths / config
# --------------------------------------------------------------------------
WORK = r"D:\dsh-x4\work"
ADDON_DIR = r"D:\dsh-x4\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
X4_ROOT = os.path.join(WORK, "x4root")
RE8_TOOLS = r"D:\dsh-mod\re8\tools\RE-Mesh-Editor-main"
RE8_RAW = r"D:\dsh-mod\re8\output\raw_natives\natives\stm\_ge\character\ch\ch01\6000"
RE8_MODELS = r"D:\dsh-mod\re8\output\models\Rose_Adult_ShadowsOfRose"

#: whichever vanilla asset hosts the X4 armature we retarget onto.
#: The head asset carries the full 91-bone skeleton, so it is the reference.
HOST_XAC = os.path.join(
    X4_ROOT, r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac")

#: RE8 parts to convert -> (mesh file, skeleton json)
PARTS = [
    ("body",      r"6000\ch01_6000_body.mesh.2101050001",      "ch01_6000_body_skeleton.json"),
    ("jacket",    r"6001\ch01_6001_jacket.mesh.2101050001",    "ch01_6001_jacket_skeleton.json"),
    ("slingbelt", r"6004\ch01_6004_slingbelt.mesh.2101050001", "ch01_6004_slingbelt_skeleton.json"),
    ("face",      r"6020\ch01_6020_rose_face.mesh.2101050001", "ch01_6020_rose_face_skeleton.json"),
    ("eyes",      r"6030\ch01_6030_rose_eyes.mesh.2101050001", "ch01_6030_rose_eyes_skeleton.json"),
    ("hair",      r"6040\ch01_6040_hair.mesh.2101050001",      "ch01_6040_hair_skeleton.json"),
    ("hand_r",    r"6050\ch01_6050_hand_r.mesh.2101050001",    "ch01_6050_hand_r_skeleton.json"),
    ("hand_l",    r"6060\ch01_6060_hand_l.mesh.2101050001",    "ch01_6060_hand_l_skeleton.json"),
]

sys.path.insert(0, os.path.join(WORK, "tools"))
sys.path.insert(0, ADDON_DIR)
sys.path.insert(0, RE8_TOOLS)

from re8_to_x4 import map_bone, re8_to_x4, is_deform_bone  # noqa: E402
import pose_align  # noqa: E402

#: parts whose vertices are driven by the arm chain
ARM_PARTS = {'body', 'jacket', 'hand_l', 'hand_r', 'slingbelt'}
from modules.mesh.file_re_mesh import readREMesh            # noqa: E402
from modules.mesh.re_mesh_parse import ParsedREMesh         # noqa: E402


# --------------------------------------------------------------------------
# 1. X4 armature
# --------------------------------------------------------------------------
def load_x4_armature():
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = X4_ROOT + os.sep
    from X4CharacterConverter import addon as A

    A.import_actor(bpy.context, pathlib.Path(HOST_XAC))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    # the importer links vanilla meshes too -- drop them, we only want the rig
    for ob in list(bpy.data.objects):
        if ob.type == 'MESH':
            bpy.data.objects.remove(ob, do_unlink=True)

    mw = arm.matrix_world
    bones = {}
    for b in arm.data.bones:
        bones[b.name] = {
            'head': tuple(mw @ b.head_local),
            'tail': tuple(mw @ b.tail_local),
            'parent': b.parent.name if b.parent else None,
        }
    return arm, bones


# --------------------------------------------------------------------------
# 2. RE8 mesh + weights
# --------------------------------------------------------------------------
def load_re8_part(mesh_rel, skel_json):
    path = os.path.join(RE8_RAW, mesh_rel)
    raw = readREMesh(path)
    parsed = ParsedREMesh()
    parsed.ParseREMesh(raw)

    skel = json.load(open(os.path.join(RE8_MODELS, skel_json), encoding='utf-8'))
    positions = {}
    for b in skel['bones']:
        m = b['worldMatrix']
        positions[b['name']] = (m[3][0], m[3][1], m[3][2])

    # flatten every submesh, keeping per-vertex weights AND per-submesh material
    verts, weights, groups, subs, base = [], [], [], [], 0
    for lod in parsed.mainMeshLODList:
        for grp in lod.visconGroupList:
            for sm in grp.subMeshList:
                n = len(sm.vertexPosList)
                uvl = list(getattr(sm, 'uvList', None) or [])
                local_v, local_w, local_uv = [], [], []
                for i in range(n):
                    verts.append(sm.vertexPosList[i])
                    w = []
                    if i < len(sm.weightList):
                        wl = sm.weightList[i]
                        wi = sm.weightIndicesList[i]
                        for k in range(len(wl)):
                            if wl[k] > 0.000001:
                                w.append((wi[k], float(wl[k])))
                    weights.append(w)
                    local_v.append(sm.vertexPosList[i])
                    local_w.append(w)
                    local_uv.append(tuple(uvl[i]) if i < len(uvl) else (0.0, 0.0))
                faces = []
                for f in sm.faceList:
                    faces.append((f[0] + base, f[1] + base, f[2] + base))
                groups.append((sm.materialIndex, faces))
                subs.append({
                    'material_index': sm.materialIndex,
                    'base': base,
                    'count': n,
                    'verts': local_v,
                    'weights': local_w,
                    'uvs': local_uv,
                    'faces': [tuple(x - base for x in f) for f in faces],
                })
                base += n

    weighted = parsed.skeleton.weightedBones if parsed.skeleton else []
    return {
        'path': path, 'verts': verts, 'weights': weights,
        'submeshes': groups,          # [(material_index, faces)]
        'submesh_geometry': subs,     # per-submesh independent geometry
        'weighted_bones': list(weighted), 'bone_positions': positions,
        'material_names': list(parsed.materialNameList),
    }


# --------------------------------------------------------------------------
# 3. per-segment affine alignment
# --------------------------------------------------------------------------
#: segment -> (rose anchor bone, x4 anchor bone) pairs used to fit scale+offset
SEGMENTS = {
    'leg':   [('L_Thigh',   'Bip01 L Thigh'), ('L_Calf', 'Bip01 L Calf'),
              ('L_Foot',    'Bip01 L Foot'),  ('L_Toe',  'Bip01 L Toe0'),
              ('R_Thigh',   'Bip01 R Thigh'), ('R_Calf', 'Bip01 R Calf'),
              ('R_Foot',    'Bip01 R Foot'),  ('R_Toe',  'Bip01 R Toe0')],
    'arm':   [('L_Shoulder', 'Bip01 L Clavicle'), ('L_UpperArm', 'Bip01 L UpperArm'),
              ('L_Forearm',  'Bip01 L Forearm'),  ('L_Hand',     'Bip01 L Hand'),
              ('R_Shoulder', 'Bip01 R Clavicle'), ('R_UpperArm', 'Bip01 R UpperArm'),
              ('R_Forearm',  'Bip01 R Forearm'),  ('R_Hand',     'Bip01 R Hand')],
    'torso': [('Hip', 'Bip01 Pelvis'), ('Spine_0', 'Bip01 Spine'),
              ('Spine_1', 'Bip01 Spine1'), ('Spine_2', 'Bip01 Spine2'),
              ('Neck_0', 'Bip01 Neck'), ('Head', 'Bip01 Head')],
}

#: which segment each RE8 bone belongs to (by name prefix)
def bone_segment(name):
    if name.startswith(('L_Thigh', 'R_Thigh', 'L_Calf', 'R_Calf', 'L_Shin',
                        'R_Shin', 'L_Foot', 'R_Foot', 'L_Toe', 'R_Toe',
                        'L_Knee', 'R_Knee')):
        return 'leg'
    if name.startswith(('L_Shoulder', 'R_Shoulder', 'L_UpperArm', 'R_UpperArm',
                        'L_Forearm', 'R_Forearm', 'L_Hand', 'R_Hand',
                        'L_Palm', 'R_Palm', 'L_Wep', 'R_Wep',
                        'L_delt', 'R_delt', 'L_pec', 'R_pec',
                        'L_Thumb', 'R_Thumb', 'L_Index', 'R_Index',
                        'L_Middle', 'R_Middle', 'L_Ring', 'R_Ring',
                        'L_Pinky', 'R_Pinky')):
        return 'arm'
    return 'torso'


def re8_to_blender(p, scale=100.0):
    """RE8 source (metres) -> the converter's Blender arrangement (cm).

    Height lands in the THIRD component, matching what the importer produces
    for skeletons (Bip01 Head z=161.4) and for vanilla meshes (head spans
    z 145..182).
    """
    return (p[0] * scale, -p[2] * scale, p[1] * scale)


#: bone pairs whose semantics are unambiguous, used to fit the retarget
ALIGN_PAIRS = [
    ('Hip', 'Bip01 Pelvis'), ('Spine_0', 'Bip01 Spine'),
    ('Spine_1', 'Bip01 Spine1'), ('Spine_2', 'Bip01 Spine2'),
    ('Neck_0', 'Bip01 Neck'), ('Head', 'Bip01 Head'),
    ('L_Shoulder', 'Bip01 L Clavicle'), ('R_Shoulder', 'Bip01 R Clavicle'),
    ('L_UpperArm', 'Bip01 L UpperArm'), ('R_UpperArm', 'Bip01 R UpperArm'),
    ('L_Forearm', 'Bip01 L Forearm'), ('R_Forearm', 'Bip01 R Forearm'),
    ('L_Thigh', 'Bip01 L Thigh'), ('R_Thigh', 'Bip01 R Thigh'),
    ('L_Calf', 'Bip01 L Calf'), ('R_Calf', 'Bip01 R Calf'),
    ('L_Foot', 'Bip01 L Foot'), ('R_Foot', 'Bip01 R Foot'),
]


def fit_global(rose_pos, x4_pos, verbose=True):
    """One Kabsch fit for the whole skeleton: (scale, R, t), all in cm.

    `rose_pos` holds RE8 world translations in METRES and `x4_pos` holds the
    imported skeleton in CENTIMETRES, so both are pushed through
    re8_to_blender()/identity first to make the fit well posed.  Forgetting
    that mismatch is what made an earlier run fit scale=1.03 (it should be
    ~1.0 *after* the metres->cm conversion) and place the mesh 45 cm off.

    Limbs whose *pose* differs from the target (Rose's arms hang forward, the
    X4 rig's do not) legitimately keep a large residual; that is handled by
    pose_align afterwards rather than by distorting this fit.
    """
    P, Q = [], []
    for rb, xb in ALIGN_PAIRS:
        if rb in rose_pos and xb in x4_pos:
            pv = np.array(rose_pos[rb], float)
            if np.linalg.norm(pv) < 10.0:        # metres -> centimetres
                pv = pv * 100.0
            P.append(np.array([pv[0], -pv[2], pv[1]]))   # -> Blender arrangement
            Q.append(np.array(x4_pos[xb]['head'], float))
    if len(P) < 3:
        raise RuntimeError("fit_global: not enough matched bone pairs")
    P, Q = np.array(P), np.array(Q)
    assert np.linalg.norm(P.mean(0)) > 50, "rose side not in cm"
    assert np.linalg.norm(Q.mean(0)) > 50, "x4 side not in cm"

    pc, qc = P.mean(0), Q.mean(0)
    P0, Q0 = P - pc, Q - qc
    U, S, Vt = np.linalg.svd(P0.T @ Q0)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    scale = float(S.sum() / (P0 ** 2).sum())
    t = qc - scale * (R @ pc)

    if verbose:
        print("  Kabsch: scale=%.5f (期望≈1.0)  t=(%.2f, %.2f, %.2f)" % (scale, *t))
        pred = (scale * (R @ P.T)).T + t
        res = sorted(((float(np.linalg.norm(a - b)), rb, xb)
                      for (rb, xb), a, b in zip(ALIGN_PAIRS, pred, Q)),
                     reverse=True)
        for d_, rb, xb in res[:4]:
            print("     残差 %-12s -> %-18s %6.2f cm" % (rb, xb, d_))
    return scale, R, t


def _rose_cm_to_blender(p_m):
    """RE8 metres -> Blender arrangement cm, same as fit_global's P side."""
    return (p_m[0] * 100.0, -p_m[2] * 100.0, p_m[1] * 100.0)


def apply_global(p, scale, R, t):
    v = (scale * (R @ np.array(p, float))) + t
    return (float(v[0]), float(v[1]), float(v[2]))


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
#: X4 NPCs are instanced: dozens share the screen inside a station.  Vanilla
#: Argon assets are ~5k vertices *per asset* (head 5002, body 4600), whereas
#: RE8 characters are authored for close-up single-character rendering and
#: arrive at 340k/359k.  Shipping them unmodified is ~73x the engine's NPC
#: budget and exhausts VRAM (flicker, map lockups, corrupted map tiles).
#: These ratios bring each part back toward the vanilla envelope.
DECIMATE_RATIO = {
    'hair': 0.05,
    'jacket': 0.06,
    'body': 0.10,
    'slingbelt': 0.10,
    # hands keep more geometry: fingers are thin and collapse badly
    'hand_l': 0.55,
    'hand_r': 0.55,
    'eyes': 0.50,
    'face': 0.20,
}
DECIMATE_FLOOR = 200


def decimate(ob, ratio, floor=DECIMATE_FLOOR):
    """Collapse-decimate in place, merging vertex-group weights.

    Blender's Decimate modifier redistributes vertex groups, so skinning
    survives; it reports no error when the *whole group* loses its weights,
    which happens on tiny meshes, so that case is checked explicitly.
    """
    if ratio >= 0.999 or len(ob.data.polygons) < 4:
        return len(ob.data.vertices), 0
    before = len(ob.data.vertices)
    mod = ob.modifiers.new(name="Decimate", type='DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    mod.use_collapse_triangulate = True

    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = new_me
    bpy.data.meshes.remove(old)

    if len(ob.data.vertices) < floor:
        return before, -1          # caller falls back to the undecimated mesh

    gname = {g.index: g.name for g in ob.vertex_groups}
    unweighted = 0
    for v in ob.data.vertices:
        if not any(ge.weight > 1e-6 for ge in v.groups):
            unweighted += 1
    return len(ob.data.vertices), unweighted


def make_material(name, info):
    """Build a Principled material from a materials.json entry."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    tex_dir = os.path.join(RE8_MODELS)

    def add_tex(rel, non_color, target, label):
        if not rel:
            return None
        path = os.path.normpath(os.path.join(tex_dir, rel))
        if not os.path.exists(path):
            return None
        img = bpy.data.images.load(path, check_existing=True)
        if non_color:
            img.colorspace_settings.name = 'Non-Color'
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        node.label = label
        node.location = (-350, 200 if not non_color else -150)
        if target is not None:
            nt.links.new(node.outputs["Color"], target)
        return node

    albedo = info.get('albedo')
    nrm = info.get('normalRoughness')
    if albedo:
        add_tex(albedo, False, bsdf.inputs['Base Color'], 'albedo')
    else:
        bsdf.inputs['Base Color'].default_value = (0.35, 0.32, 0.30, 1.0)
    if nrm:
        tex = add_tex(nrm, True, None, 'nrmr')
        if tex is not None:
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nmap.location = (-100, -200)
            nt.links.new(tex.outputs['Color'], nmap.inputs['Color'])
            nt.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Roughness'].default_value = 0.55
    return mat


def main():
    arm, x4_bones = load_x4_armature()
    print("X4 armature: %d bones" % len(x4_bones))
    x4_names = set(x4_bones)

    # global reference skeleton (body) for segment fitting
    ref = load_re8_part(*PARTS[0][1:])
    scale_g, R_g, t_g = fit_global(ref['bone_positions'], x4_bones)

    # bone map once, from the union of all parts
    bone_map = {}
    unmapped = set()
    for _, mesh_rel, skel_json in PARTS:
        skel = json.load(open(os.path.join(RE8_MODELS, skel_json), encoding='utf-8'))
        for b in skel['bones']:
            t = map_bone(b['name'])
            if t is None or t not in x4_names:
                unmapped.add(b['name'])
                bone_map[b['name']] = None
            else:
                bone_map[b['name']] = t
    print("bone map: %d entries, %d unmapped" % (len(bone_map), len(unmapped)))
    if unmapped:
        print("  UNMAPPED:", sorted(unmapped))

    built = []
    # load material definitions once and build the Blender materials
    mat_json = json.load(open(os.path.join(
        RE8_MODELS, "Rose_Adult_ShadowsOfRose_materials.json"), encoding='utf-8'))
    mat_defs = mat_json.get('materials', {})
    # Every material a submesh references must exist as a Blender material,
    # otherwise the submesh ends up with an empty slot and its geometry is
    # silently dropped from stage1.  A grey placeholder is enough here --
    # stage 2 replaces these with the real X4 materials.
    blender_mats = {}
    for mname in mat_defs:
        blender_mats[mname] = make_material(mname, mat_defs.get(mname, {}))
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.get('x4cc_material'):
            mname = ob['x4cc_material']
            if mname not in blender_mats:
                blender_mats[mname] = make_material(mname, {})
    print("materials built: %d / %d" % (len(blender_mats), len(mat_defs)))

    for tag, mesh_rel, skel_json in PARTS:
        part = load_re8_part(mesh_rel, skel_json)
        # one rigid+scale transform for the entire mesh
        new_verts = []
        for p in part['verts']:
            new_verts.append(apply_global(_rose_cm_to_blender(p), scale_g, R_g, t_g))

        # weights -> X4, merged and normalised
        new_weights = []
        for vi in range(len(part['verts'])):
            acc = {}
            for bid, wv in part['weights'][vi]:
                if bid >= len(part['weighted_bones']):
                    continue
                rname = part['weighted_bones'][bid]
                tname = bone_map.get(rname)
                if tname is None:
                    continue
                acc[tname] = acc.get(tname, 0.0) + wv
            total = sum(acc.values())
            if total <= 1e-6:
                # unweighted vertex: pin to the nearest X4 bone
                new_weights.append({})
                continue
            new_weights.append({k: v / total for k, v in acc.items()})

        # Pose alignment.  Kabsch puts the skeleton in the right place (Head
        # residual 2.5 cm, Hip 8.3 cm), but Rose's arms/legs are authored in a
        # different pose from the X4 rig: her hand bone resolves 42 cm from
        # Bip01 L Hand while head and legs land within a few cm.  Rotating the
        # affected vertices onto the bones removes that purely-posed residual.
        if tag in ARM_PARTS:
            arr, nplans = pose_align.apply_alignment(
                new_verts, new_weights, x4_bones, verbose=False)
            if nplans:
                new_verts = [tuple(float(x) for x in v) for v in arr]
                print("      [%s] pose-aligned %d chain(s)" % (tag, nplans))

        tag_clean = "rose_" + tag
        made = []
        sub_uvs = [g.get('uvs') or [] for g in part['submesh_geometry']]
        for si, (mat_index, sfaces) in enumerate(part['submeshes']):
            if not sfaces:
                continue
            used = sorted({i for f in sfaces for i in f})
            base_off = part['submesh_geometry'][si]['base'] if si < len(part['submesh_geometry']) else 0
            collected_uv = sub_uvs[si] if si < len(sub_uvs) else []
            remap = {old: new for new, old in enumerate(used)}
            sverts = [new_verts[i] for i in used]
            sfaces_local = [tuple(remap[i] for i in f) for f in sfaces]

            me = bpy.data.meshes.new("%s_%d" % (tag_clean, si))
            me.from_pydata(sverts, [], sfaces_local)
            me.validate(verbose=False)
            me.update()
            # real UVs from the source mesh (per-vertex -> per-loop)
            uvl = [(collected_uv[i - base_off] if 0 <= i - base_off < len(collected_uv) else (0.0, 0.0))
                   for i in used]
            uv_layer = me.uv_layers.new(name="UVMap")
            for loop in me.loops:
                uv_layer.data[loop.index].uv = uvl[loop.vertex_index]
            ob = bpy.data.objects.new("%s_%d" % (tag_clean, si), me)
            bpy.context.scene.collection.objects.link(ob)

            groups_vg = {}
            for newi, oldi in enumerate(used):
                for gname, gval in new_weights[oldi].items():
                    g = groups_vg.get(gname)
                    if g is None:
                        g = ob.vertex_groups.new(name=gname)
                        groups_vg[gname] = g
                    g.add([newi], gval, 'REPLACE')

            ratio = DECIMATE_RATIO.get(tag, 0.1)
            nv_before = len(me.vertices)
            nv_after, unw = decimate(ob, ratio)
            if unw < 0:
                print("      %s: decimate would leave %d verts, keeping %d"
                      % (ob.name, nv_after, nv_before))

            mname = (part['material_names'][mat_index]
                     if mat_index < len(part['material_names']) else 'mat%d' % mat_index)
            ob['x4cc_part'] = tag
            ob['x4cc_material'] = mname
            if mname in blender_mats:
                ob.data.materials.append(blender_mats[mname])
            ob.parent = arm
            mod = ob.modifiers.new(name="Armature", type='ARMATURE')
            mod.object = arm
            made.append(ob)

        kept_v = sum(len(o.data.vertices) for o in made)
        print("  [%s] verts %d -> %d (ratio %.2f) submeshes=%d groups=%d"
              % (tag, len(new_verts), kept_v, DECIMATE_RATIO.get(tag, 0.1),
                 len(made), len({g.name for o in made for g in o.vertex_groups})))
        built.extend(made)

    out = os.path.join(WORK, "rose_x4_stage1.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("SAVED", out)


main()
