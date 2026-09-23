# -*- coding: utf-8 -*-
"""
Rose -> X4 mod builder (stage 2).

Reads `rose_x4_stage1.blend` (already retargeted, weighted and material
assigned) and writes the two XAC assets the mod needs, then assembles the
mod tree.

Why two XAC files
-----------------
An X4 NPC macro has separate `head` and `torso` model slots, so Rose's parts
are split across two assets.  Both are exported from vanilla hosts, because
the converter can only *rebuild* meshes that already exist in the template:

    head : host char_arg_f_dyn_blend_head          (5 mesh slots)
           face -> 0, eye_a -> 1, hair -> 2, unused 3..4
    body : host char_arg_f_sweater_leggings_civ_01 (4 mesh slots)
           hands -> 0, torso(body+sling) -> 1, jacket -> 2, unused 3

Blender object names must match [A-Za-z0-9_]+ and material names must match
[a-z0-9_]+\\.[a-z0-9_]+ -- both are enforced by the converter.

    blender -b --factory-startup --python tools/build_mod.py
"""

import importlib
import json
import os
import shutil
import subprocess
import sys

import addon_utils
import bpy
import pathlib
from mathutils import Matrix

WORK = r"D:\dsh-x4\work"
ADDON_DIR = r"D:\dsh-x4\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
X4_ROOT = os.path.join(WORK, "x4root")
RE8_MODELS = r"D:\dsh-mod\re8\output\models\Rose_Adult_ShadowsOfRose"
STAGE1 = os.path.join(WORK, "rose_x4_stage1.blend")

MOD_ROOT = os.path.join(WORK, "x4_rose_mod")
MOD_ID = "x4_rose_mod"
DDS_DIR = os.path.join(WORK, "tex_out", "mats")
TMP_DIR = os.path.join(WORK, "tex_out", "tmp")
PKG_DIR = os.path.join(WORK, "x4cc_pkg")

sys.path.insert(0, os.path.join(WORK, "tools"))
sys.path.insert(0, ADDON_DIR)

import x4_materials  # noqa: E402

#: stage1 geometry is authored in X4 space (Z-up, cm).  A Blender scene is
#: Y-up, so rotate on the way in; the exporter rotates back on the way out.
X4_TO_BLENDER = Matrix.Rotation(__import__('math').radians(90.0), 4, 'X')

#: Submeshes dropped from the export.
#:
#: RE8 ships the eyeball twice: `ch01_6020_rose_face` carries the real eye
#: (Eye_Mat, fully textured) while `ch01_6030_rose_eyes` carries a lens shell
#: (shader_eyeslens_shader) that has no albedo at all -- the source drives it
#: from shader params.  Since our exporter requires a diffuse map, the shell
#: would get an opaque placeholder and sit in front of the eyeball as a solid
#: sphere, which is what made the eyes read as blank white.  The same applies
#: to the wet-layer and lens meshes inside the face.  Dropping them exposes
#: the properly textured eyeball underneath.
DROP_SUBMESH_MATERIALS = {
    'shader_eyeslens_shader',
    'Eyelens_Mat',
    'EyeWet_Mat',
}

HOSTS = {
    'head': r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac",
    'body': r"assets\characters\argon\bodies\char_arg_f_sweater_leggings_civ_01.xac",
}

#: target -> [(object name, host mesh_id, [stage1 parts to merge])]
SLOT_PLAN = {
    'head': [
        ("rose_head_face", 0, ['face']),
        ("rose_head_eye", 1, ['eyes']),
        ("rose_head_hair", 2, ['hair']),
    ],
    'body': [
        ("rose_body_hands", 0, ['hand_l', 'hand_r']),
        ("rose_body_torso", 1, ['body', 'slingbelt']),
        ("rose_body_jacket", 2, ['jacket']),
    ],
}

#: materials whose diffuse must carry alpha (BC3)
ALPHA_MATS = {'Sling_Mat', 'Hair_Mat', 'Stray_Hair_Mat', 'eyelashes_Mat',
              'shader_eyes_shader'}


# --------------------------------------------------------------------------
# stage 1 -> plain python geometry
# --------------------------------------------------------------------------

def read_part_geometry():
    """{part: [ {material_name, verts, weights, faces} ]} from stage1.

    Lifted into plain Python before the scene is reset, because all Blender
    datablocks are invalidated by read_factory_settings.
    """
    bpy.ops.wm.open_mainfile(filepath=STAGE1)
    parts = {}
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        part = ob.get('x4cc_part')
        if not part:
            continue

        me = ob.data
        gname = {g.index: g.name for g in ob.vertex_groups}
        verts = [tuple(v.co) for v in me.vertices]
        weights = []
        for v in me.vertices:
            wd = {}
            for ge in v.groups:
                if ge.weight > 1e-6:
                    nm = gname.get(ge.group)
                    if nm:
                        wd[nm] = wd.get(nm, 0.0) + ge.weight
            weights.append(wd)

        uv_layer = me.uv_layers[0].data if len(me.uv_layers) else None
        by_mat = {}
        for poly in me.polygons:
            mat = (me.materials[poly.material_index]
                   if poly.material_index < len(me.materials) else None)
            mn = mat.name if mat else None
            by_mat.setdefault(mn, []).append(poly)

        entry = []
        for mn, polys in by_mat.items():
            if mn in DROP_SUBMESH_MATERIALS:
                continue
            # UVs live on loops, so they are carried per triangle corner
            uvs = []
            if uv_layer is not None:
                for poly in polys:
                    for li in poly.loop_indices:
                        uvs.append(tuple(uv_layer[li].uv))
            entry.append({'material_name': mn,
                          'verts': verts,
                          'weights': weights,
                          'uvs': uvs,
                          'faces': [tuple(p.vertices) for p in polys]})
        parts.setdefault(part, []).extend(entry)
    return parts


