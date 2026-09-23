# -*- coding: utf-8 -*-
"""
RE8 -> X4 bind-pose transfer: move a source mesh onto the X4 skeleton, bone
by bone.

Why a single rigid transform is not enough
------------------------------------------
Fitting one Kabsch transform over the matched bones leaves the torso within a
few centimetres but the hands ~25 cm and the toes ~11 cm away from the bones
that drive them, because the two rigs differ in *pose* (Rose's arms are
authored hanging forward, the X4 Biped's hang down) and in *proportions* (the
X4 torso and arms are much longer).  Skinning is defined against the bind
pose, so a vertex sitting 25 cm from its bone is dragged the wrong way by
every animation -- the "limbs bend backwards" symptom.

What this does
--------------
For every X4 bone B that a source bone maps onto, build one rigid transform

    x  ->  q_B + R_B (x - p_b)

with p_b the source bone position after the global frame fit, q_B the X4
bone's bind position, and R_B the minimal rotation taking the source bone axis
onto the target bone axis.  A vertex is then moved by the weighted blend of
the transforms of the bones that skin it -- linear blend skinning, applied
once at conversion time.

Two details that matter:

* the bone axis is the direction to the child bone, computed identically on
  both skeletons.  The source skeleton's bone matrices do NOT share a local
  axis convention (the spine's axis is in row 1, the upper arm's in row 0),
  so reading an axis out of the matrix rotates the spine by 90 deg and the
  left fingers by 172 deg.
* "folding" bones (jacket_*, Hair*_FK_*, *_Twist_*, FACIAL_*) have no
  counterpart position in the target rig; they inherit the transform of the
  nearest direct bone on the same side instead of being moved to their mapped
  bone.  Without that, a jacket gets pushed inside the ribcage.
"""

import numpy as np

from re8_to_x4 import map_bone, is_direct_bone

#: bone pairs used for the global frame fit; unambiguous, symmetric, and
#: spread over the body so the fit is well conditioned
ALIGN_PAIRS = [
    ('Hip', 'Bip01 Pelvis'), ('Spine_0', 'Bip01 Spine'),
    ('Spine_1', 'Bip01 Spine1'), ('Spine_2', 'Bip01 Spine2'),
    ('Neck_0', 'Bip01 Neck'), ('Head', 'Bip01 Head'),
    ('L_Shoulder', 'Bip01 L Clavicle'), ('R_Shoulder', 'Bip01 R Clavicle'),
    ('L_UpperArm', 'Bip01 L UpperArm'), ('R_UpperArm', 'Bip01 R UpperArm'),
    ('L_Forearm', 'Bip01 L Forearm'), ('R_Forearm', 'Bip01 R Forearm'),
    ('L_Thigh', 'Bip01 L Thigh'), ('R_Thigh', 'Bip01 R Thigh'),
    ('L_Shin', 'Bip01 L Calf'), ('R_Shin', 'Bip01 R Calf'),
    ('L_Foot', 'Bip01 L Foot'), ('R_Foot', 'Bip01 R Foot'),
]

#: below this the source bone is treated as coincident with its child
#: (Rose's Hip and Spine_0 share a position, which would give a zero axis)
_MIN_AXIS_LEN = 2.0

#: X4 drives the eye dummies with a look-at controller.  Rose's eyeball and
#: eyelid geometry sits ~9 cm away from those bones, so a gaze rotation swings
#: it out of the head -- the "eyes occasionally drift off the face" report.
#: These bones' weights are moved onto the head instead.
EYE_CONTROLLERS = {'left_eye_dummy', 'right_eye_dummy'}
HEAD_BONE = 'Bip01 Head'


def rose_to_blender(p_m):
    """RE8 source (x, up, forward) metres -> X4/Blender arrangement cm.

    (x, up, forward) -> (x, forward, up).  The forward axis keeps its sign:
    Rose's eyeballs sit at +z in her own space and the X4 eyeballs sit at +y,
    so z maps to +y.  Negating z (as this pipeline did for a long time)
    mirrors the character front-to-back; the torso barely notices because it
    is nearly symmetric, but the hands land 42 cm and the toes 23 cm away
    from their bones.
    """
    return np.array([p_m[0] * 100.0, p_m[2] * 100.0, p_m[1] * 100.0], float)


