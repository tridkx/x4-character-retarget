# -*- coding: utf-8 -*-
"""
Single source of truth for the frames used by each pipeline stage.

Reports, for the hand specifically (it is the most sensitive part):
  stage 0  RE8 source mesh            (metres)
  stage 1  what build_rose_x4 writes  (stage1 .blend)
  stage 2  what build_mod sends to Blender (= what the exporter reads)
  stage 3  the exported .xac, re-imported, vs the bone it must sit on

Read-only.  Prints numbers only; no fixes are attempted here.
"""
import importlib, json, os, sys
import numpy as np
import bpy, addon_utils, pathlib
WORK = r"D:\dsh-x4\work"
ADDON = r"D:\dsh-x4\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
ROOT = os.path.join(WORK, "x4root")
sys.path.insert(0, ADDON)

def bones_of():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A
    A.import_actor(bpy.context, pathlib.Path(os.path.join(
        ROOT, r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac")))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    return {b.name: np.array(list(b.head_local)) for b in arm.data.bones}

B = bones_of()
hb = B['Bip01 L Hand']
print("X4 手骨 (Blender 空间, 权威)      = (%.1f, %.1f, %.1f)" % (hb[0], hb[1], hb[2]))

# stage1
bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, "rose_x4_stage1.blend"))
allv = []
for ob in bpy.data.objects:
    if ob.type == 'MESH' and ob.get('x4cc_part') == 'hand_l':
        allv.append(np.array([[v.co.x, v.co.y, v.co.z] for v in ob.data.vertices]))
a1 = np.concatenate(allv)
print("stage1 hand_l 中心               = (%.1f, %.1f, %.1f)" % tuple(a1.mean(axis=0)))
print("  范围 X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]" % (
    a1[:,0].min(),a1[:,0].max(),a1[:,1].min(),a1[:,1].max(),
    a1[:,2].min(),a1[:,2].max()))

# stage2: replicate exactly what fill_slot does
pass
src = None
for ob in bpy.data.objects:
    if ob.type == 'MESH' and ob.get('x4cc_part') == 'hand_l':
        src = ob
        break
raw = np.array([[v.co.x, v.co.y, v.co.z] for v in src.data.vertices])
# current fill_slot transform
def fill(p):  # keep in sync with build_mod.fill_slot
    return (p[0], p[1], p[2])
sent = np.array([fill(p) for p in raw])
print("stage2 送给 Blender 的中心        = (%.1f, %.1f, %.1f)  [fill_slot 直通]" % tuple(sent.mean(axis=0)))
print("   -> 与手骨的欧氏差 = %.1f cm" % float(np.linalg.norm(sent.mean(axis=0) - hb)))

# stage3
A_path = os.path.join(WORK, "x4_rose_mod", "assets", "characters", "argon",
                      "rose", "bodies", "rose_body.xac")
if os.path.exists(A_path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A2
    A2.import_actor(bpy.context, pathlib.Path(A_path))
    arm2 = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    h2 = np.array(list(arm2.data.bones['Bip01 L Hand'].head_local))
    print("stage3 XAC 手骨                  = (%.1f, %.1f, %.1f)" % tuple(h2))
    for o in bpy.data.objects:
        if o.type == 'MESH' and 'hands' in o.name:
            aa = np.array([[v.co.x, v.co.y, v.co.z] for v in o.data.vertices])
            print("stage3 XAC 手网格中心            = (%.1f, %.1f, %.1f)" % tuple(aa.mean(axis=0)))
            print("   -> 蒙皮中心差 = %.1f cm" % float(np.linalg.norm(aa.mean(axis=0) - h2)))
            break
