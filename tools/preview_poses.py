# -*- coding: utf-8 -*-
"""
SUPERSEDED by preview_pose_test.py -- kept for the record.

This one still imports the obsolete pose_align module and predates the
coordinate-frame fix, so its poses are mirrored.  Use

    blender -b --factory-startup --python tools/preview_pose_test.py -- <xac|blend> <tag>

which also renders a vanilla reference for comparison.

---

Pose-test preview: drive the X4 armature through a set of test poses and
render Rose's mesh after each, so skinning can be judged offline.

This is the check that matters for "her arms bend the wrong way when she
moves": if the mesh follows the bones correctly here, the same will happen
in game.

    blender -b --factory-startup --python tools/preview_poses.py
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
import math

# --- 项目根自动定位（work 已并入 x4-character-retarget）---
import sys

import numpy as np
import bpy
import addon_utils
import pathlib
from mathutils import Euler, Vector

WORK = os.path.join(_X4_DEV_ROOT, 'work')
ROOT = os.path.join(_X4_SHARED, r"x4root")
ADDON_DIR = os.path.join(_X4_SHARED, r"X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03")
HOST = r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac"
OUT = os.path.join(WORK, "preview", "poses")

sys.path.insert(0, ADDON_DIR)
sys.path.insert(0, os.path.join(WORK, "tools"))
import pose_align  # noqa: E402

SLOTS = {
    'head': [(0, ['face']), (1, ['eyes']), (2, ['hair'])],
    'body': [(0, ['hand_l', 'hand_r']), (1, ['body', 'slingbelt']),
             (2, ['jacket'])],
}


def build(align):
    """Import host skeleton, add Rose meshes, optionally pose-align them."""
    import build_mod
    parts = build_mod.read_part_geometry()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A
    A.import_actor(bpy.context, pathlib.Path(os.path.join(ROOT, HOST)))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

    mw = arm.matrix_world
    x4_bones = {b.name: {'head': tuple(mw @ b.head_local),
                         'tail': tuple(mw @ b.tail_local)}
                for b in arm.data.bones}

    # drop the vanilla meshes
    for ob in list(bpy.data.objects):
        if ob.type == 'MESH':
            bpy.data.objects.remove(ob, do_unlink=True)

    made = []
    for target, entries in SLOTS.items():
        for slot, part_names in entries:
            verts, weights, faces = [], [], []
            for pn in part_names:
                for src in parts.get(pn, []):
                    base = len(verts)
                    verts.extend(src['verts'])
                    weights.extend(src['weights'])
                    faces.extend(tuple(i + base for i in f) for f in src['faces'])
            if not faces:
                continue
            if align:
                verts, _ = pose_align.apply_alignment(verts, weights, x4_bones,
                                                      verbose=False)
            me = bpy.data.meshes.new("rose_%s_%d" % (target, slot))
            me.from_pydata([tuple(v) for v in verts], [], faces)
            me.validate(verbose=False)
            me.update()
            ob = bpy.data.objects.new("rose_%s_%d" % (target, slot), me)
            bpy.context.scene.collection.objects.link(ob)

            grp = {}
            for vi, wd in enumerate(weights):
                for gn, gv in wd.items():
                    g = grp.get(gn)
                    if g is None:
                        g = ob.vertex_groups.new(name=gn)
                        grp[gn] = g
                    g.add([vi], gv, 'REPLACE')
            ob.parent = arm
            mod = ob.modifiers.new(name="Armature", type='ARMATURE')
            mod.object = arm
            made.append(ob)

    mat = bpy.data.materials.new("prev")
    mat.use_nodes = True
    b = mat.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs['Base Color'].default_value = (0.60, 0.54, 0.50, 1.0)
    for ob in made:
        ob.data.materials.clear()
        ob.data.materials.append(mat)
    return arm, made


# --------------------------------------------------------------------------
# test poses: (name, [(bone, axis, degrees), ...])
# --------------------------------------------------------------------------
POSES = [
    ("p1_bind", []),
    ("p2_armdown", [('Bip01 L UpperArm', 'Y', -35), ('Bip01 R UpperArm', 'Y', 35)]),
    ("p3_armfwd", [('Bip01 L UpperArm', 'X', -45), ('Bip01 R UpperArm', 'X', -45)]),
    ("p4_elbow", [('Bip01 L Forearm', 'Y', -70), ('Bip01 R Forearm', 'Y', 70)]),
    ("p5_fingers", [('Bip01 L Finger1', 'Y', -50), ('Bip01 L Finger11', 'Y', -60),
                    ('Bip01 L Finger2', 'Y', -50), ('Bip01 L Finger21', 'Y', -60),
                    ('Bip01 R Finger1', 'Y', 50), ('Bip01 R Finger11', 'Y', 60),
                    ('Bip01 R Finger2', 'Y', 50), ('Bip01 R Finger21', 'Y', 60)]),
    ("p6_headturn", [('Bip01 Head', 'Z', 40), ('Bip01 Neck', 'Z', 20)]),
]


def clear_pose(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = Euler((0, 0, 0), 'XYZ')
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)


def setup_scene():
    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    scn.render.resolution_x = 480
    scn.render.resolution_y = 800
    try:
        scn.display.shading.light = 'STUDIO'
        scn.display.shading.color_type = 'SINGLE'
        scn.display.shading.single_color = (0.72, 0.66, 0.62)
        scn.display.shading.show_shadows = True
    except Exception:
        pass
    cd = bpy.data.cameras.new("Cam")
    cd.type = 'ORTHO'
    cd.ortho_scale = 200
    cam = bpy.data.objects.new("Cam", cd)
    scn.collection.objects.link(cam)
    scn.camera = cam
    return cam


def shoot(cam, name, view):
    tgt = Vector((0, 0, 100))
    v = Vector(view).normalized()
    cam.location = tgt + v * 430
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    views = {'front': (0, -1, 0.05), 'top': (0, 0.02, 1)}

    for align in (False, True):
        arm, made = build(align)
        cam = setup_scene()
        tag = "align" if align else "raw"
        for pname, rots in POSES:
            clear_pose(arm)
            for bone, axis, deg in rots:
                pb = arm.pose.bones.get(bone)
                if pb is None:
                    continue
                e = [0.0, 0.0, 0.0]
                e['XYZ'.index(axis)] = math.radians(deg)
                pb.rotation_mode = 'XYZ'
                pb.rotation_euler = Euler(e, 'XYZ')
            bpy.context.view_layer.update()
            for vname, vdir in views.items():
                shoot(cam, "%s_%s_%s" % (tag, pname, vname), vdir)
        print("done", tag, "objs", len(made))

    print("RENDERED ->", OUT)


main()