def kabsch(P, Q):
    """Least-squares similarity fit P -> Q.  Returns (scale, R, t)."""
    pc, qc = P.mean(0), Q.mean(0)
    P0, Q0 = P - pc, Q - qc
    U, S, Vt = np.linalg.svd(P0.T @ Q0)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    scale = float(S.sum() / (P0 ** 2).sum())
    return scale, R, qc - scale * (R @ pc)


def min_rotation(a, b):
    """Rotation matrix taking unit vector a onto unit vector b (shortest arc)."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    a = a / (np.linalg.norm(a) or 1.0)
    b = b / (np.linalg.norm(b) or 1.0)
    v = np.cross(a, b)
    c = float(a @ b)
    s = float(np.linalg.norm(v))
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        # 180 degrees: any perpendicular axis will do.  Never return -I, which
        # is a reflection, not a rotation.
        t = np.array([1.0, 0.0, 0.0])
        if abs(a[0]) > 0.9:
            t = np.array([0.0, 1.0, 0.0])
        k = np.cross(a, t)
        k = k / (np.linalg.norm(k) or 1.0)
        return 2.0 * np.outer(k, k) - np.eye(3)
    vx = np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])
    return np.eye(3) + vx + vx @ vx * ((1.0 - c) / (s * s))


class BindPoseRetarget:
    """Builds the per-bone transforms, then applies them to vertices."""

    def __init__(self, rose_pos_m, rose_parent, x4_bones, verbose=True):
        """
        rose_pos_m : {re8 bone: (x, y, z) metres}   source rig, world space
        rose_parent: {re8 bone: parent name or None}
        x4_bones   : {x4 bone: {'head': (3,), 'tail': (3,), ...}}
        """
        self.rose_pos = {k: np.asarray(v, float)
                         for k, v in rose_pos_m.items()}
        self.rose_parent = rose_parent
        self.x4 = x4_bones
        self.verbose = verbose

        self.children = {}
        for b, p in rose_parent.items():
            if p:
                self.children.setdefault(p, []).append(b)

        self._fit_frame()
        self._build_direct()
        self._build_delta()

    # ------------------------------------------------------------------ setup
    def _fit_frame(self):
        P, Q = [], []
        for rb, xb in ALIGN_PAIRS:
            if rb in self.rose_pos and xb in self.x4:
                P.append(rose_to_blender(self.rose_pos[rb]))
                Q.append(np.asarray(self.x4[xb]['head'], float))
        if len(P) < 3:
            raise RuntimeError('not enough matched bone pairs for the frame fit')
        self.scale, self.R, self.t = kabsch(np.array(P), np.array(Q))
        self.src = {b: self.scale * (self.R @ rose_to_blender(p)) + self.t
                    for b, p in self.rose_pos.items()}

        if self.verbose:
            pred = (self.scale * (self.R @ np.array(P).T)).T + self.t
            res = [float(np.linalg.norm(a - b)) for a, b in zip(pred, Q)]
            print('  frame fit: scale=%.5f det(R)=%+.3f' %
                  (self.scale, float(np.linalg.det(self.R))))
            worst = sorted(zip(res, [p[0] for p in ALIGN_PAIRS]), reverse=True)
            print('  worst matched pairs: ' +
                  ', '.join('%s %.1fcm' % (n, d) for d, n in worst[:4]))

    def _main_child(self, bone, pos):
        """The first child on the main chain, or None.

        Deliberately NOT the mean of all children: Rose's Hip has Spine_0
        (exactly coincident with it) plus both thighs hanging downwards, so a
        mean points *down* while the X4 pelvis points up -- a 161 degree
        rotation that flips every hem, trouser and jacket vertex weighted to
        the pelvis.  The first child in skeleton order is the spine, and when
        it is unusable the parent direction is the honest fallback.
        """
        for c in self.children.get(bone, []):
            if c not in pos:
                continue
            v = pos[c] - pos[bone]
            if float(np.linalg.norm(v)) >= _MIN_AXIS_LEN:
                return v / np.linalg.norm(v)
            break                      # main chain is degenerate: stop here
        return None

    def _pair_axis(self, bone, B):
        """(source axis, target axis) for a bone pair, derived identically.

        The target axis is read off the *same* child, mapped into the X4 rig,
        so both sides always talk about the same anatomical direction.
        """
        upos, xpos = self.src, self.x4

        def target_dir(src_bone, src_other):
            other = map_bone(src_other)
            if not other or other not in xpos or other == B:
                return None
            d = np.asarray(xpos[other]['head'], float) - np.asarray(
                xpos[B]['head'], float)
            n = float(np.linalg.norm(d))
            return d / n if n > 1e-6 else None

        for c in self.children.get(bone, []):
            if c not in upos:
                continue
            d = upos[c] - upos[bone]
            n = float(np.linalg.norm(d))
            if n < _MIN_AXIS_LEN:
                break                  # degenerate main chain, use the parent
            v = target_dir(bone, c)
            if v is not None:
                return d / n, v
            break

        par = self.rose_parent.get(bone)
        if par and par in upos:
            d = upos[bone] - upos[par]
            n = float(np.linalg.norm(d))
            if n > 1e-6:
                v = target_dir(bone, par)
                # the parent's *incoming* direction is the reverse of ours
                if v is not None:
                    return d / n, -v
        return None, None

    def _build_direct(self):
        """One source->target transform per bone that has a real counterpart."""
        self.direct = {}          # re8 bone -> (src_pos, dst_pos, R)
        self.n_axis_fallback = 0
        for b, p in self.rose_pos.items():
            if not is_direct_bone(b):
                continue
            B = map_bone(b)
            if B is None or B not in self.x4:
                continue
            q = np.asarray(self.x4[B]['head'], float)
            u, v = self._pair_axis(b, B)
            if u is None or v is None:
                # no anatomical direction available (pelvis, which coincides
                # with its own child): leave the bone unrotated rather than
                # inventing a 180 degree flip
                self.direct[b] = (self.src[b], q, np.eye(3))
                self.n_axis_fallback += 1
                continue
            self.direct[b] = (self.src[b], q, min_rotation(u, v))

    def _build_delta(self):
        """One transform per X4 bone; folding bones borrow their anchor's."""
        # every folding bone borrows the nearest same-side direct bone
        self.anchor = {}
        dn = list(self.direct)
        for b in self.rose_pos:
            if b in self.direct:
                self.anchor[b] = b
                continue
            side = b[0] if b[:2] in ('L_', 'R_') else None
            best, bd = None, 1e18
            for c in dn:
                if side and not c.startswith(side + '_'):
                    continue
                if not side and c[:2] in ('L_', 'R_'):
                    continue
                d = float(np.linalg.norm(self.src[b] - self.src[c]))
                if d < bd:
                    best, bd = c, d
            self.anchor[b] = best
            if best is None:
                self.anchor[b] = b

        self.delta = {}           # x4 bone -> (src_pos, dst_pos, R)
        for b, rec in self.direct.items():
            B = map_bone(b)
            if B is not None and B not in self.delta:
                self.delta[B] = rec
        # folding bones only fill in targets nothing direct maps to
        for b in self.rose_pos:
            if b in self.direct:
                continue
            B = map_bone(b)
            if B is None or B not in self.x4 or B in self.delta:
                continue
            a = self.anchor.get(b)
            if a in self.direct:
                self.delta[B] = self.direct[a]
        # order matters: harmonise first, so the eyeballs ride the adjusted
        # head transform rather than the raw one
        self._harmonise_head_neck()
        self._bind_eyes_to_head()
        if self.verbose:
            print('  bind transfer: %d direct bones, %d target bones, '
                  '%d without a bone axis' % (len(self.direct), len(self.delta),
                                              self.n_axis_fallback))

    def _harmonise_head_neck(self):
        """Give the neck and head chain one shared offset.

        X4's `Bip01 Head` sits 7.8 cm above `Bip01 Neck`; Rose's sits 13.7 cm
        above hers -- her neck is nearly twice as long.  Aligning each bone to
        its own target therefore drags the head 5.9 cm down while pushing the
        collar up, and the character ends up looking hunched into her jacket
        (measured: the eyeball-to-collar gap collapses from 7.5 cm as authored
        to 0.6 cm).  Splitting the difference puts each bone ~3 cm from its
        own target and restores the authored spacing.
        """
        neck = head = None
        for b, rec in self.direct.items():
            B = map_bone(b)
            if B == 'Bip01 Neck' and neck is None:
                neck = rec
            elif B == HEAD_BONE and head is None:
                head = rec
        if neck is None or head is None:
            return
        shared = 0.5 * ((neck[1] - neck[0]) + (head[1] - head[0]))
        for bone, rec in (('Neck', neck), ('Head', head)):
            src = rec[0]
            x4_bone = 'Bip01 Neck' if bone == 'Neck' else HEAD_BONE
            self.delta[x4_bone] = (src, src + shared, rec[2])
        self.head_neck_shared = float(np.linalg.norm(shared))

    def _bind_eyes_to_head(self):
        """Ride the eyeballs on the head transform rather than the eye bones.

        Rose's eyeball *geometry* sits about 5 cm below her `L_Eye`/`R_Eye`
        bones, while X4's `left_eye_dummy` sits 8.5 cm *above* `Bip01 Head` --
        a bone-anchored transfer therefore moves the eyeball only ~2 cm and
        leaves it buried in the cheek (in game: the eyes simply disappear).
        The eyeballs keep their eye_dummy weights, so gaze control still works;
        only their rest position follows the head, which is what keeps them in
        the sockets.
        """
        # read the *adjusted* head transform (harmonise runs first), otherwise
        # the eyeballs ride the raw one and stay sunk in the collar
        head = self.delta.get(HEAD_BONE)
        if head is None:
            for b, rec in self.direct.items():
                if map_bone(b) == HEAD_BONE:
                    head = rec
                    break
        if head is None:
            return
        hsrc, hdst, hR = head
        for rose_bone, x4_bone in (('L_Eye', 'left_eye_dummy'),
                                   ('R_Eye', 'right_eye_dummy')):
            rec = self.direct.get(rose_bone)
            if rec is None or x4_bone not in self.x4:
                continue
            src = rec[0]
            self.delta[x4_bone] = (src, hdst + hR @ (src - hsrc), hR)

    # ------------------------------------------------------------------ apply
    def merge_weights(self, weights, weighted_bones):
        """RE8 per-vertex weights -> {x4 bone: weight}, renormalised."""
        out = []
        for wl in weights:
            acc = {}
            for bid, w in wl:
                if bid >= len(weighted_bones):
                    continue
                B = map_bone(weighted_bones[bid])
                if B is None or B not in self.x4:
                    continue
                if B in EYE_CONTROLLERS:
                    B = HEAD_BONE
                acc[B] = acc.get(B, 0.0) + float(w)
            tot = sum(acc.values())
            out.append({k: v / tot for k, v in acc.items()} if tot > 1e-9 else {})
        return out

    def global_only(self, verts_m):
        V = np.array([rose_to_blender(p) for p in verts_m])
        return (self.scale * (self.R @ V.T)).T + self.t

    def transform(self, verts_m, weights, weighted_bones):
        """Return (N,3) vertices in X4/Blender space (cm)."""
        V = np.array([rose_to_blender(p) for p in verts_m])
        G = (self.scale * (self.R @ V.T)).T + self.t
        merged = self.merge_weights(weights, weighted_bones)

        n = len(verts_m)
        acc = np.zeros((n, 3))
        tot = np.zeros(n)
        by_bone = {}
        for i, d in enumerate(merged):
            for B, w in d.items():
                by_bone.setdefault(B, []).append((i, w))
        for B, items in by_bone.items():
            rec = self.delta.get(B)
            if rec is None:
                continue
            src, dst, R = rec
            idx = np.array([it[0] for it in items])
            w = np.array([it[1] for it in items])
            acc[idx] += w[:, None] * (dst + (G[idx] - src) @ R.T)
            tot[idx] += w
        ok = tot > 1e-9
        out = G.copy()
        out[ok] = acc[ok] / tot[ok][:, None]
        return out, int((~ok).sum()), len(self.delta)
