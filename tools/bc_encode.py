# -*- coding: utf-8 -*-
"""
Vectorised BC1 / BC3 / BC4 / BC5 DDS encoder (numpy + struct).

X4CharacterConverter validates DDS pixel formats:

    Diffuse     -> BC1 or BC3
    Normal      -> BC5
    Smoothness  -> BC4

The bundled texconv DLL fails on this machine (E_NOINTERFACE), so block
compression is implemented here.  A pure-Python per-texel loop is far too slow
for 2048^2 character textures, so every block is processed with numpy.

Block layout
------------
BC1 : 8 bytes  = u16 colour0 | u16 colour1 | 16 x 2-bit indices
BC4 : 8 bytes  = u8 red0 | u8 red1 | 16 x 3-bit indices
BC5 : 16 bytes = two BC4 blocks (red, then green)
BC3 : 16 bytes = BC1 colour block (4-colour mode) + BC4 alpha block

Index bit order is column-major (i = x + 4*y), i.e. bit pair 0 belongs to the
top-left texel of the block.  Getting this wrong yields per-block colour
confetti, so it is asserted in the unit test at the bottom of this file.
"""

import os
import struct

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _rgb_to_565(rgb):
    """(..., 3) uint8 -> (...) uint16 RGB565."""
    r = rgb[..., 0].astype(np.uint16)
    g = rgb[..., 1].astype(np.uint16)
    b = rgb[..., 2].astype(np.uint16)
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def _expand565(c):
    """(...,) uint16 RGB565 -> (..., 3) float32 RGB."""
    r = (c >> 11) & 0x1F
    g = (c >> 5) & 0x3F
    b = c & 0x1F
    out = np.empty(c.shape + (3,), dtype=np.float32)
    out[..., 0] = (r << 3) | (r >> 2)
    out[..., 1] = (g << 2) | (g >> 4)
    out[..., 2] = (b << 3) | (b >> 2)
    return out


