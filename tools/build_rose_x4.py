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
3. Retargets (see retarget_core.py):
     * global frame conversion  RE8(x, up, forward) m -> X4(x, forward, up) cm
     * one rigid transform per X4 bone, blended by skin weight, so the mesh
       lands on the X4 bind pose despite the two rigs differing in pose and
       proportions
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
from retarget_core import BindPoseRetarget                    # noqa: E402

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
def load_re8_skeleton_union():
    """Merge every part's skeleton JSON into one source rig.

    The parts do not share a bone set: the body skeleton carries no eye or
    facial bones, while face/eyes reference ones the others lack (hair chains
    likewise).  The bind transfer needs the union -- without it every eye and
    facial vertex finds no transform and silently keeps the raw frame fit.
    Bone world positions agree wherever two parts both list a bone.
    """
    pos, parents = {}, {}
    for _, _, skel_json in PARTS:
        skel = json.load(open(os.path.join(RE8_MODELS, skel_json),
                              encoding='utf-8'))
        for b in skel['bones']:
            m = b['worldMatrix']
            pos.setdefault(b['name'], (m[3][0], m[3][1], m[3][2]))
            parents.setdefault(
                b['name'],
                skel['bones'][b['parent']]['name'] if b['parent'] >= 0 else None)
    return pos, parents


def load_re8_part(mesh_rel, skel_json):
    path = os.path.join(RE8_RAW, mesh_rel)
    raw = readREMesh(path)
    parsed = ParsedREMesh()
    parsed.ParseREMesh(raw)

    skel = json.load(open(os.path.join(RE8_MODELS, skel_json), encoding='utf-8'))
    positions, parents = {}, {}
    for b in skel['bones']:
        m = b['worldMatrix']
        positions[b['name']] = (m[3][0], m[3][1], m[3][2])
        parents[b['name']] = (skel['bones'][b['parent']]['name']
                              if b['parent'] >= 0 else None)

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
        'bone_parents': parents,
        'material_names': list(parsed.materialNameList),
    }


# --------------------------------------------------------------------------
# 3. the retarget itself lives in retarget_core.py
# --------------------------------------------------------------------------
# The geometry is moved onto the X4 bind pose by `BindPoseRetarget`, which
# builds one transform per X4 bone instead of a single global one.  See that
# module's docstring for why a global Kabsch fit cannot work here.


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
#: X4 NPCs are instanced: dozens share the screen inside a station.  Vanilla
#: Argon assets are ~5k vertices *per asset* (head 5002, body 4600), whereas
#: RE8 characters are authored for close-up single-character rendering and
#: arrive at 340k/359k.  Shipping them unmodified is ~73x the engine's NPC
#: budget and exhausts VRAM (flicker, map lockups, corrupted map tiles).
#: These ratios bring each part back toward the vanilla envelope.
#:
#: Tuned against the source preview render: at ratio 0.06 the parka's
#: silhouette dissolved into facets and the sling belt (872 vertices in total)
#: collapsed to an unrecognisable stub, which is what "the jacket changed
#: completely" looked like in game.
#:
#: Boundary-aware collapse was tried here and abandoned: RE8 ships some
#: submeshes as piles of loose quads (the jacket's stitch layer and fittings
#: score faces/vertex ~1.0 with 84-87% of vertices on a border), so marking
#: borders "protected" marks everything, switches decimation off and jumps the
#: vertex count from 4k to 20k.  A hard vertex budget matters more than a
#: clever heuristic, so ratio alone decides.
#: Budget matters: X4 instances NPCs (dozens on screen in a station) and the
#: engine starts flickering / corrupting the map once the asset is far above
#: vanilla's ~5k vertices per asset.  (The exported count counts a vertex per
#: UV *and normal* seam, so smoothing the normals cut the exported total by
#: 70% -- which is why these ratios can be far more generous than the old
#: ones while shipping fewer vertices than the 9x build that was stable.)
DECIMATE_RATIO = {
    'hair': 0.10,
    'jacket': 0.35,
    'body': 0.30,
    'slingbelt': 0.70,
    # hands are not decimated at all.  They are only 2346 vertices each, and
    # collapsing them rewrites the finger UVs: the tangents follow the UVs, so
    # the normal map comes out as rings around the fingers and dark blotches
    # at the knuckles.  Keeping them intact costs ~4k vertices in total.
    'hand_l': 1.0,
    'hand_r': 1.0,
    'eyes': 0.50,
    'face': 0.50,
}
DECIMATE_FLOOR = 200

#: vanilla's own sneaker mesh bottoms out at -0.32 cm
GROUND_Z = -0.5


def foot_vertex_mask(weights):
    """Boolean mask of vertices driven by the foot/toe chains."""
    out = []
    for wd in weights:
        s = 0.0
        for bn, wv in wd.items():
            if bn.endswith(' Foot') or 'Toe' in bn:
                s += wv
        out.append(s > 0.5)
    return np.array(out, bool)