def plant_host(host_key):
    """Import the vanilla host; returns its {mesh_id: object}."""
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = X4_ROOT + os.sep
    from X4CharacterConverter import addon as A

    path = os.path.join(X4_ROOT, HOSTS[host_key])
    A.import_actor(bpy.context, pathlib.Path(path))

    out = {}
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.get("x4cc_actor_id"):
            mid = ob.get("x4cc_mesh_id")
            if mid is not None:
                out[int(mid)] = ob
    return out


def fill_slot(host_ob, obj_name, sources, materials):
    """Replace a host mesh with merged Rose geometry.

    Each source entry carries its own face list indexing into *its own*
    vertex array, so the two are remapped together; appending every source's
    full vertex array would corrupt the indices.
    """
    verts, weights, faces, uvs, mat_order, mat_index = [], [], [], [], [], {}

    for src in sources:
        mn = src['material_name']
        mat = materials.get(mn) or materials.get(None)
        if mat is None:
            continue
        if mat.name not in mat_index:
            mat_index[mat.name] = len(mat_order)
            mat_order.append(mat)
        slot = mat_index[mat.name]

        base = len(verts)
        for p in src['verts']:
            verts.append((p[0], p[1], p[2]))
        weights.extend(src['weights'])
        for f in src['faces']:
            faces.append((f[0] + base, f[1] + base, f[2] + base, slot))
        uvs.extend(src.get('uvs') or [])

    if not faces:
        verts = [(0.0, 0.0, 0.0)] * 3
        weights = [{}, {}, {}]
        faces = [(0, 1, 2, 0)]
        mat_order = [next(iter(materials.values()))]

    me = bpy.data.meshes.new(obj_name)
    me.from_pydata(verts, [], [(f[0], f[1], f[2]) for f in faces])
    me.validate(verbose=False)
    me.update()
    for m in mat_order:
        me.materials.append(m)
    for poly, f in zip(me.polygons, faces):
        poly.material_index = f[3]

    uv = me.uv_layers.new(name="UVMap")
    if len(uvs) == len(me.loops):
        # pass UVs through unchanged: the exporter applies `1.0 - uv.y`
        # itself when writing the XAC, so flipping here would double-flip.
        for loop, v in zip(me.loops, uvs):
            uv.data[loop.index].uv = (v[0], v[1])
    else:
        for loop in me.loops:
            uv.data[loop.index].uv = (0.0, 0.0)

    host_ob.data = me
    host_ob.name = obj_name
    for g in list(host_ob.vertex_groups):
        host_ob.vertex_groups.remove(g)
    groups = {}
    for vi, wd in enumerate(weights):
        for gname, gval in wd.items():
            g = groups.get(gname)
            if g is None:
                g = host_ob.vertex_groups.new(name=gname)
                groups[gname] = g
            g.add([vi], gval, 'REPLACE')
    return len(verts), len(faces), len(mat_order)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def build_asset(target):
    # stage1 geometry must be lifted into plain Python BEFORE the scene is
    # reset, and materials must be built AFTER it: read_factory_settings wipes
    # every datablock, so building them earlier leaves dangling references.
    parts = read_part_geometry()
    used = {s['material_name'] for e in parts.values() for s in e}
    print("[%s] parts=%s materials=%d" % (target, sorted(parts), len(used)))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = X4_ROOT + os.sep
    from X4CharacterConverter import addon as A2

    mats = x4_materials.create_materials(DDS_DIR, only=used)
    print("[%s] materials built: %d" % (target, len(mats)))

    A2.import_actor(bpy.context, pathlib.Path(
        os.path.join(X4_ROOT, HOSTS[target])))
    slots = {}
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.get("x4cc_actor_id"):
            mid = ob.get("x4cc_mesh_id")
            if mid is not None:
                slots[int(mid)] = ob
    print("[%s] host slots: %s" % (target, sorted(slots)))

    kept = []
    for obj_name, mesh_id, parts_wanted in SLOT_PLAN[target]:
        host_ob = slots.get(mesh_id)
        if host_ob is None:
            print("   !! slot %d missing" % mesh_id)
            continue
        sources = [s for p in parts_wanted for s in parts.get(p, [])]
        if not sources:
            bpy.data.objects.remove(host_ob, do_unlink=True)
            print("   -- slot %d (%s) empty, removed" % (mesh_id, obj_name))
            continue
        nv, nf, nm = fill_slot(host_ob, obj_name, sources, mats)
        print("   %-18s slot=%d verts=%-6d faces=%-6d mats=%d"
              % (obj_name, mesh_id, nv, nf, nm))
        kept.append(host_ob)

    for mesh_id, ob in slots.items():
        if ob not in kept:
            bpy.data.objects.remove(ob, do_unlink=True)

    out_dir = os.path.join(MOD_ROOT, 'assets', 'characters', 'argon',
                           'rose' if target == 'head' else 'rose_body')
    os.makedirs(out_dir, exist_ok=True)
    export_name = 'rose_head' if target == 'head' else 'rose_body'
    # export_package refuses to write into an existing directory, and it does
    # so *after* the meshes are built -- silently leaving the previous .xac in
    # place and making every downstream check look stale.
    pkg_target = os.path.join(PKG_DIR, export_name)
    if os.path.isdir(pkg_target):
        shutil.rmtree(pkg_target)
    pkg = A2.export_package(bpy.context, pathlib.Path(pkg_target))
    print("[%s] exported package -> %s" % (target, pkg))
    return pkg


def main():
    os.makedirs(PKG_DIR, exist_ok=True)
    for target in ('head', 'body'):
        build_asset(target)


if __name__ == '__main__':
    main()
