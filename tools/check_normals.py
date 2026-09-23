# -*- coding: utf-8 -*-
"""Check that a .xac's meshes are wound outwards.

    blender -b --factory-startup --python tools/check_normals.py -- <a.xac> [<b.xac> ...]

Reports, per mesh, the fraction of faces whose normal points away from the
mesh centroid.  A healthy asset sits around 0.8-0.95; a mesh whose triangle
winding got flipped lands near 0.1-0.2 and renders as an inside-out shell --
which in game looks like transparent clothing (you see the far inner surface),
scrambled shading, and a vanished face.

Pass a vanilla asset alongside the mod asset to get a reference column.
This is the check that catches a handedness/reflection mistake in the frame
conversion, which no amount of looking at vertex positions will reveal.
"""
import importlib
import os
import pathlib
import sys

import addon_utils
import bpy
import numpy as np

ADDON = r"D:\dsh-x4\X4CharacterConverter 2152 v0.8.7 2026-06-13T03-09Z QePzPJC03"
ROOT = r"D:\dsh-x4\work\x4root"
sys.path.insert(0, ADDON)


def analyse(xac_path, label):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importlib.import_module("X4CharacterConverter")
    addon_utils.enable("X4CharacterConverter", default_set=True)
    bpy.context.preferences.addons["X4CharacterConverter"].preferences.data_root = ROOT + os.sep
    from X4CharacterConverter import addon as A
    A.import_actor(bpy.context, pathlib.Path(xac_path))

    print('=' * 78)
    print('%s   (%s)' % (label, os.path.basename(xac_path)))
    rows = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.get('x4cc_actor_id'):
            continue
        me = ob.data
        n = len(me.polygons)
        if n < 20 or len(me.vertices) < 20:
            continue
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        centre = co.mean(axis=0)
        cen = np.empty(n * 3)
        nrm = np.empty(n * 3)
        me.polygons.foreach_get('center', cen)
        me.polygons.foreach_get('normal', nrm)
        cen = cen.reshape(-1, 3) - centre
        nrm = nrm.reshape(-1, 3)
        dot = (cen * nrm).sum(axis=1)
        ratio = float((dot > 0).mean())
        rows.append((ratio, ob.name, n))
    for ratio, name, n in sorted(rows):
        flag = ''
        if ratio < 0.45:
            flag = '   <== WOUND INWARDS'
        elif ratio < 0.62:
            # vanilla's own Sneakers/Hands meshes sit at 0.59-0.61: concave
            # shapes (armpits, between fingers, inside a boot) legitimately
            # have inward faces, so this band is "look at it", not "broken"
            flag = '   <-- low (vanilla concave meshes are ~0.59)'
        print('   %-22s faces=%-6d outward=%.3f%s' % (name, n, ratio, flag))
    if rows:
        print('   worst mesh outward ratio: %.3f' % min(r[0] for r in rows))
    return min((r[0] for r in rows), default=1.0)


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    worst = 1.0
    for p in argv:
        worst = min(worst, analyse(p, os.path.basename(p)))
    print()
    # A flipped mesh scores 1 - original, so a healthy 0.55 mesh would land at
    # 0.45; the threshold sits just below that.  Concave meshes legitimately
    # run low (fingers are ~0.49: the gaps between them face inwards, and
    # vanilla's own Hands mesh is only 0.61), so this is a flip detector, not
    # a quality score.
    print('VERDICT: %s (worst outward ratio %.3f)'
          % ('OK' if worst >= 0.45 else 'FAILING - winding flipped', worst))
    if worst < 0.45:
        sys.exit(1)
