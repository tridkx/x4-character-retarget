# -*- coding: utf-8 -*-
"""Render a .xac under a few test poses, so skin binding can be judged the way
the game will use it (bones rotating, mesh following) instead of at rest.

    blender -b --factory-startup --python tools/preview_pose_test.py -- <xac> <tag>

Each shot rotates one joint chain about its own joint and renders a side and a
front view.  A mesh whose weights landed on the wrong bone tears or swings the
wrong way here, which is exactly the in-game symptom.
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
import pathlib
import sys

import addon_utils
import bpy
from mathutils import Matrix, Vector

ADDON = os.path.join(_X4_SHARED, r"X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03")

#: set by the optional third argv: render with diffuse textures instead of a
#: flat material colour
TEXTURE_MODE = False
ROOT = os.path.join(_X4_SHARED, r"x4root")
OUT = os.path.join(_X4_DEV_ROOT, 'work')
sys.path.insert(0, ADDON)

#: pose name -> [(bone, world axis, degrees)]
#: pose name -> [(bone, world axis, degrees)].
#: +y is the character's forward axis in X4 assets, so an elbow bends with a
#: POSITIVE rotation about +x (forearm swings forward) and a knee with a
#: NEGATIVE one (shin swings back).  Getting these backwards renders a
#: correctly bound mesh as if its limbs bent the wrong way.
POSES = {
    'rest':   [],
    'elbow':  [('Bip01 L Forearm', (1, 0, 0), 100),
               ('Bip01 R Forearm', (1, 0, 0), 100)],
    'knee':   [('Bip01 L Calf', (1, 0, 0), -90),
               ('Bip01 R Calf', (1, 0, 0), -90)],
    'walk':   [('Bip01 L Thigh', (1, 0, 0), -30),
               ('Bip01 L Calf', (1, 0, 0), -25),
               ('Bip01 R Thigh', (1, 0, 0), 25),
               ('Bip01 R Forearm', (1, 0, 0), 35)],
    'armsup': [('Bip01 L UpperArm', (0, 1, 0), -60),
               ('Bip01 R UpperArm', (0, 1, 0), 60)],
    'twist':  [('Bip01 Spine1', (0, 0, 1), 35),
               ('Bip01 Head', (0, 0, 1), 40)],
}


def rotate_about_joint(arm, bone_name, axis, degrees):
    """Rotate a bone (and its chain) about its own head, in world axes."""
    pb = arm.pose.bones.get(bone_name)
    if pb is None:
        print('   !! no bone', bone_name)
        return
    head = pb.matrix.translation.copy()
    R = Matrix.Rotation(math.radians(degrees), 4, Vector(axis))
    pb.matrix = (Matrix.Translation(head) @ R
                 @ Matrix.Translation(-head) @ pb.matrix)
    bpy.context.view_layer.update()


def render(xac_path, tag):
    if xac_path.lower().endswith('.blend'):
        # stage-1 scene: meshes are already parented and weighted
        bpy.ops.wm.open_mainfile(filepath=xac_path)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        importlib.import_module("X4CharacterConverter")
        addon_utils.enable("X4CharacterConverter", default_set=True)
        bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
        from X4CharacterConverter import addon as A
        A.import_actor(bpy.context, pathlib.Path(xac_path))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

    if not TEXTURE_MODE:
        mat = bpy.data.materials.new("m")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs['Base Color'].default_value = (0.62, 0.60, 0.58, 1)
        for ob in bpy.data.objects:
            if ob.type == 'MESH' and ob.get('x4cc_actor_id'):
                ob.data.materials.clear()
                ob.data.materials.append(mat)

    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    scn.render.resolution_x = 520
    scn.render.resolution_y = 700
    scn.display.shading.light = 'STUDIO'
    # 'TEXTURE' shows the real diffuse maps (the converter resolves them
    # relative to the add-on's data root, so the mod tree must be reachable
    # from there); otherwise flat material colour.
    scn.display.shading.color_type = TEXTURE_MODE and 'TEXTURE' or 'MATERIAL'
    scn.display.shading.show_shadows = False
    # Backface culling on: this is what turns a flipped triangle winding into
    # the in-game "transparent clothes / missing face" symptom, so the preview
    # has to reproduce it rather than hide it behind two-sided shading.
    try:
        scn.display.shading.show_backface_culling = True
    except AttributeError:
        pass

    cd = bpy.data.cameras.new("C")
    cd.type = 'ORTHO'
    cam = bpy.data.objects.new("C", cd)
    scn.collection.objects.link(cam)
    scn.camera = cam

    for pose_name, ops in POSES.items():
        for pb in arm.pose.bones:          # reset
            pb.matrix_basis.identity()
        bpy.context.view_layer.update()
        for bone, axis, deg in ops:
            rotate_about_joint(arm, bone, axis, deg)

        for view, dirv, scale in (('side', (1.0, -0.25, 0.08), 190),
                                  ('back', (0.15, -1.0, 0.05), 190),
                                  ('face', (0.10, 1.0, 0.06), 190)):
            cd.ortho_scale = scale
            tgt = Vector((0, 0, 90))
            v = Vector(dirv).normalized()
            cam.location = tgt + v * 500
            cam.rotation_euler = (tgt - cam.location).to_track_quat(
                '-Z', 'Y').to_euler()
            scn.render.filepath = os.path.join(
                OUT, "%s_%s_%s.png" % (tag, pose_name, view))
            bpy.ops.render.render(write_still=True)
    print("POSETEST DONE ->", OUT, tag)


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    os.makedirs(OUT, exist_ok=True)
    if len(argv) > 2 and argv[2] == 'tex':
        globals()['TEXTURE_MODE'] = True
    render(argv[0], argv[1])