def _to_blocks(arr, bs=4):
    """(h, w, c) -> (nby, nbx, bs*bs, c).

    Texels inside a block follow the BC convention i = x + bs*y (x varies
    fastest), and each index field is written in that order.  Emitting
    row-major texels here silently produces per-block colour confetti.

    Note the reshape/transpose must be done in one expression on the original
    (C-contiguous) array: transposing first and reshaping afterwards makes
    numpy fall back to memory order and scrambles the texel sequence.
    """
    h, w = arr.shape[:2]
    ph = (-h) % bs
    pw = (-w) % bs
    if ph or pw:
        pad = [(0, ph), (0, pw)] + [(0, 0)] * (arr.ndim - 2)
        arr = np.pad(arr, pad, mode='edge')
    h2, w2 = arr.shape[:2]
    # (by, y, bx, x, c) -> transpose -> (by, bx, y, x, c) -> flatten
    # so that i = x + bs*y, i.e. texel 0 is the block's left edge.
    a = arr.reshape(h2 // bs, bs, w2 // bs, bs, arr.shape[2]).transpose(0, 2, 1, 3, 4)
    return a.reshape(h2 // bs, w2 // bs, bs * bs, arr.shape[2]), (h, w)


def _bits_to_u32(bits):
    """(..., n) uint32 of values 0..3 -> (...,) uint32 packed LSB-first."""
    n = bits.shape[-1]
    out = np.zeros(bits.shape[:-1], dtype=np.uint32)
    for i in range(n):
        out |= (bits[..., i].astype(np.uint32) & 0x3) << (2 * i)
    return out


def _bits_to_u48(bits):
    """(..., n) uint32 of values 0..7 -> (...,) uint64 packed LSB-first."""
    n = bits.shape[-1]
    out = np.zeros(bits.shape[:-1], dtype=np.uint64)
    for i in range(n):
        out |= (bits[..., i].astype(np.uint64) & 0x7) << (3 * i)
    return out


# --------------------------------------------------------------------------
# BC1
# --------------------------------------------------------------------------

def _bc1_pack(px, force_four=True):
    """(nby, nbx, 16, 3) uint8 -> (nby, nbx, 8) uint8 BC1 blocks.

    Endpoints are chosen along the block's principal colour axis (power
    iteration on the 3x3 covariance), not by luminance extremes.  Picking the
    luminance extremes collapses a block containing both white and black plus
    saturated colours onto a greyscale line, which turns e.g. red/blue blocks
    into grey mush.
    """
    nby, nbx = px.shape[0], px.shape[1]
    n = px.shape[2]
    v = px.astype(np.float32)
    mean = v.mean(axis=2, keepdims=True)               # (nby, nbx, 1, 3)
    d = v - mean                                       # (nby, nbx, 16, 3)

    # covariance per block, then power-iterate for the dominant eigenvector
    cov = np.einsum('...ni,...nj->...ij', d, d)        # (nby, nbx, 3, 3)
    axis = np.tile(np.array([1.0, 1.0, 1.0], np.float32),
                   (nby, nbx, 1))
    for _ in range(6):
        axis = np.einsum('...ij,...j->...i', cov, axis)
        norm = np.linalg.norm(axis, axis=-1, keepdims=True)
        axis = np.where(norm > 1e-6, axis / np.maximum(norm, 1e-6), axis)

    proj = np.einsum('...ni,...i->...n', d, axis)      # (nby, nbx, 16)
    imax = proj.argmax(axis=2)
    imin = proj.argmin(axis=2)

    idx = np.arange(nby)[:, None]
    idy = np.arange(nbx)[None, :]
    c_hi = px[idx, idy, imax]                          # (nby, nbx, 3)
    c_lo = px[idx, idy, imin]

    p0 = _rgb_to_565(c_hi)
    p1 = _rgb_to_565(c_lo)

    # BC1's 4-colour mode requires p0 > p1
    swap = p1 > p0
    p0, p1 = np.where(swap, p1, p0), np.where(swap, p0, p1)
    same = p0 == p1
    p1 = np.where(same, np.maximum(p0.astype(np.int32) - 1, 0).astype(np.uint16), p1)

    e0 = _expand565(p0)
    e1 = _expand565(p1)
    pal = np.stack([e0, e1, (2 * e0 + e1) / 3.0, (e0 + 2 * e1) / 3.0], axis=2)
    dist = ((v[:, :, None, :, :] - pal[:, :, :, None, :]) ** 2).sum(axis=-1)
    sel = dist.argmin(axis=2).astype(np.uint32)
    bits = _bits_to_u32(sel)

    out = np.empty((nby, nbx, 8), dtype=np.uint8)
    out[..., 0:2] = p0[..., None].view(np.uint8)
    out[..., 2:4] = p1[..., None].view(np.uint8)
    out[..., 4:8] = bits[..., None].view(np.uint8)
    return out


# --------------------------------------------------------------------------
# BC4
# --------------------------------------------------------------------------

def _bc4_pack(vals, force_eight=True):
    """(nby, nbx, 16) uint8 -> (nby, nbx, 8) uint8 BC4 blocks."""
    v = vals.astype(np.int32)
    hi = v.max(axis=2)
    lo = v.min(axis=2)

    levels = np.zeros(v.shape[:2] + (8,), dtype=np.int32)
    levels[..., 0] = hi
    levels[..., 1] = lo
    for i in range(1, 7):
        levels[..., 1 + i] = ((7 - i) * hi + i * lo) // 7

    d = np.abs(v[:, :, None, :] - levels[:, :, :, None])
    sel = d.argmin(axis=2).astype(np.uint64)
    bits = _bits_to_u48(sel)

    out = np.empty(v.shape[:2] + (8,), dtype=np.uint8)
    out[..., 0] = hi.astype(np.uint8)
    out[..., 1] = lo.astype(np.uint8)
    # 48 bits of indices: take the low 6 bytes of the uint64 little-endian
    out[..., 2:8] = bits[..., None].view(np.uint8)[..., :6]
    return out


# --------------------------------------------------------------------------
# DDS container
# --------------------------------------------------------------------------

DDSD_CAPS = 0x1
DDSD_HEIGHT = 0x2
DDSD_WIDTH = 0x4
DDSD_PIXELFORMAT = 0x1000
DDSD_LINEARSIZE = 0x80000
DDPF_FOURCC = 0x4
DXGI = {'BC1': 71, 'BC3': 77, 'BC4': 80, 'BC5': 83}

#: Legacy (non-DX10) FourCC codes.
#:
#: X4CharacterConverter's DDS reader looks for the DXGI format at byte 128,
#: but a DX10 header stores `dwSize` (= 60) there and the format at 132 -- so
#: feeding it a DX10 file makes it report "DXGI format is not supported: 60".
#: Legacy FourCC headers have no extension, so the payload starts at 128 and
#: the reader takes the FourCC branch instead.
FOURCC = {'BC1': b'DXT1', 'BC3': b'DXT5', 'BC4': b'ATI1', 'BC5': b'ATI2'}

#: total header length of a legacy DDS container
HEADER_BYTES = 128


def write_dds(path, width, height, fmt, data):
    """Write a legacy FourCC DDS file."""
    four_cc = FOURCC[fmt]
    block_bytes = 8 if fmt in ('BC1', 'BC4') else 16
    pitch = max(1, (width + 3) // 4) * block_bytes

    hdr = bytearray()
    hdr += b'DDS '
    hdr += struct.pack('<I', 124)                     # dwSize
    hdr += struct.pack('<I', DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH
                       | DDSD_PIXELFORMAT | DDSD_LINEARSIZE)
    hdr += struct.pack('<I', height)
    hdr += struct.pack('<I', width)
    hdr += struct.pack('<I', pitch)                   # dwPitchOrLinearSize
    hdr += struct.pack('<I', 0)                       # dwDepth
    hdr += struct.pack('<I', 1)                       # dwMipMapCount
    hdr += b'\x00' * 44                               # dwReserved1[11]
    hdr += struct.pack('<I', 32)                      # ddspf.dwSize
    hdr += struct.pack('<I', DDPF_FOURCC)
    hdr += four_cc
    hdr += b'\x00' * 20                               # rgb bit masks
    hdr += struct.pack('<I', 0x1000)                  # dwCaps = TEXTURE
    hdr += b'\x00' * 16                               # dwCaps2..4 + reserved
    assert len(hdr) == HEADER_BYTES, len(hdr)

    with open(path, 'wb') as fh:
        fh.write(bytes(hdr))
        fh.write(data)


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def encode_bc1(img, path):
    arr = np.asarray(img.convert('RGB'))
    blocks, (h, w) = _to_blocks(arr)
    out = _bc1_pack(blocks, force_four=True)
    write_dds(path, w, h, 'BC1', out.tobytes())
    return path


def encode_bc3(img, path):
    rgba = img.convert('RGBA')
    arr = np.asarray(rgba)[..., :3]
    alpha = np.asarray(rgba)[..., 3]
    cb, (h, w) = _to_blocks(arr)
    ab, _ = _to_blocks(alpha[..., None])
    colour = _bc1_pack(cb, force_four=True)
    a = _bc4_pack(ab[..., 0])
    out = np.concatenate([colour, a], axis=2)
    write_dds(path, w, h, 'BC3', out.tobytes())
    return path


def encode_bc4(img, path):
    g = np.asarray(img.convert('L'))
    blocks, (h, w) = _to_blocks(g[..., None])
    out = _bc4_pack(blocks[..., 0])
    write_dds(path, w, h, 'BC4', out.tobytes())
    return path


def encode_bc5(img, path):
    arr = np.asarray(img.convert('RGB'))
    rb, (h, w) = _to_blocks(arr[..., 0:1])
    gb, _ = _to_blocks(arr[..., 1:2])
    r = _bc4_pack(rb[..., 0])
    g = _bc4_pack(gb[..., 0])
    out = np.concatenate([r, g], axis=2)
    write_dds(path, w, h, 'BC5', out.tobytes())
    return path


ENCODERS = {'BC1': encode_bc1, 'BC3': encode_bc3,
            'BC4': encode_bc4, 'BC5': encode_bc5}


# --------------------------------------------------------------------------
# self-test: round-trip decode + PSNR
# --------------------------------------------------------------------------

def _dec_bc1(p0, p1, bits):
    e0 = _expand565(np.array([p0]))[0]
    e1 = _expand565(np.array([p1]))[0]
    if p0 > p1:
        pal = [e0, e1, (2 * e0 + e1) / 3, (e0 + 2 * e1) / 3]
    else:
        pal = [e0, e1, (e0 + e1) / 2, np.zeros(3, np.float32)]
    return np.array([pal[(bits >> (2 * i)) & 3] for i in range(16)])


def _self_test():
    """Round-trip a smooth image and assert sane quality.

    Note: pure random noise is NOT a valid test for BC1 -- a block holds only
    four colours, so 16 unrelated texels are inherently unrepresentable and
    even a correct encoder scores ~12 dB.  Real character textures are locally
    smooth, so the test image is smooth too.
    """
    import math
    h = w = 256
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.stack([
        (np.sin(xx / 17.0) * 0.5 + 0.5) * 255.0,
        (yy / h) * 255.0,
        (np.cos((xx + yy) / 23.0) * 0.5 + 0.5) * 255.0,
    ], axis=-1)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

    dds = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '_selftest_bc1.dds')
    encode_bc1(img, dds)
    raw = open(dds, 'rb').read()
    nb = 256 // 4
    assert len(raw) - HEADER_BYTES == nb * nb * 8, len(raw)

    data = np.frombuffer(raw[HEADER_BYTES:], dtype=np.uint8).reshape(nb, nb, 8)
    p0 = data[..., 0].astype(np.uint16) | (data[..., 1].astype(np.uint16) << 8)
    p1 = data[..., 2].astype(np.uint16) | (data[..., 3].astype(np.uint16) << 8)
    bits = (data[..., 4].astype(np.uint32)
            | (data[..., 5].astype(np.uint32) << 8)
            | (data[..., 6].astype(np.uint32) << 16)
            | (data[..., 7].astype(np.uint32) << 24))

    e0 = _expand565(p0)
    e1 = _expand565(p1)
    pal = np.stack([e0, e1, (2 * e0 + e1) / 3.0, (e0 + 2 * e1) / 3.0], axis=2)
    idx = np.zeros((nb, nb, 16), np.uint32)
    for i in range(16):
        idx[..., i] = (bits >> (2 * i)) & 3
    rec = np.zeros((nb, nb, 4, 4, 3), np.float32)
    for by in range(nb):
        for bx in range(nb):
            p = pal[by, bx]                      # (4,3)
            b_idx = idx[by, bx]                  # (16,)
            for i in range(16):
                rec[by, bx, i // 4, i % 4] = p[b_idx[i]]
    rec = rec.transpose(0, 2, 1, 3, 4).reshape(h, w, 3)

    mse = ((rec - np.asarray(img, np.float32)) ** 2).mean()
    psnr = 99.0 if mse == 0 else 10 * math.log10(255 * 255 / mse)
    print('BC1 self-test PSNR = %.2f dB' % psnr)
    os.remove(dds)
    assert psnr > 35, 'BC1 encoder quality too low: %.2f dB' % psnr
    print('self-test OK')


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 1:
        _self_test()
    else:
        src, dst, fmt = sys.argv[1], sys.argv[2], sys.argv[3]
        ENCODERS[fmt](Image.open(src), dst)
        print('wrote', dst, os.path.getsize(dst), 'bytes')
