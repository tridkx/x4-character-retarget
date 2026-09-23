# -*- coding: utf-8 -*-
"""
RE8 (RE Engine) -> X4: Foundations character conversion core.

Takes a RE Engine .mesh (positions + skin weights, via RE-Mesh-Editor) and
produces Blender-ready geometry whose vertex weights are expressed against the
X4 Biped skeleton, so it can be exported as .xac by X4CharacterConverter.

Two problems this module solves
-------------------------------
1. Coordinate frame + scale.
   RE8 characters are Y-up / metres; X4 characters are Z-up / centimetres.
   Empirically the mapping is  (x, y, z)_re8 -> (x, -z, y)_x4 * 100.

2. Skeleton topology mismatch.
   Rose carries a 203-bone UE/Mixamo-style rig; X4 uses a 91-bone 3ds Max
   Biped rig, and the two rigs have different proportions (Rose's legs are
   shorter relative to her torso).  Bone-position nearest-neighbour alone
   therefore mis-assigns bones, so the mapping is driven by *bone name
   semantics* first, with nearest-neighbour only as a fallback for helper
   bones that have no meaningful counterpart (muscle bones, cloth chains).
"""

import math
import os
import re
import sys

# --------------------------------------------------------------------------
# coordinate transform
# --------------------------------------------------------------------------

#: RE8 world (x, y, z) metres  ->  X4 world (x, y, z) centimetres
SCALE = 100.0


def re8_to_x4(p, scale=SCALE):
    """RE8 source position (metres) -> the SAME arrangement the skeleton uses.

    fit_segment() least-squares fits scale/offset between these values and
    bone positions that the converter's importer has ALREADY rotated, so both
    sides must share an arrangement or the fit collapses (it produced a ~2 cm
    mesh).  The importer's xac_to_blender mapping is

        (x, y, z)_xac -> (x, -z, y)_blender

    i.e. in Blender the height sits in the THIRD component.  RE8 has height in
    its second, so swap those two here; the height ends up in component 3 and
    the fit is well conditioned again.

    build_mod.fill_slot() then performs the single authoring->Blender
    rotation, and the exporter reverses it when writing the .xac.
    """
    return (p[0] * scale, p[2] * scale, p[1] * scale)


# --------------------------------------------------------------------------
# bone name mapping
# --------------------------------------------------------------------------

