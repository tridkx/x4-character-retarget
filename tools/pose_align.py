# -*- coding: utf-8 -*-
"""
OBSOLETE -- kept for the record, not used by the pipeline any more.

This tried to fix the "arms bend backwards" symptom by rotating the arm chain
vertices onto the bone direction.  It could not work: the real cause was a
mirrored forward axis plus the impossible job of fitting two differently
proportioned rigs with one transform.  See docs/萝丝移植进展.md §11; the
replacement is retarget_core.BindPoseRetarget.

---

Pose alignment: swing Rose's arms from her source pose onto the X4 bind pose.

Why this is needed
------------------
Rose's mesh is authored with her arms out to the sides, while the X4 Biped
skeleton's arm chain points diagonally down and forward:

    X4  Bip01 L UpperArm   direction ( 0.514, 0.003, -0.858)   ~59 deg down
        Bip01 L Forearm    direction ( 0.455, 0.457, -0.764)
    Rose mesh arm          direction ( 1, 0, 0 ) horizontally outward

Skin weights are authored against the *bind* pose, so when an animation drives
a bone the mesh is pulled toward wherever that bone actually is.  A horizontal
arm bound to a downward bone gets dragged the wrong way -- the "arm bends
backwards" symptom -- and the fingers, which sit furthest from their bones,
stretch the most.

What this does
--------------
For every vertex influenced by the arm chain, rotate it about the shoulder so
the arm direction matches the bone direction.  Rotating the mesh (rather than
moving bones) keeps the skeleton identical to vanilla, so animations, look-at
controllers and the shared component all keep working.

Only the arm chain is touched; the torso, head, legs and their weights are
left exactly as they were.
"""
import math
import numpy as np

#: X4 arm chain, proximal -> distal, without side prefix
ARM_CHAIN = ('Clavicle', 'UpperArm', 'Forearm', 'Hand',
             'Finger0', 'Finger01', 'Finger02', 'Finger0Nub',
             'Finger1', 'Finger11', 'Finger12', 'Finger1Nub',
             'Finger2', 'Finger21', 'Finger22', 'Finger2Nub',
             'Finger3', 'Finger31', 'Finger32', 'Finger3Nub',
             'Finger4', 'Finger41', 'Finger42', 'Finger4Nub')

#: how far along the arm the swing ramps in, as a fraction of the distance
#: from shoulder to hand.  0 = rotate from the shoulder joint outward, which
#: would tear the deltoid; the ramp keeps the shoulder smooth.
RAMP_START = 0.06
RAMP_END = 0.30

#: blend weight -> swing fraction; low-weight vertices near the clavicle are
#: only partially rotated so the shoulder does not collapse.
MIN_SWING = 0.35


