# -*- coding: utf-8 -*-
"""Trace where Rose's hand ends up at each pipeline stage. Read-only."""




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
import importlib, os, sys, json
import numpy as np
import bpy, addon_utils, pathlib
ADDON = os.path.join(_X4_SHARED, r"X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03")
ROOT = os.path.join(_X4_SHARED, r"x4root")
sys.path.insert(0, ADDON)
sys.path.insert(0, os.path.join(_X4_DEV_ROOT, 'x4-character-retarget', 'work', r"tools"))

print("## 阶段 0: RE8 原始骨骼（米）")
RS = json.load(open(r"D:\dsh-mod\re8\output\models\Rose_Adult_ShadowsOfRose"
                    r"\ch01_6060_hand_l_skeleton.json", encoding='utf-8'))
m = {b['name']: b for b in RS['bones']}['L_Hand']['worldMatrix']
p0 = np.array([m[3][0], m[3][1], m[3][2]])
print("   RE8 L_Hand =", np.round(p0, 4), "  (x=左右 y=身高 z=前后)")

print()
print("## 阶段 1: re8_to_x4 之后（cm）")
import re8_to_x4 as R
p1 = np.array(R.re8_to_x4(p0))
print("   =", np.round(p1, 1), "  <- 现在写进 stage1 的就是这个")

print()
print("## 阶段 2: 插件导入原版 XAC 后，骨骼在 Blender 里的位置")
bpy.ops.wm.read_factory_settings(use_empty=True)
importlib.import_module("X4CharacterConverter")
addon_utils.enable("X4CharacterConverter", default_set=True)
bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
from X4CharacterConverter import addon as A

# tools/ 与 work/ 两种深度都恰好再上两层到 dsh-x4（已用断言实测）
A.import_actor(bpy.context, pathlib.Path(os.path.join(
    ROOT, r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac")))
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
hb = arm.data.bones['Bip01 L Hand'].head_local
print("   Bip01 L Hand (Blender) =", np.round([hb.x, hb.y, hb.z], 1))
print("   插件的 xac_to_blender 用在这个值上会得到:",
      np.round(A.xac_to_blender_vector([hb.x, hb.y, hb.z]), 1))

print()
print("## 阶段 3: stage1 里手部顶点（read_part_geometry 读出）")
bpy.ops.wm.open_mainfile(filepath=os.path.join(_X4_DEV_ROOT, 'x4-character-retarget', 'work', r"rose_x4_stage1.blend"))
ob = bpy.data.objects.get('rose_hand_l_0')
a = np.array([[v.co.x, v.co.y, v.co.z] for v in ob.data.vertices])
print("   stage1 rose_hand_l_0 中心 =", np.round(a.mean(axis=0), 1))
print("   范围 X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]" % (
    a[:,0].min(),a[:,0].max(), a[:,1].min(),a[:,1].max(), a[:,2].min(),a[:,2].max()))

print()
print("## 阶段 4: 导出的 XAC 里手部顶点 + 骨骼（同一文件，同一空间）")
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("X4CharacterConverter", default_set=True)
bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
A.import_actor(bpy.context, pathlib.Path(
    os.path.join(_X4_DEV_ROOT, 'x4-character-retarget', 'work', r"x4_rose_mod\assets\characters\argon\rose\bodies\rose_body.xac")))
arm2 = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
hb2 = arm2.data.bones['Bip01 L Hand'].head_local
print("   XAC 骨骼 L Hand (导入后 Blender) =", np.round([hb2.x, hb2.y, hb2.z], 1))
for o in bpy.data.objects:
    if o.type == 'MESH' and 'hands' in o.name:
        aa = np.array([[v.co.x, v.co.y, v.co.z] for v in o.data.vertices])
        print("   XAC 手部网格中心 =", np.round(aa.mean(axis=0), 1))
        print("   范围 X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]" % (
            aa[:,0].min(),aa[:,0].max(), aa[:,1].min(),aa[:,1].max(),
            aa[:,2].min(),aa[:,2].max()))
        print("   -> 手骨与手网格的距离 = %.1f cm" % float(np.linalg.norm(
            aa.mean(axis=0) - np.array([hb2.x, hb2.y, hb2.z]))))
