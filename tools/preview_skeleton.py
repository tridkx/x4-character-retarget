# -*- coding: utf-8 -*-
"""
Render the skeleton as thin geometry on top of the mesh, so a binding
mismatch is visible instead of inferred.  Also renders the vanilla asset
the same way as a control.
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
import importlib, os, sys
import numpy as np
import bpy, addon_utils, pathlib
from mathutils import Vector

# tools/ 与 work/ 两种深度都恰好再上两层到 dsh-x4（已用断言实测）

ADDON = os.path.join(_X4_SHARED, r"X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03")
ROOT = os.path.join(_X4_SHARED, r"x4root")
OUT = os.path.join(_X4_DEV_ROOT, 'x4-character-retarget', 'work', r"preview\skel")
sys.path.insert(0, ADDON)

TARGETS = [
    (os.path.join(ROOT, r"assets\characters\argon\bodies\char_arg_f_sweater_leggings_civ_01.xac"),
     "vanilla_body"),
    (os.path.join(_X4_DEV_ROOT, 'x4-character-retarget', 'work', r"x4_rose_mod\assets\characters\argon\rose\bodies\rose_body.xac"),
     "rose_body"),
]


def bone_mesh(arm, name):
    """Build a thin octahedron-ish box per bone as its own object."""
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    mw = arm.matrix_world
    R = 1.2                      # 骨骼线框的半径（cm）
    for b in arm.data.bones:
        h = mw @ b.head_local
        t = mw @ b.tail_local
        d = t - h
        L = d.length or 0.1
        # 简单的骨骼柱：在首尾各放一个小立方体
        for p in (h, t):
            bmesh.ops.create_cube(bm, size=R * 2.0,
                                  matrix=__import__('mathutils').Matrix.Translation(p))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def render(xac, tag):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A
    A.import_actor(bpy.context, pathlib.Path(xac))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

    mat_mesh = bpy.data.materials.new("m"); mat_mesh.use_nodes = True
    b = mat_mesh.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs['Base Color'].default_value = (0.55, 0.55, 0.60, 1)
        b.inputs['Alpha'].default_value = 0.35
    mat_mesh.blend_method = 'BLEND'
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            ob.data.materials.clear()
            ob.data.materials.append(mat_mesh)

    bs = bone_mesh(arm, "skel_%s" % tag)
    mat_b = bpy.data.materials.new("b"); mat_b.use_nodes = True
    bb = mat_b.node_tree.nodes.get("Principled BSDF")
    if bb:
        bb.inputs['Base Color'].default_value = (0.9, 0.1, 0.1, 1)
    bs.data.materials.append(mat_b)

    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    scn.render.resolution_x = 620
    scn.render.resolution_y = 820
    try:
        scn.display.shading.light = 'FLAT'
        scn.display.shading.color_type = 'MATERIAL'
        scn.display.shading.show_xray = True
        scn.display.shading.xray_alpha = 0.3
    except Exception as e:
        print("shading:", e)

    cd = bpy.data.cameras.new("C"); cd.type = 'ORTHO'; cd.ortho_scale = 150
    cam = bpy.data.objects.new("C", cd); scn.collection.objects.link(cam); scn.camera = cam

    # 手部特写 + 全身
    shots = [
        ("hand", Vector((40, 0, 105)), 34, (0.75, -0.6, 0.3)),
        ("full", Vector((0, 0, 95)), 200, (0.3, -1, 0.15)),
    ]
    for name, tgt, scale, dirv in shots:
        cd.ortho_scale = scale
        v = Vector(dirv).normalized()
        cam.location = tgt + v * 400
        cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scn.render.filepath = os.path.join(OUT, "%s_%s.png" % (tag, name))
        bpy.ops.render.render(write_still=True)
        print("  shot", tag, name)


os.makedirs(OUT, exist_ok=True)
for xac, tag in TARGETS:
    if os.path.exists(xac):
        render(xac, tag)
print("RENDERED ->", OUT)
