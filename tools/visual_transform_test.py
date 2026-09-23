# -*- coding: utf-8 -*-
"""
Render the skeleton inside the mesh for each candidate transform, so the
correct one is identified by eye rather than by a metric that may itself be
measuring the wrong thing.
"""
import importlib, os, sys
import numpy as np
import bpy, addon_utils, bmesh, pathlib
from mathutils import Matrix
WORK = r"D:\dsh-x4\work"
ADDON = r"D:\dsh-x4\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
ROOT = os.path.join(WORK, "x4root")
OUT = os.path.join(WORK, "preview", "vistest")
sys.path.insert(0, ADDON)
sys.path.insert(0, os.path.join(WORK, "tools"))

CASES = {
    'A_as_is':   lambda v: (v[0], v[1], v[2]),
    'B_negY':    lambda v: (v[0], -v[1], v[2]),
    'C_negZ':    lambda v: (v[0], v[1], -v[2]),
    'D_xzy':     lambda v: (v[0], v[2], v[1]),
    'E_xnzyn':   lambda v: (v[0], -v[2], v[1]),
}


def stage1_parts():
    bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, "rose_x4_stage1.blend"))
    parts = {}
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        p = ob.get('x4cc_part')
        if not p:
            continue
        gname = {g.index: g.name for g in ob.vertex_groups}
        W = []
        for v in ob.data.vertices:
            d = {}
            for ge in v.groups:
                if ge.weight > 1e-6:
                    d[gname[ge.group]] = d.get(gname[ge.group], 0.0) + ge.weight
            W.append(d)
        parts.setdefault(p, []).append({
            'verts': [tuple(v.co) for v in ob.data.vertices],
            'weights': W,
            'faces': [tuple(p2.vertices) for p2 in ob.data.polygons]})
    return parts


parts = stage1_parts()
os.makedirs(OUT, exist_ok=True)

for tag, xf in CASES.items():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A
    A.import_actor(bpy.context, pathlib.Path(os.path.join(
        ROOT, r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac")))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    for ob in list(bpy.data.objects):
        if ob.type == 'MESH':
            bpy.data.objects.remove(ob, do_unlink=True)

    # mesh (only body+hands so the silhouette is clear)
    for pn in ('body', 'hand_l', 'hand_r'):
        for src in parts.get(pn, []):
            vs = [xf(v) for v in src['verts']]
            me = bpy.data.meshes.new("m_%s" % pn)
            me.from_pydata(vs, [], src['faces'])
            me.validate(verbose=False); me.update()
            ob = bpy.data.objects.new("m_%s" % pn, me)
            bpy.context.scene.collection.objects.link(ob)
            ob.parent = arm
            mod = ob.modifiers.new("A", 'ARMATURE'); mod.object = arm
            grp = {}
            for vi, wd in enumerate(src['weights']):
                for gn, gv in wd.items():
                    g = grp.get(gn)
                    if g is None:
                        g = ob.vertex_groups.new(name=gn); grp[gn] = g
                    g.add([vi], gv, 'REPLACE')

    # skeleton as boxes
    me = bpy.data.meshes.new("skel")
    bm = bmesh.new()
    mw = arm.matrix_world
    for b in arm.data.bones:
        h = mw @ b.head_local; t = mw @ b.tail_local
        n = max(1, int((t - h).length / 4))
        for k in range(n + 1):
            bmesh.ops.create_cube(bm, size=2.0,
                                  matrix=Matrix.Translation(h.lerp(t, k / n)))
    bm.to_mesh(me); bm.free()
    sk = bpy.data.objects.new("skel", me)
    bpy.context.scene.collection.objects.link(sk)

    mm = bpy.data.materials.new("m"); mm.use_nodes = True
    bs = mm.node_tree.nodes.get("Principled BSDF")
    if bs:
        bs.inputs['Base Color'].default_value = (0.6, 0.6, 0.65, 1)
        bs.inputs['Alpha'].default_value = 0.30
    mm.blend_method = 'BLEND'
    mb = bpy.data.materials.new("b"); mb.use_nodes = True
    bb = mb.node_tree.nodes.get("Principled BSDF")
    if bb:
        bb.inputs['Base Color'].default_value = (0.95, 0.1, 0.1, 1)
    for o in bpy.context.scene.collection.objects:
        if o.type == 'MESH':
            o.data.materials.clear()
            o.data.materials.append(mb if o.name == 'skel' else mm)

    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    scn.render.resolution_x = 520; scn.render.resolution_y = 700
    try:
        scn.display.shading.light = 'FLAT'
        scn.display.shading.color_type = 'MATERIAL'
        scn.display.shading.show_xray = True
        scn.display.shading.xray_alpha = 0.25
    except Exception:
        pass
    cd = bpy.data.cameras.new("C"); cd.type = 'ORTHO'; cd.ortho_scale = 190
    cam = bpy.data.objects.new("C", cd); scn.collection.objects.link(cam); scn.camera = cam
    tgt = __import__('mathutils').Vector((0, 0, 95))
    v = __import__('mathutils').Vector((0.2, -1, 0.1)).normalized()
    cam.location = tgt + v * 500
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scn.render.filepath = os.path.join(OUT, tag + ".png")
    bpy.ops.render.render(write_still=True)
    print("rendered", tag, flush=True)

print("OUT ->", OUT)
