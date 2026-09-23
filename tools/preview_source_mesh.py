# -*- coding: utf-8 -*-
"""Render a RE8 .mesh straight from source data, as a ground-truth baseline.

    blender -b --factory-startup --python tools/preview_source_mesh.py -- <mesh path> <tag>

No retarget, no decimation, no X4: just the source vertices, UVs, faces and
albedo maps.  Useful when a retargeted part "looks wrong" -- this separates
"the source data really is like that / RE8's shaders added the rest" from
"our pipeline broke it".
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

RE8_TOOLS = r"D:\dsh-mod\re8\tools\RE-Mesh-Editor-main"
RE8_MODELS = r"D:\dsh-mod\re8\output\models\Rose_Adult_ShadowsOfRose"
OUT = r"D:\dsh-x4\work\preview\source"
sys.path.insert(0, RE8_TOOLS)

from modules.mesh.file_re_mesh import readREMesh            # noqa: E402
from modules.mesh.re_mesh_parse import ParsedREMesh         # noqa: E402


def build(mesh_path, tag):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    parsed = ParsedREMesh()
    parsed.ParseREMesh(readREMesh(mesh_path))

    mat_json = json.load(open(os.path.join(
        RE8_MODELS, "Rose_Adult_ShadowsOfRose_materials.json"), encoding='utf-8'))
    defs = mat_json.get('materials', {})
    names = [str(m) for m in parsed.materialNameList]

    made = 0
    for lod in parsed.mainMeshLODList:
        for grp in lod.visconGroupList:
            for si, sm in enumerate(grp.subMeshList):
                mat_name = names[sm.materialIndex] if sm.materialIndex < len(names) else 'm%d' % si
                # RE8 is Y-up metres; Blender wants Z-up
                verts = [(v[0] * 100.0, v[2] * 100.0, v[1] * 100.0)
                         for v in sm.vertexPosList]
                me = bpy.data.meshes.new('%s_%d' % (tag, si))
                me.from_pydata(verts, [], [tuple(f) for f in sm.faceList])
                me.validate(verbose=False)
                uv = me.uv_layers.new(name='UVMap')
                uvl = list(getattr(sm, 'uvList', None) or [])
                for loop in me.loops:
                    if loop.vertex_index < len(uvl):
                        u = uvl[loop.vertex_index]
                        uv.data[loop.index].uv = (u[0], 1.0 - u[1])

                mat = bpy.data.materials.new(mat_name)
                mat.use_nodes = True
                nt = mat.node_tree
                nt.nodes.clear()
                out = nt.nodes.new("ShaderNodeOutputMaterial")
                bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
                nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
                alb = (defs.get(mat_name) or {}).get('albedo')
                if alb:
                    p = os.path.normpath(os.path.join(RE8_MODELS, alb))
                    if os.path.exists(p):
                        tex = nt.nodes.new("ShaderNodeTexImage")
                        tex.image = bpy.data.images.load(p, check_existing=True)
                        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
                me.materials.append(mat)
                ob = bpy.data.objects.new(me.name, me)
                bpy.context.scene.collection.objects.link(ob)
                made += 1
    print('built %d submeshes from %s' % (made, os.path.basename(mesh_path)))

    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    scn.render.resolution_x = 520
    scn.render.resolution_y = 700
    scn.display.shading.light = 'STUDIO'
    scn.display.shading.color_type = 'TEXTURE'
    try:
        scn.display.shading.show_backface_culling = True
    except AttributeError:
        pass

    cd = bpy.data.cameras.new('C')
    cd.type = 'ORTHO'
    cd.ortho_scale = 190
    cam = bpy.data.objects.new('C', cd)
    scn.collection.objects.link(cam)
    scn.camera = cam
    tgt = Vector((0, 0, 90))
    for view, dirv in (('face', (0.10, 1.0, 0.06)), ('side', (1.0, -0.25, 0.08))):
        v = Vector(dirv).normalized()
        cam.location = tgt + v * 500
        cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scn.render.filepath = os.path.join(OUT, '%s_%s.png' % (tag, view))
        bpy.ops.render.render(write_still=True)
    print('SOURCE PREVIEW DONE ->', OUT, tag)


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    os.makedirs(OUT, exist_ok=True)
    build(argv[0], argv[1])