def lift_feet(verts, weights, ground=GROUND_Z):
    """Raise the feet so the soles rest on the floor.

    X4's toe bones sit almost on the ground (Toe0 z = 0.12) while Rose's are
    3 cm higher, so binding the toe geometry to them buries the shoes ~3.5 cm
    into the floor.  The toes lose that much accuracy against their bone, which
    is invisible; a sunken boot is not.
    """
    mask = foot_vertex_mask(weights)
    if not mask.any():
        return verts, 0.0
    # align either way: the feet must meet the floor, whether the transfer
    # left them sunk into it or hanging above it
    dz = ground - float(verts[mask][:, 2].min())
    if abs(dz) < 0.05:
        return verts, 0.0
    out = verts.copy()
    out[mask, 2] += dz
    return out, dz


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

    unweighted = 0
    for v in ob.data.vertices:
        if not any(ge.weight > 1e-6 for ge in v.groups):
            unweighted += 1
    return len(ob.data.vertices), unweighted


def smooth_vertex_weights(ob, rounds=2, alpha=0.5):
    """Laplacian-smooth the skin weights across the mesh topology.

    Where two neighbouring bones pull in very different directions -- thumb vs
    index across the web of the hand -- a sharp weight transition makes the
    surface pinch inwards.  Averaging each vertex's weights with its
    neighbours spreads the transition out, which is how the pinch is removed
    without moving any bone.
    """
    me = ob.data
    n = len(me.vertices)
    adj = [[] for _ in range(n)]
    for e in me.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)
    gname = {g.index: g.name for g in ob.vertex_groups}
    W = [{gname[ge.group]: ge.weight for ge in v.groups
          if ge.weight > 1e-6 and ge.group in gname} for v in me.vertices]
    for _ in range(rounds):
        NW = []
        for i, w in enumerate(W):
            acc = {k: v * (1.0 - alpha) for k, v in w.items()}
            nb = adj[i]
            if nb:
                share = alpha / len(nb)
                for j in nb:
                    for k, val in W[j].items():
                        acc[k] = acc.get(k, 0.0) + val * share
            tot = sum(acc.values())
            NW.append({k: v / tot for k, v in acc.items() if v > 1e-6}
                      if tot > 1e-9 else w)
        W = NW
    for g in list(ob.vertex_groups):
        ob.vertex_groups.remove(g)
    groups = {}
    for i, w in enumerate(W):
        # the exporter demands weights summing to exactly 1.0, and rounding
        # the tail away leaves ~1e-4 behind -- fold the residue into the
        # dominant bone
        tot = sum(w.values())
        if tot > 1e-9:
            w = {k: v / tot for k, v in w.items()}
            top = max(w, key=w.get)
            w[top] += 1.0 - sum(w.values())
        for name, val in w.items():
            g = groups.get(name)
            if g is None:
                g = ob.vertex_groups.new(name=name)
                groups[name] = g
            g.add([i], val, 'REPLACE')
    return len(groups)


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

    # The retarget: one transform per X4 bone, blended by skin weights.  The
    # source rig is the union of every part's skeleton, built once and reused.
    rose_pos, rose_parents = load_re8_skeleton_union()
    print("source rig: %d bones (%d parts)" % (len(rose_pos), len(PARTS)))
    transfer = BindPoseRetarget(rose_pos, rose_parents, x4_bones)

    # bone map once, from the union of all parts (reporting only)
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
        # Move the whole part onto the X4 bind pose, bone by bone.
        arr, n_unweighted, n_targets = transfer.transform(
            part['verts'], part['weights'], part['weighted_bones'])
        # weights -> X4, merged and normalised (needed by the foot lift)
        new_weights = transfer.merge_weights(part['weights'],
                                             part['weighted_bones'])
        arr, lifted = lift_feet(arr, new_weights)
        if lifted:
            print("      [%s] feet raised %.2f cm to stand on the floor"
                  % (tag, lifted))
        new_verts = [tuple(float(x) for x in v) for v in arr]
        if n_unweighted:
            print("      [%s] %d vertices have no X4 bone, keeping the frame fit"
                  % (tag, n_unweighted))

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
            # Reverse every triangle.  The RE8 -> X4 frame conversion is a
            # *reflection* (RE8 reads (x, up, forward), X4 reads (x, forward,
            # up), so the two axis triples have opposite handedness) and the
            # whole vertex transform therefore has det = -1.  Copying the
            # source winding would flip every face normal inwards, which the
            # renderer shows as clothes turning transparent (you see the far
            # inner shell), scrambled shading, and a face that has vanished.
            sfaces_local = [tuple(remap[i] for i in reversed(f)) for f in sfaces]

            me = bpy.data.meshes.new("%s_%d" % (tag_clean, si))
            me.from_pydata(sverts, [], sfaces_local)
            me.validate(verbose=False)
            me.update()
            # Smooth shading.  RE8's meshes are smooth-shaded and `from_pydata`
            # leaves everything flat; on a decimated mesh flat shading turns
            # every irregular triangle into a visible facet, which is the
            # "furrowed" look in game.  It also merges normal seams, so the
            # exported vertex count drops instead of rising.
            for poly in me.polygons:
                poly.use_smooth = True
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
            # no weight smoothing on the hands either -- with the fingers
            # bound to the palm the weights there are already uniform, and
            # perturbing the vertices only disturbs the normal map
            if tag not in ('hand_l', 'hand_r'):
                smooth_vertex_weights(ob)
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
