# -*- coding: utf-8 -*-
"""
Prepare all DDS textures + the material manifest for the Rose mod.

Runs under the *system* Python (Blender's bundled Python has no PIL), then
`build_mod.py` consumes the manifest inside Blender.

    python tools/prepare_textures.py
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

# --- 项目根自动定位（work 已并入 x4-character-retarget）---
import os
import json

# --- 项目根自动定位（work 已并入 x4-character-retarget）---
import re
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bc_encode          # noqa: E402
import tex_convert        # noqa: E402

WORK = os.path.join(_X4_DEV_ROOT, 'work')
RE8_MODELS = r"D:\dsh-mod\re8\output\models\Rose_Adult_ShadowsOfRose"
RE8_RAW = r"D:\dsh-mod\re8\output\raw_natives\natives\stm\_ge\character\ch\ch01\6000"
STAGE1_PARTS = os.path.join(WORK, "stage1_parts.json")

#: meshes whose UVs decide what a shared albedo atlas actually looks like on
#: each material (only needed to derive colours for albedo-less materials)
PARTS = [
    (r"6000\ch01_6000_body.mesh.2101050001",      "ch01_6000_body_skeleton.json"),
    (r"6001\ch01_6001_jacket.mesh.2101050001",    "ch01_6001_jacket_skeleton.json"),
    (r"6004\ch01_6004_slingbelt.mesh.2101050001", "ch01_6004_slingbelt_skeleton.json"),
    (r"6020\ch01_6020_rose_face.mesh.2101050001", "ch01_6020_rose_face_skeleton.json"),
    (r"6030\ch01_6030_rose_eyes.mesh.2101050001", "ch01_6030_rose_eyes_skeleton.json"),
    (r"6040\ch01_6040_hair.mesh.2101050001",      "ch01_6040_hair_skeleton.json"),
    (r"6050\ch01_6050_hand_r.mesh.2101050001",    "ch01_6050_hand_r_skeleton.json"),
    (r"6060\ch01_6060_hand_l.mesh.2101050001",    "ch01_6060_hand_l_skeleton.json"),
]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"D:\dsh-mod\re8\tools\RE-Mesh-Editor-main")
DDS_DIR = os.path.join(WORK, "tex_out", "mats")
TMP_DIR = os.path.join(WORK, "tex_out", "tmp")

COLLECTION = 'rose'

#: materials whose diffuse must keep alpha (BC3 instead of BC1)
#: 'shader_eyes_shader' is deliberately absent: the eyeball's albedo is
#: plain RGB (no alpha), and tagging it ALPHA1 made the eye render as a
#: transparent/blank sphere.
ALPHA_MATS = {'Sling_Mat', 'Hair_Mat', 'Stray_Hair_Mat', 'eyelashes_Mat'}

#: Placeholder base colours, only for materials the automatic rule cannot
#: derive (they have no base material whose albedo could be sampled).
#:
#: The `*_Stitch_Mat` family used to be listed here with hand-picked dark
#: values, which was wrong: those submeshes are not thin decorative lines, they
#: are large patches of the garment (Jacket_Stitch_Mat alone is 3799 of the
#: jacket's 33741 vertices, with tiling UVs far outside 0..1).  Painting them a
#: flat dark grey put dark slabs across an olive jacket -- the "random line at
#: the waist, wrong colours" report.  They are now derived from the material
#: they sit on; see `material_mean_colours()`.
PLACEHOLDER_RGB = {
    'boa_mat_01': (238, 236, 228),
    'boa_mat_02': (238, 236, 228),
    'boa_mat_03': (238, 236, 228),
    'boa_mat_04': (238, 236, 228),
    'shader_eyeslens_shader': (20, 20, 24),
    'eyewet_mat': (235, 235, 238),
    'eyebrow_mat': (78, 56, 42),
    'eyelens_mat': (18, 18, 20),
}
DEFAULT_PLACEHOLDER = (200, 200, 200)

#: `Jacket_Stitch_Mat` -> `Jacket_Mat`: a material that shares another one's
#: surface and therefore has to borrow its colour *and* its roughness
BASE_MAT_RE = re.compile(r'_(?:stitch|base|detail|decal)_mat$', re.I)

#: materials whose name does not encode what they sit on.  `Metal_Mat` is the
#: parka's card geometry (7776 vertices of loose quads laid over the jacket);
#: sampling the atlas through its own tiling UVs yields pale brown (117,108,92)
#: against the jacket's (80,75,66), which is the pale patch across the waist.
SHARED_SURFACE = {
    'metal_mat': 'Jacket_Mat',
    # The zip backing is card geometry too: its UVs land on a magenta patch of
    # the upper-body atlas, so it renders as bright pink chips on the seams
    # (reported in game as "a pink thing under the hat" -- the seams run up to
    # the shoulder).  Give it the coat's colour and keep its normal/roughness.
    'jacket_zipper_base_mat': 'Jacket_Mat',
}

#: see tex_convert.MAX_TEXTURE_SIZE
MAX_SIZE = 1024

#: Flat placeholder maps only need to carry one colour.  Keep them small --
#: at 1024 they added 35 MB to the package for no visual gain.  (The magenta
#: chips that were blamed on a small map turned out to be the BC3 block-order
#: bug, so there is no reason to inflate these.)
PLACEHOLDER_SIZE = 128


def local_name(re8_name):
    s = re8_name.lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    return re.sub(r'_+', '_', s).strip('_')


def full_name(re8_name):
    return '%s.%s' % (COLLECTION, local_name(re8_name))


#: RE8 builds the eye from two textures: a light base (`_eyes_albd`) plus a
#: near-black iris/pupil layer (`_eyeao_albd`).  X4's material only reads one
#: diffuse map, so the iris layer is multiplied in, otherwise the eye renders
#: as a blank pale ball.
EYE_AO_BY_ALBEDO = {
    'ch01_6030_rose_eyes_albd.png': 'ch01_6000_rose_eyeao_albd.png',
    'ch09_0130_rose_eyes_albd.png': 'ch09_0120_rose_eyeao_albd.png',
}


def merge_eye_ao(albedo_path):
    """Multiply the iris/pupil layer into an eye albedo.  Returns a temp PNG."""
    name = os.path.basename(albedo_path)
    ao_name = EYE_AO_BY_ALBEDO.get(name)
    if not ao_name:
        return albedo_path
    ao_path = os.path.join(os.path.dirname(albedo_path), ao_name)
    if not os.path.exists(ao_path):
        print('    (eye AO missing: %s)' % ao_name)
        return albedo_path

    base = Image.open(albedo_path).convert('RGB')
    ao = Image.open(ao_path).convert('RGB').resize(base.size, Image.LANCZOS)
    out = np.asarray(base, np.float32) * (np.asarray(ao, np.float32) / 255.0)
    dst = os.path.join(TMP_DIR, 'eye_%s' % name)
    os.makedirs(TMP_DIR, exist_ok=True)
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(dst)
    return dst


def write_placeholder(path, rgb, alpha=False, size=128):
    arr = np.zeros((size, size, 3), np.uint8)
    arr[:, :] = rgb
    if alpha:
        img = Image.fromarray(np.dstack(
            [arr, np.full((size, size), 255, np.uint8)]), 'RGBA')
        bc_encode.encode_bc3(img, path)
    else:
        bc_encode.encode_bc1(Image.fromarray(arr, 'RGB'), path)
    return path


def used_materials():
    """Material names actually referenced by stage1 geometry."""
    if os.path.exists(STAGE1_PARTS):
        return json.load(open(STAGE1_PARTS, encoding='utf-8'))
    raise RuntimeError(
        'stage1_parts.json missing -- run tools/dump_parts.py in Blender first')


# --------------------------------------------------------------------------
# colours for materials that have no albedo of their own
# --------------------------------------------------------------------------

def material_mean_colours(mat_defs):
    """{material: mean RGB actually sampled through that submesh's UVs}.

    Sampling rather than averaging the whole texture matters: RE8 packs every
    upper-body material into one atlas, so a whole-image average would be
    pulled around by the jeans, skin and boots that share it.
    """
    try:
        import re_mesh_weights as RMW
    except Exception as exc:                              # noqa: BLE001
        print('  (mesh reader unavailable, using flat placeholders: %s)' % exc)
        return {}

    sums = {}
    for mesh_rel, _skel in PARTS:
        path = os.path.join(RE8_RAW, mesh_rel)
        if not os.path.exists(path):
            continue
        try:
            parsed = RMW.load(path)
        except Exception as exc:                          # noqa: BLE001
            print('  (cannot read %s: %s)' % (os.path.basename(path), exc))
            continue
        names = [str(m) for m in parsed.materialNameList]
        for lod in parsed.mainMeshLODList:
            for grp in lod.visconGroupList:
                for sm in grp.subMeshList:
                    if sm.materialIndex >= len(names):
                        continue
                    mat = names[sm.materialIndex]
                    alb = (mat_defs.get(mat) or {}).get('albedo')
                    uvs = list(getattr(sm, 'uvList', None) or [])
                    if not alb or not uvs:
                        continue
                    png = os.path.normpath(os.path.join(RE8_MODELS, alb))
                    if not os.path.exists(png):
                        continue
                    img = Image.open(png).convert('RGB')
                    arr = np.asarray(img)
                    h, w = arr.shape[:2]
                    uv = np.asarray(uvs, np.float32) % 1.0
                    px = np.clip((uv[:, 0] * (w - 1)).astype(int), 0, w - 1)
                    py = np.clip((uv[:, 1] * (h - 1)).astype(int), 0, h - 1)
                    cols = arr[py, px].astype(np.float32)
                    acc = sums.setdefault(mat, [np.zeros(3), 0])
                    acc[0] += cols.sum(axis=0)
                    acc[1] += len(cols)
    return {k: tuple(int(round(c)) for c in (v[0] / max(1, v[1])))
            for k, v in sums.items()}


def base_material_name(re8_name):
    """The material whose surface `re8_name` sits on, or None."""
    hit = SHARED_SURFACE.get(local_name(re8_name))
    if hit:
        return hit
    m = BASE_MAT_RE.search(re8_name)
    if not m:
        return None
    stem = re8_name[:m.start()]
    return '%s_Mat' % stem


def base_material_colour(re8_name, derived):
    """Colour for a material that has no albedo: its base material's colour."""
    cand = base_material_name(re8_name)
    if cand and cand in derived:
        return derived[cand]
    return None


def base_material_smoothness(re8_name, mat_defs):
    """Mean smoothness of the material `re8_name` sits on, or None.

    Matters because the exporter writes a default `Smoothness = 0.5` when a
    material has no smoothness map, while the parka's own map averages 0.08.
    Those overlay strips (placket, waist trim, cuffs) then read as shiny bands
    on a matte coat -- the "random bright line at the waist".
    """
    cand = base_material_name(re8_name)
    if not cand:
        return None
    nrmr = (mat_defs.get(cand) or {}).get('normalRoughness')
    if not nrmr:
        return None
    png = os.path.normpath(os.path.join(RE8_MODELS, nrmr))
    if not os.path.exists(png):
        return None
    img = Image.open(png)
    if img.mode not in ('RGBA', 'LA'):
        return None
    rough = np.asarray(img.convert('RGBA'))[..., 3].astype(np.float32) / 255.0
    return float(1.0 - rough.mean())


def write_smoothness_placeholder(path, value, size=128):
    """Flat BC4 smoothness map of a single value (0..1)."""
    v = int(round(max(0.0, min(1.0, value)) * 255))
    arr = np.full((size, size, 3), v, np.uint8)
    bc_encode.encode_bc4(Image.fromarray(arr, 'RGB'), path)
    return path


def main():
    os.makedirs(DDS_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)

    mat_defs = json.load(open(os.path.join(
        RE8_MODELS, "Rose_Adult_ShadowsOfRose_materials.json"),
        encoding='utf-8'))['materials']
    names = used_materials()

    derived = material_mean_colours(mat_defs)
    if derived:
        print('sampled %d material colours through their own UVs' % len(derived))

    manifest = {}
    for re8_name in sorted(names):
        info = mat_defs.get(re8_name, {})
        x4_full = full_name(re8_name)
        safe = x4_full.replace('.', '_')
        alpha = re8_name in ALPHA_MATS

        # NOTE: do not fold `_eyeao_albd` into the eye albedo.  That texture is
        # uniformly near-black (mean (24,4,0), max 24, no bright pixels) -- a
        # shader parameter map, not a detail layer -- so multiplying it in
        # renders the whole eyeball black.
        try:
            produced = tex_convert.convert_material_textures(
                x4_full, info, RE8_MODELS, DDS_DIR, TMP_DIR,
                needs_alpha=alpha, verbose=False, max_size=MAX_SIZE)
        except Exception as exc:                       # noqa: BLE001
            print('  !! %-24s texture conversion failed: %s' % (re8_name, exc))
            produced = {}

        shared = SHARED_SURFACE.get(local_name(re8_name))
        if shared and shared in derived:
            # Card geometry lying on another material.  A flat colour is the
            # only thing that works here: sampling the base material's atlas
            # through these UVs lands on dark patches (the jacket's dark
            # vertical stripes) or on the atlas padding, and a small solid map
            # is rejected outright.  Colour comes from the base material's own
            # UV-sampled mean, at the same size/format as a real texture.
            ph = os.path.join(DDS_DIR, '%s_diff.dds' % safe)
            write_placeholder(ph, derived[shared], alpha=alpha, size=PLACEHOLDER_SIZE)
            produced['Diffuse'] = ph
            print('  %-26s flat Diffuse %-16s (overlay on %s, %dpx)'
                  % (re8_name, str(derived[shared]), shared, MAX_SIZE))

        if 'Diffuse' not in produced:
            ph = os.path.join(DDS_DIR, '%s_diff.dds' % safe)
            rgb = PLACEHOLDER_RGB.get(local_name(re8_name))
            source = 'explicit'
            if rgb is None:
                rgb = base_material_colour(re8_name, derived)
                source = 'from base material'
            if rgb is None:
                rgb = DEFAULT_PLACEHOLDER
                source = 'default'
            # Flat colour, but at the same size and format as a real texture.
            # Two failures bracket this: a 16x16 solid was *rejected* by the
            # game (rendered as its missing-texture magenta), while reusing the
            # base material's map is wrong for these parts because their UVs
            # are tiled far outside 0..1 -- every clamped sample lands on the
            # atlas padding and the trim turns black.
            write_placeholder(ph, rgb, alpha=alpha, size=PLACEHOLDER_SIZE)
            produced['Diffuse'] = ph
            note = ''
            if 'Smoothness' not in produced:
                sm = base_material_smoothness(re8_name, mat_defs)
                if sm is not None:
                    sp = os.path.join(DDS_DIR, '%s_smooth.dds' % safe)
                    write_smoothness_placeholder(sp, sm, size=PLACEHOLDER_SIZE)
                    produced['Smoothness'] = sp
                    note = ' + smooth %.2f' % sm
            print('  %-26s flat Diffuse %-16s (%s, %dpx)%s'
                  % (re8_name, str(rgb), source, PLACEHOLDER_SIZE, note))

        manifest[re8_name] = {
            'x4_name': x4_full,
            'alpha': alpha,
            'textures': produced,
        }
        print('  %-26s -> %-28s %s' % (re8_name, x4_full,
                                       ','.join(sorted(produced))))

    out = os.path.join(DDS_DIR, 'manifest.json')
    json.dump(manifest, open(out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\nmanifest: %d materials -> %s' % (len(manifest), out))

    total = sum(os.path.getsize(p) for e in manifest.values()
                for p in e['textures'].values())
    print('texture payload: %.1f MB' % (total / 1e6))


if __name__ == '__main__':
    main()
