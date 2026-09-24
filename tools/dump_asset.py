# -*- coding: utf-8 -*-
"""Dump a .xac (bones + skinned meshes) to .npz for offline analysis.

Run inside Blender:
    blender -b --factory-startup --python tools/dump_asset.py -- <xac> <out.npz> [tag]

The point is to get the *authoritative* skeleton the game will use -- head,
tail and the full local orientation of every bone -- plus per-vertex skin
weights, into plain numpy arrays so retarget experiments do not need Blender.
"""




# --- 项目根自动定位（work 已并入 x4-character-retarget）---
import os
_X4_WORK_PKG = os.path.dirname(os.path.abspath(__file__))
_X4_DEV_ROOT = _X4_WORK_PKG
while os.path.basename(_X4_DEV_ROOT) != 'x4-character-retarget':
    _X4_UP = os.path.dirname(_X4_DEV_ROOT)
    if _X4_UP == _X4_DEV_ROOT:
        break
    _X4_DEV_ROOT = _X4_UP
_X4_DEV_ROOT = os.path.dirname(_X4_DEV_ROOT)
_X4_SHARED = os.path.join(_X4_DEV_ROOT, 'shared')

# --- 项目根自动定位（work 已并入 x4-character-retarget）---
import os
import importlib
import pathlib
import sys

import addon_utils
import bpy
import numpy as np

ADDON = os.path.join(_X4_SHARED, r"X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03")
ROOT = os.path.join(_X4_SHARED, r"x4root")

sys.path.insert(0, ADDON)


def dump(xac_path, out_path, tag):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A
    A.import_actor(bpy.context, pathlib.Path(xac_path))

    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    mw = arm.matrix_world
    names, parents, heads, tails, mats = [], [], [], [], []
    for b in arm.data.bones:
        names.append(b.name)
        parents.append(b.parent.name if b.parent else '')
        heads.append(list(mw @ b.head_local))
        tails.append(list(mw @ b.tail_local))
        mats.append([list(row) for row in (mw @ b.matrix_local).to_3x3()])

    v_pos, v_widx, v_wval, v_part, v_obj = [], [], [], [], []
    edges_i, edges_j, e_part = [], [], []
    parts = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.get('x4cc_actor_id'):
            continue
        me = ob.data
        pi = len(parts)
        parts.append(ob.name)
        gname = {g.index: g.name for g in ob.vertex_groups}
        base = len(v_pos)
        omw = ob.matrix_world
        for v in me.vertices:
            v_pos.append(list(omw @ v.co))
            idx = [gname.get(ge.group, '') for ge in v.groups if ge.weight > 1e-6]
            val = [float(ge.weight) for ge in v.groups if ge.weight > 1e-6]
            keep = [(i, w) for i, w in zip(idx, val) if i]
            v_widx.append([k for k, _ in keep])
            v_wval.append([w for _, w in keep])
            v_part.append(pi)
        for e in me.edges:
            edges_i.append(base + e.vertices[0])
            edges_j.append(base + e.vertices[1])
            e_part.append(pi)

    np.savez_compressed(
        out_path,
        tag=tag,
        bone_names=np.array(names, dtype=object),
        bone_parents=np.array(parents, dtype=object),
        bone_heads=np.array(heads, dtype=np.float64),
        bone_tails=np.array(tails, dtype=np.float64),
        bone_mats=np.array(mats, dtype=np.float64),
        verts=np.array(v_pos, dtype=np.float64),
        w_idx=np.array(v_widx, dtype=object),
        w_val=np.array(v_wval, dtype=object),
        v_part=np.array(v_part, dtype=np.int32),
        part_names=np.array(parts, dtype=object),
        edge_i=np.array(edges_i, dtype=np.int32),
        edge_j=np.array(edges_j, dtype=np.int32),
    )
    print("DUMPED %s -> %s  bones=%d verts=%d meshes=%d"
          % (tag, out_path, len(names), len(v_pos), len(parts)))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    xac, out = argv[0], argv[1]
    tag = argv[2] if len(argv) > 2 else os.path.basename(xac)
    dump(xac, out, tag)
