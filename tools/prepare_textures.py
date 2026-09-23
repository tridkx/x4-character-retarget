# -*- coding: utf-8 -*-
"""
Prepare all DDS textures + the material manifest for the Rose mod.

Runs under the *system* Python (Blender's bundled Python has no PIL), then
`build_mod.py` consumes the manifest inside Blender.

    python tools/prepare_textures.py
"""

import json
import os
import re
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bc_encode          # noqa: E402
import tex_convert        # noqa: E402

WORK = r"D:\dsh-x4\work"
RE8_MODELS = r"D:\dsh-mod\re8\output\models\Rose_Adult_ShadowsOfRose"
STAGE1_PARTS = os.path.join(WORK, "stage1_parts.json")
DDS_DIR = os.path.join(WORK, "tex_out", "mats")
TMP_DIR = os.path.join(WORK, "tex_out", "tmp")

COLLECTION = 'rose'

#: materials whose diffuse must keep alpha (BC3 instead of BC1)
#: 'shader_eyes_shader' is deliberately absent: the eyeball's albedo is
#: plain RGB (no alpha), and tagging it ALPHA1 made the eye render as a
#: transparent/blank sphere.
ALPHA_MATS = {'Sling_Mat', 'Hair_Mat', 'Stray_Hair_Mat', 'eyelashes_Mat'}

#: placeholder base colours for shader-driven materials with no albedo map
PLACEHOLDER_RGB = {
    'boa_mat_01': (238, 236, 228),
    'boa_mat_02': (238, 236, 228),
    'boa_mat_03': (238, 236, 228),
    'boa_mat_04': (238, 236, 228),
    'shader_eyeslens_shader': (20, 20, 24),
    'eyewet_mat': (235, 235, 238),
    'cap_stitch_mat': (32, 32, 36),
    'eyebrow_mat': (78, 56, 42),
    'eyelens_mat': (18, 18, 20),
    'foodie_stitch_mat': (64, 64, 68),
    'jacket_stitch_mat': (58, 54, 50),
    'pants_stitch_mat': (62, 56, 48),
    'shirt_stitch_mat': (232, 230, 224),
    'shoes_stitch_mat': (38, 38, 42),
}
DEFAULT_PLACEHOLDER = (200, 200, 200)

#: see tex_convert.MAX_TEXTURE_SIZE
MAX_SIZE = 1024


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


def write_placeholder(path, rgb, alpha=False, size=16):
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


def main():
    os.makedirs(DDS_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)

    mat_defs = json.load(open(os.path.join(
        RE8_MODELS, "Rose_Adult_ShadowsOfRose_materials.json"),
        encoding='utf-8'))['materials']
    names = used_materials()

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

        if 'Diffuse' not in produced:
            ph = os.path.join(DDS_DIR, '%s_diff.dds' % safe)
            rgb = PLACEHOLDER_RGB.get(local_name(re8_name), DEFAULT_PLACEHOLDER)
            write_placeholder(ph, rgb, alpha=alpha)
            produced['Diffuse'] = ph
            print('  %-26s placeholder Diffuse %s' % (re8_name, rgb))

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
