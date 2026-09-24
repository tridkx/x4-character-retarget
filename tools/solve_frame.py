# -*- coding: utf-8 -*-
"""
Solve the mesh frame EMPIRICALLY.

For every candidate transform T of the RE8 source vertices, run the real
pipeline in-process:
    source verts --T--> Blender mesh --> converter export --> re-import
and score the re-imported asset with the skinning error
(mean distance from each vertex to the bone that dominates it).

Vanilla assets score ~1.9 cm.  The transform that scores like vanilla is the
correct one; no derivation required.
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

import os
import importlib, itertools, os, shutil, sys
import numpy as np
import bpy, addon_utils, pathlib
WORK = os.path.join(_X4_DEV_ROOT, 'x4-character-retarget', 'work')
ADDON = os.path.join(_X4_SHARED, r"X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03")
ROOT = os.path.join(_X4_SHARED, r"x4root")
sys.path.insert(0, ADDON)
sys.path.insert(0, os.path.join(WORK, "tools"))
sys.path.insert(0, r"D:\dsh-mod\re8\tools\RE-Mesh-Editor-main")

from modules.mesh.file_re_mesh import readREMesh
from modules.mesh.re_mesh_parse import ParsedREMesh
import re8_to_x4 as R

HOST = os.path.join(ROOT, r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac")
PKG = os.path.join(WORK, "x4cc_solve")
MESH = (r"D:\dsh-mod\re8\output\raw_natives\natives\stm\_ge\character"
        r"\ch\ch01\6000\6060\ch01_6060_hand_l.mesh.2101050001")
SKEL = (r"D:\dsh-mod\re8\output\models\Rose_Adult_ShadowsOfRose"
        r"\ch01_6060_hand_l_skeleton.json")
import json

# tools/ 与 work/ 两种深度都恰好再上两层到 dsh-x4（已用断言实测）
_a = json.load(open(SKEL, encoding='utf-8'))
SCALE = 100.0


def source_hand():
    """RE8 hand vertices (metres) + weights already mapped to X4 bone names."""
    raw = readREMesh(MESH)
    p = ParsedREMesh(); p.ParseREMesh(raw)
    sm = p.mainMeshLODList[0].visconGroupList[0].subMeshList[0]
    V = np.array(sm.vertexPosList, float)
    wb = list(p.skeleton.weightedBones)
    W = []
    for i in range(len(V)):
        w = {}
        if i < len(sm.weightList):
            for k in range(len(sm.weightList[i])):
                wv = float(sm.weightList[i][k])
                if wv > 1e-6:
                    t = R.map_bone(wb[sm.weightIndicesList[i][k]])
                    if t:
                        w[t] = w.get(t, 0.0) + wv
        W.append(w)
    faces = []
    for f in sm.faceList:
        faces.append(tuple(f))
    return V, W, faces


def probe(vs, W, faces, tag):
    """Build -> export -> reimport -> skinning error."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A

    if os.path.isdir(PKG):
        shutil.rmtree(PKG)
    os.makedirs(PKG)
    A.import_actor(bpy.context, pathlib.Path(HOST))
    host = None
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.get('x4cc_mesh_id') == 1:
            host = ob
    if host is None:
        return None
    me = bpy.data.meshes.new("probe")
    me.from_pydata([tuple(v) for v in vs], [], faces)
    me.validate(verbose=False); me.update()
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        uv.data[loop.index].uv = (0.0, 0.0)
    host.data = me
    host.name = "rose_body_torso"
    for g in list(host.vertex_groups):
        host.vertex_groups.remove(g)
    grp = {}
    for vi, wd in enumerate(W):
        for gn, gv in wd.items():
            g = grp.get(gn)
            if g is None:
                g = host.vertex_groups.new(name=gn); grp[gn] = g
            g.add([vi], gv, 'REPLACE')
    import glob
    dds = sorted(glob.glob(os.path.join(WORK, "tex_out", "mats", "*_diff.dds")))
    if not dds:
        return "NO-TEX"
    mat = bpy.data.materials.new("rose.probe")
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    on = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bs.outputs["BSDF"], on.inputs["Surface"])
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(dds[0], check_existing=True)
    tx.name = "Diffuse"
    nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
    me.materials.append(mat)
    for ob in list(bpy.data.objects):
        if ob.type == 'MESH' and ob is not host:
            bpy.data.objects.remove(ob, do_unlink=True)
    try:
        A.export_package(bpy.context, pathlib.Path(os.path.join(PKG, "probe")))
    except Exception as exc:
        return "EXPORT-FAIL:%s" % str(exc)[:40]

    out = os.path.join(PKG, "probe", "assets", "characters", "mycharacters",
                       "bodies", "probe.xac")
    if not os.path.exists(out):
        return "NO-XAC"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    A.import_actor(bpy.context, pathlib.Path(out))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    B = {b.name: (np.array(list(b.head_local)), np.array(list(b.tail_local)))
         for b in arm.data.bones}
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.get('x4cc_actor_id'):
            continue
        if len(ob.data.vertices) < 50:
            continue
        gname = {g.index: g.name for g in ob.vertex_groups}
        tot, n = 0.0, 0
        for v in ob.data.vertices:
            dom, bw = None, 0.0
            for ge in v.groups:
                if ge.weight > bw:
                    bw, dom = ge.weight, gname.get(ge.group)
            if dom is None or dom not in B:
                continue
            h, t = B[dom]
            ab = t - h; L2 = float(ab @ ab) or 1.0
            p = np.array(list(v.co))
            u = max(0.0, min(1.0, float((p - h) @ ab) / L2))
            tot += float(np.linalg.norm(p - (h + ab * u))); n += 1
        return tot / n if n else None
    return None


def main():
    V, W, F = source_hand()
    print("RE8 原始 hand_l: %d 顶点" % len(V), flush=True)
    print("  范围 X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f] (米)" % (
        V[:,0].min(),V[:,0].max(), V[:,1].min(),V[:,1].max(),
        V[:,2].min(),V[:,2].max()), flush=True)
    rows = []
    # 只扫「偶排列 + 任意符号」这些正交变换，且先用厘米缩放
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            def T(v, p=perm, s=signs):
                return (v[p[0]] * s[0] * SCALE, v[p[1]] * s[1] * SCALE,
                        v[p[2]] * s[2] * SCALE)
            vs = [T(v) for v in V]
            r = probe(vs, W, F, "T")
            rows.append((r if isinstance(r, float) else 9e9, perm, signs, r))
            print("   perm=%s signs=%s -> %s" % (
                perm, signs, ("%.2f cm" % r) if isinstance(r, float) else r),
                flush=True)
    rows.sort(key=lambda x: x[0])
    print("\n=== 最优 ===", flush=True)
    for d, perm, signs, raw in rows[:4]:
        print("   perm=%s signs=%s  -> %s" % (
            perm, signs, ("%.2f cm" % d) if d < 9e9 else raw), flush=True)


main()
