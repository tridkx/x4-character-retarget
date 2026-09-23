# -*- coding: utf-8 -*-
"""Follow ONE identifiable vertex through every stage. Read-only trace."""
import importlib, json, os, sys
import numpy as np
import bpy, addon_utils, pathlib
WORK = r"D:\dsh-x4\work"
ADDON = r"D:\dsh-x4\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
ROOT = os.path.join(WORK, "x4root")
sys.path.insert(0, ADDON); sys.path.insert(0, os.path.join(WORK, "tools"))
sys.path.insert(0, r"D:\dsh-mod\re8\tools\RE-Mesh-Editor-main")

# --- stage 0: RE8 source (hand_l, first vertex) --------------------------
from modules.mesh.file_re_mesh import readREMesh
from modules.mesh.re_mesh_parse import ParsedREMesh
raw = readREMesh(r"D:\dsh-mod\re8\output\raw_natives\natives\stm\_ge\character"
                 r"\ch\ch01\6000\6060\ch01_6060_hand_l.mesh.2101050001")
pp = ParsedREMesh(); pp.ParseREMesh(raw)
sm = pp.mainMeshLODList[0].visconGroupList[0].subMeshList[0]
v0 = np.array(sm.vertexPosList[0], float)
print("S0 RE8 源 (m)            =", np.round(v0, 4))

# --- stage 1: after re8_to_x4 -------------------------------------------
import re8_to_x4 as R
v1 = np.array(R.re8_to_x4(v0, 1.0))
print("S1 re8_to_x4 (cm)        =", np.round(v1, 2))

# --- stage 2: what stage1 actually stores -------------------------------
bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, "rose_x4_stage1.blend"))
ob = bpy.data.objects.get('rose_hand_l_0')
v2 = np.array(list(ob.data.vertices[0].co))
print("S2 stage1 实测           =", np.round(v2, 2))

# --- stage 3: what fill_slot writes to Blender --------------------------
v3 = np.array([v2[0], -v2[2], v2[1]])
print("S3 fill_slot -> Blender  =", np.round(v3, 2))

# --- stage 4: exported XAC (reimported = Blender space again) -----------
bpy.ops.wm.read_factory_settings(use_empty=True)
importlib.import_module("X4CharacterConverter")
addon_utils.enable("X4CharacterConverter", default_set=True)
bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
from X4CharacterConverter import addon as A
A.import_actor(bpy.context, pathlib.Path(
    os.path.join(WORK, "x4_rose_mod", "assets", "characters", "argon",
                 "rose", "bodies", "rose_body.xac")))
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
hb = arm.data.bones['Bip01 L Hand'].head_local
print("S4 XAC 手骨 (Blender)    =", np.round([hb.x, hb.y, hb.z], 2))
for o in bpy.data.objects:
    if o.type == 'MESH' and 'hands' in o.name:
        allv = np.array([[v.co.x, v.co.y, v.co.z] for v in o.data.vertices])
        # nearest vertex to our traced point
        d = np.linalg.norm(allv - v3, axis=1)
        i = int(d.argmin())
        print("S4 XAC 手网格 范围       = X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]" % (
            allv[:,0].min(),allv[:,0].max(), allv[:,1].min(),allv[:,1].max(),
            allv[:,2].min(),allv[:,2].max()))
        print("   S3 点最近邻 (i=%d, d=%.1f) =" % (i, d[i]), np.round(allv[i], 2))
        break
