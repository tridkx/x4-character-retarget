# -*- coding: utf-8 -*-
"""
Frame-independent binding check: how far is each vertex from the bones that
drive it?  Big distances mean weights landed on unrelated bones.
"""
import importlib, os, sys
import numpy as np
import bpy, addon_utils, pathlib

ADDON = r"D:\dsh-x4\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
ROOT = r"D:\dsh-x4\work\x4root"
sys.path.insert(0, ADDON)
sys.path.insert(0, r"D:\dsh-x4\work\tools")

import build_mod  # noqa: E402


def analyse(xac_path, label):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A
    A.import_actor(bpy.context, pathlib.Path(xac_path))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    mw = arm.matrix_world
    bones = {b.name: (mw @ b.head_local, mw @ b.tail_local) for b in arm.data.bones}

    print("=" * 78)
    print(label)
    worst = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.get('x4cc_actor_id'):
            continue
        if len(ob.data.vertices) < 50:
            continue
        gname = {g.index: g.name for g in ob.vertex_groups}
        d = []
        for v in ob.data.vertices:
            best, bw = None, 0.0
            for ge in v.groups:
                if ge.weight > bw:
                    bw, best = ge.weight, gname.get(ge.group)
            if best is None or best not in bones:
                continue
            h, t = bones[best]
            p = ob.matrix_world @ v.co
            # 点到骨骼线段的距离
            ab = t - h
            denom = ab.dot(ab) or 1.0
            u = max(0.0, min(1.0, (p - h).dot(ab) / denom))
            d.append(((p - (h + ab * u)).length, best, bw))
        if not d:
            continue
        arr = np.array([x[0] for x in d])
        print("  %-18s v=%-6d 平均=%.2fcm 中位=%.2f p95=%.2f 最大=%.2f" % (
            ob.name, len(d), arr.mean(), np.median(arr),
            np.percentile(arr, 95), arr.max()))
        for dist, bone, w in sorted(d, reverse=True)[:5]:
            worst.append((dist, ob.name, bone, w))
    print("  --- 最差顶点 ---")
    for dist, ob, bone, w in sorted(worst, reverse=True)[:10]:
        print("     %6.1fcm  %-18s 骨骼=%-20s 权重=%.2f" % (dist, ob, bone, w))


if __name__ == '__main__':
    V = r"D:\dsh-x4\work\vanilla\assets\characters\argon"
    analyse(V + r"\bodies\char_arg_f_sweater_leggings_civ_01.xac", "原版 body（参照）")
    analyse(r"D:\dsh-x4\work\x4_rose_mod\assets\characters\argon\rose\bodies\rose_body.xac",
            "我的 rose_body")
