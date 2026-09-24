# -*- coding: utf-8 -*-
"""Which finger bones are mis-assigned on Rose's hands?"""
import importlib, os, sys
from collections import defaultdict
import numpy as np
import bpy, addon_utils, pathlib
ADDON = r"D:\dsh-x4\shared\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
ROOT = r"D:\dsh-x4\shared\x4root"
sys.path.insert(0, ADDON)
sys.path.insert(0, r"D:\dsh-x4\work\tools")

V = r"D:\dsh-x4\work\vanilla\assets\characters\argon"
path = (sys.argv[-1] if sys.argv[-1].endswith('.xac')
        else V + r"\bodies\char_arg_f_sweater_leggings_civ_01.xac")

bpy.ops.wm.read_factory_settings(use_empty=True)
importlib.import_module("X4CharacterConverter")
addon_utils.enable("X4CharacterConverter", default_set=True)
bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
from X4CharacterConverter import addon as A
A.import_actor(bpy.context, pathlib.Path(path))
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
mw = arm.matrix_world
bones = {b.name: (np.array(list(mw @ b.head_local)),
                  np.array(list(mw @ b.tail_local))) for b in arm.data.bones}

for ob in bpy.data.objects:
    if ob.type != 'MESH' or not ob.get('x4cc_actor_id'):
        continue
    if not any(k in ob.name.lower() for k in ('hand', 'Hands')):
        continue
    gname = {g.index: g.name for g in ob.vertex_groups}
    per = defaultdict(list)
    for v in ob.data.vertices:
        best, bw = None, 0.0
        for ge in v.groups:
            if ge.weight > bw:
                bw, best = ge.weight, gname.get(ge.group)
        if best is None or best not in bones:
            continue
        p = np.array(list(ob.matrix_world @ v.co))
        h, t = bones[best]
        ab = t - h
        u = max(0.0, min(1.0, float((p - h) @ ab) / (float(ab @ ab) or 1.0)))
        per[best].append(float(np.linalg.norm(p - (h + ab * u))))
    print("=" * 74)
    print("%s  (%d verts)" % (ob.name, len(ob.data.vertices)))
    print("%-22s %6s %10s %10s %10s" % ("骨骼", "顶点", "平均", "中位", "最大"))
    for bn in sorted(per, key=lambda k: -np.mean(per[k])):
        a = np.array(per[bn])
        print("%-22s %6d %9.1f %10.1f %10.1f" % (bn, len(a), a.mean(),
                                                 np.median(a), a.max()))