#: Regex rules, evaluated in order.  First match wins.
#: group(1) = side letter (L/R), group(2) = finger digit, group(3) = phalanx.
_NAME_RULES = [
    # --- spine / head -----------------------------------------------------
    (r'^root$',                    lambda m: None),               # drop
    (r'^Null_Offset$',             lambda m: None),               # drop
    (r'^Hip$',                     lambda m: 'Bip01 Pelvis'),
    (r'^Spine_0$',                 lambda m: 'Bip01 Spine'),
    (r'^Spine_1$',                 lambda m: 'Bip01 Spine1'),
    (r'^Spine_2$',                 lambda m: 'Bip01 Spine2'),
    (r'^Neck_0$',                  lambda m: 'Bip01 Neck'),
    (r'^Neck_1$',                  lambda m: 'Bip01 Neck'),
    (r'^Head$',                    lambda m: 'Bip01 Head'),
    (r'^NeckTwist.*$',             lambda m: 'Bip01 Neck'),

    # --- shoulders / arms -------------------------------------------------
    (r'^([LR])_Shoulder$',         lambda m: 'Bip01 %s Clavicle' % m.group(1)),
    (r'^([LR])_UpperArm$',         lambda m: 'Bip01 %s UpperArm' % m.group(1)),
    (r'^([LR])_Forearm$',          lambda m: 'Bip01 %s Forearm' % m.group(1)),
    (r'^([LR])_Hand$',             lambda m: 'Bip01 %s Hand' % m.group(1)),
    (r'^([LR])_Palm$',             lambda m: 'Bip01 %s Hand' % m.group(1)),
    (r'^([LR])_Wep$',              lambda m: 'Bip01 %s Hand' % m.group(1)),
    (r'^B_Wep$',                   lambda m: 'Bip01 Spine'),

    # twist / muscle helpers collapse onto their parent limb
    (r'^([LR])_UpperArm_Twist_\d+$', lambda m: 'Bip01 %s UpperArm' % m.group(1)),
    (r'^([LR])_Forearm_Twist_\d+$',  lambda m: 'Bip01 %s Forearm' % m.group(1)),
    (r'^([LR])_Thigh_Twist_\d+$',    lambda m: 'Bip01 %s Thigh' % m.group(1)),
    (r'^([LR])_Shin_Twist_\d+$',     lambda m: 'Bip01 %s Calf' % m.group(1)),
    (r'^([LR])_delt.*_muscle$',    lambda m: 'Bip01 %s UpperArm' % m.group(1)),
    (r'^([LR])_pec[A-Z]?_muscle$', lambda m: 'Bip01 %s UpperArm' % m.group(1)),
    (r'^([LR])_trap.*_muscle$',    lambda m: 'Bip01 %s Clavicle' % m.group(1)),
    (r'^([LR])_lat[A-Z]?_muscle$', lambda m: 'Bip01 %s Clavicle' % m.group(1)),
    (r'^([LR])_serratus.*_muscle$', lambda m: 'Bip01 %s Clavicle' % m.group(1)),
    (r'^([LR])_muscle.*$',         lambda m: 'Bip01 %s UpperArm' % m.group(1)),

    # --- fingers ----------------------------------------------------------
    # X4 Biped chains: Finger0=Thumb, 1=Index, 2=Middle, 3=Ring, 4=Pinky.
    # Each chain is FingerN / FingerN1 / FingerN2 / FingerNNub, so RE8's
    # F1 / F2 / F3 map to the empty / "1" / "2" suffixes respectively.
    (r'^([LR])_Thumb(\d)$',        lambda m: _phalanx(m, '0')),
    (r'^([LR])_IndexF(\d)$',       lambda m: _phalanx(m, '1')),
    (r'^([LR])_MiddleF(\d)$',      lambda m: _phalanx(m, '2')),
    (r'^([LR])_RingF(\d)$',        lambda m: _phalanx(m, '3')),
    (r'^([LR])_PinkyF(\d)$',       lambda m: _phalanx(m, '4')),

    # --- legs -------------------------------------------------------------
    (r'^([LR])_Thigh$',            lambda m: 'Bip01 %s Thigh' % m.group(1)),
    (r'^([LR])_Calf$',             lambda m: 'Bip01 %s Calf' % m.group(1)),
    (r'^([LR])_Shin$',             lambda m: 'Bip01 %s Calf' % m.group(1)),
    (r'^([LR])_Foot$',             lambda m: 'Bip01 %s Foot' % m.group(1)),
    (r'^([LR])_Toe$',              lambda m: 'Bip01 %s Toe0' % m.group(1)),
    (r'^([LR])_Knee_Helper$',      lambda m: 'Bip01 %s Calf' % m.group(1)),

    # --- face -------------------------------------------------------------
    (r'^([LR])_Eye$',              lambda m: 'left_eye_dummy' if m.group(1) == 'L'
                                            else 'right_eye_dummy'),
    (r'^FACIAL_([LR])_Pupil$',     lambda m: 'left_eye_dummy' if m.group(1) == 'L'
                                            else 'right_eye_dummy'),
    (r'^FACIAL_.*$',               lambda m: 'Bip01 Head'),
    (r'^([LR])_(Upper|Lower)Eyelid$', lambda m: 'Bip01 Head'),
    (r'^([LR])_Eyebrow_\d+$',      lambda m: 'Bip01 Head'),
    (r'^([LR])_Cheek$',            lambda m: 'Bip01 Head'),
    (r'^C_Jaw$',                   lambda m: 'Bip01 Head'),
    (r'^C_.*$',                    lambda m: 'Bip01 Head'),      # lips/nose/jaw
    (r'^([LR])_[UL]_MouthCorner$', lambda m: 'Bip01 Head'),
    (r'^([LR])_(Upper|Lower)Lip$', lambda m: 'Bip01 Head'),
    (r'^([LR])_NasalisCorner$',    lambda m: 'Bip01 Head'),

    # --- cloth chains (jacket/hood) collapse onto the torso ---------------
    # jacket_<N>_<M>: N is the RADIAL index around the torso (0..8, every chain
    # hangs off Spine_2), M is the distance DOWN the chain.  Measured from the
    # skeleton rather than assumed:
    #     jacket_*_0  z = 121..132   (Spine_2 at 127.7)
    #     jacket_*_1  z = 115..120   (Spine_1 at 112.4)
    #     jacket_*_2  z = 107..109   (Spine   spans  97..112)
    #     jacket_*_3  z =  99..100   (Pelvis  at  97.2)
    # Mapping on N (the old behaviour) bound the hem to the neck.
    (r'^jacket_\d+_(\d+)$',        lambda m: _JACKET_TARGETS[
        min(int(m.group(1)), len(_JACKET_TARGETS) - 1)]),
    (r'^Hood_\d+$',                lambda m: 'Bip01 Neck'),

    # --- hair chains collapse onto the head -------------------------------
    (r'^Hair[A-Z]_FK_\d+$',        lambda m: 'Bip01 Head'),
]

