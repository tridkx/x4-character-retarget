# -*- coding: utf-8 -*-
"""Extract vertex positions + skin weights from a RE Engine .mesh file.

Uses the RE-Mesh-Editor parser bundled with the user's re8 project.
"""
import os, sys, json, struct

REMESH = r"D:\dsh-mod\re8\tools\RE-Mesh-Editor-main"
if REMESH not in sys.path:
    sys.path.insert(0, REMESH)

from modules.mesh.file_re_mesh import readREMesh           # noqa: E402
from modules.mesh.re_mesh_parse import ParsedREMesh        # noqa: E402


def load(path):
    raw = readREMesh(path)
    parsed = ParsedREMesh()
    parsed.ParseREMesh(raw)
    return parsed


def summarize(parsed, path):
    print('=' * 74)
    print(os.path.basename(path))
    skel = parsed.skeleton
    print('  bones        :', len(skel.boneList) if skel else 0)
    print('  weightedBones:', len(skel.weightedBones) if skel else 0)
    print('  LODs         :', len(parsed.mainMeshLODList))
    print('  has weight buf:', parsed.bufferHasWeight)
    if not parsed.mainMeshLODList:
        return
    lod = parsed.mainMeshLODList[0]
    groups = lod.visconGroupList
    print('  viscon groups:', len(groups))
    tot_v = tot_f = 0
    subs = []
    for g in groups:
        for sm in g.subMeshList:
            subs.append(sm)
            tot_v += len(sm.vertexPosList)
            tot_f += len(sm.faceList)
    print('  total verts  :', tot_v, ' faces:', tot_f, ' submeshes:', len(subs))
    if not subs:
        return
    sm = subs[0]
    print('  sm0 verts=%d faces=%d mat=%s' % (len(sm.vertexPosList), len(sm.faceList), sm.materialIndex))
    wl, wi = sm.weightList, sm.weightIndicesList
    print('  weightList len=%d  weightIndicesList len=%d' % (len(wl), len(wi)))
    if wl:
        print('  weightList[0]        =', wl[0])
        print('  weightIndicesList[0] =', wi[0])
        print('  weightList[5]        =', wl[5])
        print('  weightIndicesList[5] =', wi[5])
    if skel:
        print('  weightedBones[:8]:', skel.weightedBones[:8])


if __name__ == '__main__':
    base = r"D:\dsh-mod\re8\output\raw_natives\natives\stm\_ge\character\ch\ch01\6000"
    for rel in ['6000/ch01_6000_body.mesh.2101050001',
                '6020/ch01_6020_rose_face.mesh.2101050001']:
        p = os.path.join(base, rel.replace('/', os.sep))
        if not os.path.exists(p):
            print('MISSING', p)
            continue
        try:
            summarize(load(p), p)
        except Exception as e:
            import traceback
            traceback.print_exc()
