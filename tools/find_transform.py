# -*- coding: utf-8 -*-
"""
Find the correct coordinate transform by EMPIRICAL TEST, not derivation.

For each candidate transform T:
  1. stage1 vertices (already in whatever frame re8_to_x4 produced) are mapped
     with T and written into a Blender mesh, exactly as build_mod.fill_slot does
  2. the same mesh is exported through the converter's own packer
  3. the result is re-imported and the hand mesh centre is compared with the
     Bip01 L Hand bone in the SAME imported scene

Metric: distance between hand mesh centroid and its driving bone.
Vanilla assets score ~2 cm.
"""
import importlib, itertools, os, sys
import numpy as np
import bpy, addon_utils, pathlib
WORK = r"D:\dsh-x4\work"
ADDON = r"D:\dsh-x4\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
ROOT = os.path.join(WORK, "x4root")
sys.path.insert(0, ADDON)
sys.path.insert(0, os.path.join(WORK, "tools"))

HOST = os.path.join(ROOT, r"assets\characters\argon\heads\char_arg_f_dyn_blend_head.xac")
STAGE1 = os.path.join(WORK, "rose_x4_stage1.blend")


def load_stage1_hand():
    """Hand vertices as stored in stage1 (no extra transform)."""
    bpy.ops.wm.open_mainfile(filepath=STAGE1)
    verts, weights, faces = [], [], []
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        if ob.get('x4cc_part') not in ('hand_l', 'hand_r'):
            continue
        gname = {g.index: g.name for g in ob.vertex_groups}
        base = len(verts)
        verts.extend([tuple(v.co) for v in ob.data.vertices])
        for v in ob.data.vertices:
            wd = {}
            for ge in v.groups:
                if ge.weight > 1e-6:
                    wd[gname[ge.group]] = wd.get(gname[ge.group], 0.0) + ge.weight
            weights.append(wd)
        faces.extend(tuple(i + base for i in p.vertices) for p in ob.data.polygons)
    return verts, weights, faces


def bone_dist(verts, weights, faces):
    """After building + exporting + reimporting, measure bone/mesh distance."""
    # build the mesh exactly like fill_slot does, with transform already applied
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    prefs = bpy.context.preferences.addons["X4CharacterConverter"].preferences
    prefs.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A
    pkg_dir = os.path.join(WORK, "x4cc_find")
    if os.path.isdir(pkg_dir):
        import shutil
        shutil.rmtree(pkg_dir)
    os.makedirs(pkg_dir)

    A.import_actor(bpy.context, pathlib.Path(HOST))
    host_ob = None
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.get('x4cc_mesh_id') == 1:
            host_ob = ob
    if host_ob is None:
        return None
    me = bpy.data.meshes.new("probe")
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate(verbose=False)
    me.update()
    if not me.uv_layers:
        uv = me.uv_layers.new(name="UVMap")
        for loop in me.loops:
            uv.data[loop.index].uv = (0.0, 0.0)
    host_ob.data = me
    host_ob.name = "rose_body_torso"
    for g in list(host_ob.vertex_groups):
        host_ob.vertex_groups.remove(g)
    grp = {}
    for vi, wd in enumerate(weights):
        for gn, gv in wd.items():
            g = grp.get(gn)
            if g is None:
                g = host_ob.vertex_groups.new(name=gn)
                grp[gn] = g
            g.add([vi], gv, 'REPLACE')
    # the packer refuses materials without a Diffuse image node; reuse an
    # already-converted dds (Blender's python has no PIL)
    import glob
    found = sorted(glob.glob(os.path.join(WORK, "tex_out", "mats", "*_diff.dds")))
    if not found:
        return ("NO-TEX", "run prepare_textures.py first")
    mat = bpy.data.materials.new("rose.probe")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out_n = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out_n.inputs["Surface"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(found[0], check_existing=True)
    tex.name = "Diffuse"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    me.materials.append(mat)
    for ob in list(bpy.data.objects):
        if ob.type == 'MESH' and ob is not host_ob:
            bpy.data.objects.remove(ob, do_unlink=True)

    try:
        A.export_package(bpy.context, pathlib.Path(os.path.join(pkg_dir, "probe")))
    except Exception as exc:
        return ("EXPORT-FAIL", str(exc)[:60])

    # re-import and measure
    out = os.path.join(pkg_dir, "probe", "assets", "characters",
                       "mycharacters", "bodies", "probe.xac")
    if not os.path.exists(out):
        return ("NO-XAC", "")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("X4CharacterConverter", default_set=True)
    prefs = bpy.context.preferences.addons["X4CharacterConverter"].preferences
    prefs.data_root = ROOT + os.sep
    A.import_actor(bpy.context, pathlib.Path(out))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    B = {b.name: (np.array(list(b.head_local)), np.array(list(b.tail_local)))
         for b in arm.data.bones}
    # per-vertex distance to the bone that dominates it == skinning error.
    # vanilla assets score ~1.9 cm; that is the target.
    best = None
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
            ab = t - h
            L2 = float(ab @ ab) or 1.0
            p = np.array(list(v.co))
            u = max(0.0, min(1.0, float((p - h) @ ab) / L2))
            tot += float(np.linalg.norm(p - (h + ab * u)))
            n += 1
        if n:
            best = tot / n
    return best

def main():
    V, W, F = load_stage1_hand()
    print("stage1 hand verts:", len(V), flush=True)
    cands = {
        'as_is':        lambda v: (v[0], v[1], v[2]),
        '(x,-z,y)':     lambda v: (v[0], -v[2], v[1]),
        '(x,z,-y)':     lambda v: (v[0], v[2], -v[1]),
        '(x,-y,-z)':    lambda v: (v[0], -v[1], -v[2]),
        '(x,y,-z)':     lambda v: (v[0], v[1], -v[2]),
        '(x,-y,z)':     lambda v: (v[0], -v[1], v[2]),
    }
    for name, f in cands.items():
        vv = [f(v) for v in V]
        r = bone_dist(vv, W, F)
        if isinstance(r, tuple):
            print("   %-12s %s" % (name, r), flush=True)
        else:
            print("   %-12s 逐顶点蒙皮误差 = %s cm   (原版基准 1.86)" % (
                name, "None" if r is None else "%.2f" % r), flush=True)


main()
