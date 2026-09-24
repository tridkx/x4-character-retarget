# -*- coding: utf-8 -*-
"""
Replace the per-segment affine fit with one global Kabsch alignment.

Both skeletons are expressed in the SAME space (the converter's Blender
arrangement, height in component 3), so the fit is well conditioned:

    RE8 bone (m)  --xac_to_blender((x, y, z) * 100)-->  Blender space
    X4  bone      --importer already yields Blender space-->

Result: a single (scale, R, t) mapping the whole mesh, which is what a
rigid retarget actually is.  Prints the residual so the fit can be judged.
"""
import importlib, json, os, sys
import numpy as np
import bpy, addon_utils, pathlib
WORK = r"D:\dsh-x4\work"
ADDON = r"D:\dsh-x4\shared\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
ROOT = r"D:\dsh-x4\shared\x4root"
sys.path.insert(0, ADDON)

# RE8 bones
RS = json.load(open(r"D:\dsh-mod\re8\output\models\Rose_Adult_ShadowsOfRose"
                    r"\ch01_6000_body_skeleton.json", encoding='utf-8'))
rose = {b['name']: np.array([b['worldMatrix'][3][0], b['worldMatrix'][3][1],
                             b['worldMatrix'][3][2]], float) for b in RS['bones']}

# X4 bones (Blender space, via the converter's own importer)
bpy.ops.wm.read_factory_settings(use_empty=True)
importlib.import_module("X4CharacterConverter")
addon_utils.enable("X4CharacterConverter", default_set=True)
bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
from X4CharacterConverter import addon as A
A.import_actor(bpy.context, pathlib.Path(os.path.join(
    ROOT, r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac")))
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
x4 = {b.name: np.array(list(b.head_local)) for b in arm.data.bones}

PAIRS = [
    ('Hip', 'Bip01 Pelvis'), ('Spine_0', 'Bip01 Spine'),
    ('Spine_1', 'Bip01 Spine1'), ('Spine_2', 'Bip01 Spine2'),
    ('Neck_0', 'Bip01 Neck'), ('Head', 'Bip01 Head'),
    ('L_Shoulder', 'Bip01 L Clavicle'), ('R_Shoulder', 'Bip01 R Clavicle'),
    ('L_UpperArm', 'Bip01 L UpperArm'), ('R_UpperArm', 'Bip01 R UpperArm'),
    ('L_Forearm', 'Bip01 L Forearm'), ('R_Forearm', 'Bip01 R Forearm'),
    ('L_Hand', 'Bip01 L Hand'), ('R_Hand', 'Bip01 R Hand'),
    ('L_Thigh', 'Bip01 L Thigh'), ('R_Thigh', 'Bip01 R Thigh'),
    ('L_Calf', 'Bip01 L Calf'), ('R_Calf', 'Bip01 R Calf'),
    ('L_Foot', 'Bip01 L Foot'), ('R_Foot', 'Bip01 R Foot'),
    ('L_Toe', 'Bip01 L Toe0'), ('R_Toe', 'Bip01 R Toe0'),
]


def re8_to_blender(p_m, scale=100.0):
    """RE8 metres -> the converter's Blender arrangement (height in comp 3)."""
    x, y, z = p_m[0] * scale, p_m[1] * scale, p_m[2] * scale
    return np.array([x, -z, y])


P, Q, names = [], [], []
for rb, xb in PAIRS:
    if rb in rose and xb in x4:
        P.append(re8_to_blender(rose[rb]))
        Q.append(x4[xb])
        names.append((rb, xb))
P, Q = np.array(P), np.array(Q)
print("配对 %d 组" % len(P), flush=True)

pc, qc = P.mean(0), Q.mean(0)
P0, Q0 = P - pc, Q - qc
H = P0.T @ Q0
U, S, Vt = np.linalg.svd(H)
d = np.sign(np.linalg.det(Vt.T @ U.T))
R = Vt.T @ np.diag([1, 1, d]) @ U.T
scale = S.sum() / (P0 ** 2).sum()
t = qc - scale * (R @ pc)

print("scale = %.5f" % scale)
print("R =\n%s" % np.round(R, 4))
print("t = %s" % np.round(t, 2))
pred = (scale * (R @ P.T)).T + t
print("\n逐配对残差 (cm):", flush=True)
for (rb, xb), a, b in zip(names, pred, Q):
    print("   %-12s -> %-18s %6.2f" % (rb, xb, np.linalg.norm(a - b)), flush=True)
print("\n平均残差 = %.2f cm" % np.mean([np.linalg.norm(a - b)
                                        for a, b in zip(pred, Q)]), flush=True)

# 看看直接把 RE8 原始顶点映射过去的效果
print("\n关键点投影检查:", flush=True)
for rb, xb in [('Head', 'Bip01 Head'), ('L_Hand', 'Bip01 L Hand')]:
    p = re8_to_blender(rose[rb])
    q = (scale * (R @ p)) + t
    print("   %-10s 映射后 %s   X4 实际 %s" % (
        rb, np.round(q, 1), np.round(x4[xb], 1)), flush=True)