#: jacket_<N>_<M> folded by M (0 = chest, 3 = hem), measured against the spine
_JACKET_TARGETS = [
    'Bip01 Spine2', 'Bip01 Spine1', 'Bip01 Spine', 'Bip01 Pelvis',
]

_COMPILED = [(re.compile(rx), fn) for rx, fn in _NAME_RULES]


def _phalanx(m, digit):
    """RE8 <side>_<Finger>F<n>  ->  X4 'Bip01 <side> Finger<digit><suffix>'.

    n = 1,2,3 -> suffix '', '1', '2'  (X4 has no separate 3rd phalanx bone;
    the tip lives in Finger<N>Nub, which carries no skin weights).
    """
    n = int(m.group(2))
    suffix = '' if n == 1 else str(n - 1)
    return 'Bip01 %s Finger%s%s' % (m.group(1), digit, suffix)


def map_bone(name):
    """Map one RE8 bone name to an X4 bone name, or None to drop it."""
    for rx, fn in _COMPILED:
        m = rx.match(name)
        if m:
            return fn(m)
    return None


#: Bones that have a real one-to-one counterpart in the X4 rig: their own
#: position in the source skeleton is the anchor the bind-pose transfer uses.
#: Everything else (twist/muscle helpers, cloth and hair chains, facial bones)
#: only *shares* an X4 bone; those must borrow the transform of the nearest
#: direct bone instead of being dragged to their mapped bone's position.
_DIRECT_BONES = frozenset([
    'Hip', 'Spine_0', 'Spine_1', 'Spine_2', 'Neck_0', 'Neck_1', 'Head',
    'L_Shoulder', 'R_Shoulder', 'L_UpperArm', 'R_UpperArm',
    'L_Forearm', 'R_Forearm', 'L_Hand', 'R_Hand', 'L_Palm', 'R_Palm',
    'L_Thigh', 'R_Thigh', 'L_Shin', 'R_Shin', 'L_Foot', 'R_Foot',
    'L_Toe', 'R_Toe', 'L_Eye', 'R_Eye',
])

_DIRECT_PREFIXES = (
    'L_Thumb', 'R_Thumb', 'L_IndexF', 'R_IndexF', 'L_MiddleF', 'R_MiddleF',
    'L_RingF', 'R_RingF', 'L_PinkyF', 'R_PinkyF',
)


def is_direct_bone(name):
    """True when `name` has a positional counterpart in the X4 skeleton."""
    return name in _DIRECT_BONES or name.startswith(_DIRECT_PREFIXES)


def build_bone_map(rose_bones, x4_bone_positions, drop_unmapped=True):
    """Return {rose_bone_name: x4_bone_name}.

    Bones with a semantic match use it; the rest fall back to the nearest X4
    bone in transformed space (only meaningful for helper bones).
    """
    result = {}
    unmatched = []
    for rb in rose_bones:
        target = map_bone(rb['name'])
        if target is not None:
            result[rb['name']] = target
        else:
            unmatched.append(rb)

    for b in unmatched:
        if drop_unmapped:
            result[b['name']] = None
            continue
        m = b['worldMatrix']
        p = re8_to_x4((m[3][0], m[3][1], m[3][2]))
        best, bestd = None, 1e18
        for xn, xp in x4_bone_positions.items():
            if not is_deform_bone(xn):
                continue
            d = (p[0] - xp[0]) ** 2 + (p[1] - xp[1]) ** 2 + (p[2] - xp[2]) ** 2
            if d < bestd:
                best, bestd = xn, d
        result[b['name']] = best

    return result


#: X4 bones that actually deform the mesh (no morph/material pseudo-bones)
def is_deform_bone(x4_name):
    if not (x4_name.startswith('Bip01')
            or x4_name.startswith('Attachment')
            or 'eye_dummy' in x4_name
            or x4_name.endswith(('Helper', 'LookAt', 'Nub'))):
        return False
    # morph / viseme entries are material slots, not bones
    return not (x4_name.endswith('.xac') or '.' in x4_name.split(' ')[0]
                and x4_name[0].isupper() and '_' not in x4_name)