def rot_about(axis, angle, pivot):
    """4x4 rotation of `angle` radians about `axis` through `pivot`."""
    axis = np.asarray(axis, float)
    axis = axis / (np.linalg.norm(axis) or 1.0)
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    C = 1.0 - c
    R = np.array([
        [c + x * x * C,     x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C,     y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
    ])
    R4 = np.eye(4)
    R4[:3, :3] = R
    R4[:3, 3] = np.asarray(pivot, float) - R @ np.asarray(pivot, float)
    return R4


def arm_side(bone_name):
    for side in ('L', 'R'):
        if ' %s ' % side in bone_name:
            return side
    return None


def plan_alignment(vert_coords, weights, x4_bones, verbose=True):
    """Return [(rotation_matrix4, vertex_indices)] to apply.

    vert_coords : (N,3) mesh vertices, X4 model space
    weights     : list of {bone_name: weight}
    x4_bones    : {bone_name: {'head': (3,), 'tail': (3,)}}
    """
    verts = np.asarray(vert_coords, float)
    plans = []

    for side in ('L', 'R'):
        up_bone = 'Bip01 %s UpperArm' % side
        hand_bone = 'Bip01 %s Hand' % side
        if up_bone not in x4_bones or hand_bone not in x4_bones:
            continue

        chain_prefix = 'Bip01 %s ' % side
        shoulder = np.array(x4_bones[up_bone]['head'], float)
        bone_dir = np.array(x4_bones[up_bone]['tail'], float) - shoulder
        bone_dir = bone_dir / (np.linalg.norm(bone_dir) or 1.0)

        # Arm direction must come from the MESH, not from the bones: the
        # bones are the target we are rotating towards, so using them as the
        # source direction collapses the rotation to ~0 and then mis-rotates.
        # Collect this side's arm vertices and measure shoulder -> fingertip.
        arm_pts = []
        for i, wd in enumerate(weights):
            tot = 0.0
            for bn, wv in wd.items():
                if bn.startswith(chain_prefix) and bn[len(chain_prefix):] in ARM_CHAIN:
                    tot += wv
            if tot > 0.5:
                arm_pts.append(verts[i])
        if len(arm_pts) < 8:
            continue
        arm_pts = np.array(arm_pts, float)
        # outermost point along the bone axis direction == the hand end
        bone_axis = np.array(x4_bones[hand_bone]['head'], float) - shoulder
        if np.linalg.norm(bone_axis) < 1e-6:
            continue
        bone_axis = bone_axis / np.linalg.norm(bone_axis)
        proj = (arm_pts - shoulder) @ bone_axis
        hand_end = arm_pts[int(np.argmax(proj))]
        mesh_dir = hand_end - shoulder
        mesh_dir = mesh_dir / (np.linalg.norm(mesh_dir) or 1.0)
        arm_len = float(np.linalg.norm(hand_end - shoulder)) or 1.0

        axis = np.cross(mesh_dir, bone_dir)
        axis_len = np.linalg.norm(axis)
        if axis_len < 1e-6:
            continue
        axis = axis / axis_len
        angle = math.atan2(axis_len, float(np.dot(mesh_dir, bone_dir)))

        # vertices driven by this arm's chain (lower threshold than the
        # direction probe above, so partial weights are still carried along)
        idx = []
        for i, wd in enumerate(weights):
            tot = 0.0
            for bn, wv in wd.items():
                if bn.startswith(chain_prefix) and bn[len(chain_prefix):] in ARM_CHAIN:
                    tot += wv
            if tot > 0.15:
                idx.append((i, min(1.0, tot)))
        if not idx:
            continue

        plans.append({
            'side': side, 'axis': axis, 'angle': angle, 'pivot': shoulder,
            'arm_len': arm_len, 'idx': idx,
            'mesh_dir': mesh_dir, 'bone_dir': bone_dir,
        })
        if verbose:
            print('  %s arm: rotate %5.1f deg about (%5.2f,%5.2f,%5.2f)'
                  % (side, math.degrees(angle), *axis))
            print('     mesh dir %s -> bone dir %s   (%d verts)'
                  % (np.round(mesh_dir, 3), np.round(bone_dir, 3), len(idx)))

    return plans


def apply_alignment(vert_coords, weights, x4_bones, verbose=True):
    """Rotate arm vertices onto the bind pose.  Returns new (N,3) array."""
    verts = np.array(vert_coords, float)
    plans = plan_alignment(verts, weights, x4_bones, verbose=verbose)
    if not plans:
        return verts, 0

    for plan in plans:
        pivot = plan['pivot']
        for i, wsum in plan['idx']:
            # ramp: nothing at the joint, full swing further down the arm
            d = np.linalg.norm(verts[i] - pivot) / plan['arm_len']
            t = (d - RAMP_START) / max(1e-6, (RAMP_END - RAMP_START))
            t = min(1.0, max(0.0, t))
            frac = max(MIN_SWING, wsum) * t
            if frac <= 1e-4:
                continue
            M = rot_about(plan['axis'], plan['angle'] * frac, pivot)
            p = np.append(verts[i], 1.0)
            verts[i] = (M @ p)[:3]
    return verts, len(plans)
