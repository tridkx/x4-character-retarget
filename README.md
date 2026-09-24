# x4-character-retarget

> **中文说明**: [`README.zh-CN.md`](README.zh-CN.md)
> **Finished mod**: [Releases → `x4_rose_mod_v1.0.zip`](https://github.com/tridkx/x4-character-retarget/releases/download/v1.0/x4_rose_mod_v1.0.zip)

Tooling and reverse-engineering notes for **retargeting a RE Engine character
(Resident Evil Village) onto the X4: Foundations NPC skeleton**, so it can
appear as an Argon female NPC in game.

This repo holds the **pipeline scripts and the findings**, not the built mod --
binary assets stay out of git history and ship as a
[release](../../releases) attachment instead.

## Installing the mod

1. Download `x4_rose_mod_v1.0.zip` from [Releases](../../releases)
2. Unpack into `X4 Foundations/extensions/` so you get `extensions/x4_rose_mod/`
3. Enable it in the game's *Extensions* menu

This build is in **test mode**: every Argon-female appearance pool is replaced
outright, so every Argon woman you meet is Rose. To run alongside other mods of
the same kind, set `REPLACE_ALL_ARGON_FEMALE = False` in `tools/make_mod.py`
and rebuild (append mode, ~1 in N).

Requires a legitimate copy of X4: Foundations (developed against 9.00). The
release contains only converted assets, no game files.

> **Project status: retarget solved offline; in-game re-test pending.**
> The skinning error that stalled this project (~20 cm, limbs bending the
> wrong way under animation) is fixed. Measured mean distance from each vertex
> to the bone that dominates it, at the same measurement setup as vanilla:
>
> | asset | before | after | vanilla reference |
> |---|---|---|---|
> | fingers | 23.9 cm | **1.03 cm** | 1.11 cm |
> | toes | 27.9 cm | **4.28 cm** | 4.36 cm |
> | palms | 17.3 cm | **4.67 cm** | 5.34 cm |
> | forearms | 7.5 cm | **4.87 cm** | 6.49 cm |
> | whole body | 17.2 cm | **6.89 cm** | 7.17 cm |
>
> Pose tests (elbow/knee/spine rotations rendered offline) now match vanilla's
> behaviour; pose-by-pose comparison renders are in `work/preview/posetest/`.
> What has *not* happened yet is a fresh in-game check.

---

## What this project does

X4 NPCs are replaced by swapping *meshes* while keeping the vanilla *skeleton*:
`libraries/character_macros.xml` picks a head/torso/props mesh, and every Argon
female NPC shares one `character_argon_female_01` component that owns the bones
and animations. So a replacement only has to carry the same 91-bone Biped rig
with byte-identical bind data — and X4 ships an official Blender plugin,
**X4 Character Converter**, that imports a vanilla `.xac`, lets you edit it, and
writes a new one back out.

This repo provides the RE Engine -> X4 half of that pipeline:

```
RE8 .mesh (weights)  ->  bind-pose transfer onto the X4 skeleton  ->  .blend
                     ->  X4CharacterConverter export   ->  .xac + DDS + xml
                     ->  XRCatTool pack                ->  ext_01.cat
```

## Status

### Verified working

| Piece | Result |
|---|---|
| XAC parsing / skeleton comparison | `xac.py` — byte-compares two `.xac` bone tables |
| Bone name mapping (RE8 → X4 Biped) | 240 rules, **100 % hit rate** on all 8 body parts |
| Skin weight recovery | read straight from RE8 `.mesh` (the existing export tooling dropped them) |
| Retarget onto the X4 bind pose | per-bone transfer; **6.89 cm** mean vertex→bone error vs vanilla **7.17 cm** |
| Pose behaviour | elbow / knee / walk / twist renders match vanilla |
| Eyes | real eyeball (in the face mesh) in the socket; head-bound so look-at cannot swing it out |
| Shading | smooth normals all the way to the .xac (both stages set `use_smooth`), which also cut exported vertices by 70% |
| Skeleton compatibility | 91/91 bind payloads **byte-identical** to vanilla in both exported assets |
| Texture pipeline | `NRMR` split into BC5 normal + BC4 smoothness, own BC1/BC3 encoder |
| Mod packaging | loads in game; no crash, no VRAM blowup, model appears |

### Remaining

| Item | State |
|---|---|
| In-game re-test | mod is installed in `extensions/x4_rose_mod` |
| **Hands and hair are rigid** | fingers are bound to the palm and hair to `Bip01 Head`, so neither moves on its own. Deliberate: see "Known compromises" below. |
| **Hand surface still not perfectly smooth** | much better since the hands stopped being decimated, but the normal map on the fingers is still not as clean as vanilla's |
| Eyeball shading | RE8 drives the iris from shader params; X4 only takes diffuse/normal/smoothness, so the eye reads pale grey |
| Vertex budget | kept near 6x vanilla per asset; 15x brought back the in-station flicker |
| Long hair | bound to `Bip01 Head` — the X4 Biped has no hair chain, so it moves rigidly with the head |
| Cloth bones | `jacket_*` collapse onto the spine; there is no per-strand cloth simulation |

### Known compromises

Three of these are deliberate trades rather than open bugs -- each one bought a
visible defect somewhere else:

| Compromise | What it fixed | What it costs |
|---|---|---|
| Fingers bind to the palm (`FINGERS_BIND_TO_PALM`) | the web between thumb and index tore open to the base of the palm, because Rose authors the fingers together and the X4 biped splays them | fingers do not animate individually; an NPC never shows it |
| Hair binds to `Bip01 Head` | there is no hair chain in the 91-bone Biped to bind to | hair is a rigid shell that turns with the head |
| Feet share the ankle's offset (`_feet_share_one_offset`) | per-bone offsets levered the foot, hanging the heel 5.4 cm above the deck | toes sit ~5 cm from their bones |
| Camera-frustum-free decimation ratios | the vertex budget, which X4 punishes with station-wide flicker | faces and hands are coarser than the source |

The hand's normal map is the one item here that is still a defect rather than a
trade: tangents follow UVs, so any decimation on a hand rewrites the finger UVs
and the normal map loses its footing. The hands are no longer decimated at all,
which removed the worst of it (rings around the fingers), but the remaining
roughness suggests the tangent basis is still not clean -- the next thing to
try is exporting tangents explicitly rather than letting the add-on derive them.

## Key technical findings

These are the parts worth keeping regardless of the specific character.

### 1. X4's model space, measured not assumed

| Space | Arrangement | Evidence |
|---|---|---|
| RE8 source | `(x, up, forward)` metres, +x = character's left | eyeballs sit at +z, toes at +z |
| X4 `.xac` / Blender | `(x, forward, up)` cm, +x = character's left | `left_eye_dummy` at y=+4.8 and `Toe0` at y=+6.9, both on the +y side of `Bip01 Head` (y=-3.9) |

So the frame conversion is `(x, up, forward) -> (x, forward, up)`, **keeping the
forward axis positive**. This pipeline negated it for a long time, which mirrors
the character front-to-back. The torso barely notices (it is nearly symmetric),
but the hands land 42 cm and the toes 23 cm from their bones — and because a
mirror is a reflection, no rotation-only Kabsch fit can repair it. That single
sign is what turned "limbs bend backwards" into a 20 cm residual that looked
like a pose problem.

### 1b. …but that mapping is a reflection, so the winding must be reversed

Swapping two axes is `det = -1`. Vertex positions come out right while every
triangle now faces inwards, and the engine culls outward faces: clothes turn
see-through (you see the far inner shell), shading reads as crumpled fabric,
and the face vanishes entirely. Compensate by reversing the index order of
every triangle (`(a, b, c) -> (c, b, a)`) when the mesh is built; UVs are
unaffected because they are carried per vertex/loop.

This is invisible to any position-based check — the geometry is exactly where
it should be. `tools/check_normals.py` is the guard: it reports, per mesh, the
fraction of faces pointing away from the centroid (vanilla assets sit at
0.59–0.77, a flipped mesh lands just under 0.5).

### 2. A single rigid transform cannot retarget between two rigs

Even with the frame right, one Kabsch fit over matched bones leaves the torso
within a few cm but the hands 25 cm and the toes 11 cm out, because the two
rigs differ in pose *and* proportions (the X4 Biped's torso is ~15 cm and its
arm ~20 cm longer than Rose's). Skinning is defined against the bind pose, so
those residuals are exactly the "arm swings the wrong way" symptom.

`retarget_core.BindPoseRetarget` builds **one transform per X4 bone** — position
from the matched source bone, rotation from source bone axis to target bone
axis — and moves each vertex by the weighted blend of the transforms of the
bones that skin it. The X4 skeleton itself is never touched.

### 3. Deriving bone axes: never average the children

A bone axis must come from the **first child on the main chain**, computed the
same way on both rigs, with the parent direction as the fallback and "no
rotation" as the last resort.  Averaging the children looks reasonable and is
badly wrong on any forking bone: Rose's `Hip` owns a coincident `Spine_0` plus
both thighs, so the average points *down* while the X4 pelvis points *up*, and
the fit produced a **161° pelvis rotation** that flipped every jacket hem,
trouser and boot vertex weighted to it (visible in game as a pale patch across
the waist — the flipped inner surface sampling a different part of the atlas).

Sanity check: nearly every bone should come out under 60°.  Clean 90°/180°
values mean the axis convention is wrong, not that the pose differs.

### 4. The RE8 skeleton has no single local-axis convention

Bone axes must be derived from *child bone positions*, not from the bone
matrix: in Rose's rig the spine's axis sits in matrix row 0 (pointing +x) while
the upper arm's is also row 0 but along the limb — feeding rows straight into a
rotation fit spun the spine by exactly 90° and the left fingers by 172°, while
the mirrored right hand looked fine. Using `mean(child positions) - position`
on both skeletons gives a consistent, symmetric result.

### 5. Vanilla assets are the ground truth

Comparing against a vanilla asset is the only reliable check. The useful metric
is **mean distance from each vertex to the bone that dominates it**:

```
vanilla Hands_ter   ~1.1 cm      vanilla body asset  ~7.2 cm
```

Anything in the tens of centimetres means weights landed on bones that are
nowhere near the geometry.

### 6. Folding bones need an anchor

`jacket_*`, `Hair*_FK_*`, `*_Twist_*` and the facial bones have no positional
counterpart in the X4 rig — they only *share* a bone. Giving them the transform
of the bone they map onto drags a jacket 30 cm into the ribcage; they must
inherit the transform of the nearest same-side bone that does have a
counterpart (`re8_to_x4.is_direct_bone`).

Related mapping bug worth remembering: `jacket_<N>_<M>` has **N = radial index
around the torso** and **M = distance down the chain** (every chain hangs off
`Spine_2`; `M=0` sits at z≈127, `M=3` at z≈100). The original rules keyed off N,
binding the hem to the neck.

### 7. `X4CharacterConverter` constraints

* Object names must match `[A-Za-z0-9_]+`; materials `[a-z0-9_]+\.[a-z0-9_]+`.
* It only *rebuilds* meshes whose `mesh_id` already exists in the template, so
  the exporter is pinned to the host asset's mesh-slot count.
* `write_package()` hardcodes every `.xac` into `bodies/`.
* `export_package()` **refuses to write into an existing directory** — and only
  after the meshes have been built, so a second run silently leaves the old
  `.xac` in place and every downstream check looks stale. `build_mod.py` clears
  the target first.
* Its DDS reader looks for the DXGI format at byte 128 — which in a DX10 header
  is `dwSize` (=60), so **it only accepts legacy FourCC headers**
  (`DXT1`/`DXT5`/`ATI1`/`ATI2`).
* Textures are looked up by **Blender node name** (`Diffuse`, `Normal`,
  `Smoothness`), not by material property.

### 8. X4's geometry budget

Vanilla NPC assets are ~5 k vertices *per asset*. A RE8 character arrives at
340 k–359 k — roughly **73×** the budget, and unmodified that exhausts VRAM in
stations (flicker, map lock-ups, corrupted map tiles). The exporter's vertex
count includes UV/normal seams, so compare like with like: this character
ships at **~8.5×** vanilla (~71 k across both assets). 15× brought the flicker
back; the numbers below are the ones that held:

```python
{'hair': 0.10, 'jacket': 0.35, 'body': 0.30,
 'slingbelt': 0.70, 'hand_l': 0.75, 'hand_r': 0.75,
 'eyes': 0.50, 'face': 0.50}
```

The exported count includes a vertex per UV *and normal* seam, so smooth normals
are worth as much as decimation: emitting them cut the total by 70% and paid
for the much denser mesh above. The character now ships at **6.1x** vanilla
with about 2.3x the triangles of the previous 8.3x build.

Two more things sit between the retarget and a usable asset:

* **Hands are not decimated at all.**  Tangents follow UVs, so collapsing a
  hand rewrites the finger UVs and the normal map renders as rings around the
  fingers and dark blotches at the knuckles.  They are only 2346 vertices
  each; keeping them intact costs ~4k and removes the artefact.
* **Fingers bind to the palm.**  Rose authors her fingers together, the X4
  biped splays them, and the web between thumb and index is only skin bridging
  two fingers -- matching each finger to its own bone prises them apart until
  it looks like a piece is missing.  Binding them to the palm keeps the hand
  as authored; individual fingers no longer animate, which an NPC never shows.
* **Soles.** X4's toe bones are almost on the ground (Toe0 z = 0.12 against a
  11.55 ankle) while Rose's are 6 cm above it, so binding toe geometry to them
  buries the shoes ~3.5 cm. `lift_feet()` raises the foot-weighted vertices
  afterwards; the toes give up that much accuracy, which is invisible, and the
  boots stop sinking into the deck.
* **Eyes.** Rose's eyeball *geometry* sits 4.9 cm below her eye bones, so a
  bone-anchored transfer leaves it inside the cheek (the eyes vanish). The
  eyeballs ride the head transform instead while keeping their eye-dummy
  weights, so gaze still works.

## How the retarget works

`tools/retarget_core.py` in four steps:

1. **Frame fit** — one Kabsch similarity over 18 unambiguous bone pairs puts the
   source rig in X4 space (`scale≈1.047`, `det(R)=+1`).
2. **Per-bone transform** — for every source bone that has an X4 counterpart:
   `x -> q_B + R_B (x - p_b)`, with `R_B` the shortest rotation from the source
   bone axis to the target bone axis, both axes computed as
   `mean(child positions) - position`.
3. **Anchoring** — folding bones inherit the nearest same-side direct bone's
   transform.
4. **Blend** — each vertex moves by `Σ w_B · T_B(x) / Σ w_B`, i.e. linear blend
   skinning applied once at conversion time. This is what stretches the
   geometry to the X4 proportions instead of leaving it 25 cm off the bones.

Nothing about the skeleton, the weights' bone names, or the material slots
changes, so the exported asset still rides the shared vanilla skeleton.

## Tools

| Script | Purpose |
|---|---|
| `xcat.py` | index/read X4 `.cat`/`.dat` catalogs without unpacking |
| `xac.py` | `.xac` parser; byte-compares bone tables between two files |
| `re8_to_x4.py` | bone-name mapping rules (RE8 → X4 Biped) + direct/folding split |
| `retarget_core.py` | **the retarget**: global frame fit + per-bone bind transfer |
| `re_mesh_weights.py` | read positions + skin weights from a RE8 `.mesh` |
| `bc_encode.py` | BC1/BC3/BC4/BC5 DDS encoder (numpy; no texconv needed) |
| `tex_convert.py` | RE8 `_albd`/`_nrmr` → X4 Diffuse/Normal/Smoothness DDS |
| `build_rose_x4.py` | stage 1: extract, retarget, decimate, build `.blend` |
| `build_mod.py` | stage 2: fill host mesh slots, export `.xac` |
| `prepare_textures.py`, `x4_materials.py` | texture batch + material manifest |
| `make_mod.py` | assemble the mod tree and XML, ready for `XRCatTool` |
| `verify_mod.py` | pre-flight check: XML, diff XPaths, pool coverage, assets, skeleton |
| `check_normals.py` | per-mesh outward-facing ratio — catches flipped triangle winding |
| `dump_asset.py` | export a `.xac`'s bones + skinned meshes to `.npz` for analysis |
| `preview_skeleton.py` | bone wireframe over the mesh (most trustworthy single check) |
| `preview_pose_test.py` | render a `.xac` or `.blend` under test poses (elbow/knee/walk/…) |
| `diag_binding.py` | per-mesh vertex→dominant-bone distance |

Historical diagnostics from the coordinate-hunting phase (still useful when a
*new* asset misbehaves): `calibrate.py`, `solve_frame.py`, `find_transform.py`,
`audit_frames.py`, `trace_coords.py`, `trace_one_vertex.py`,
`visual_transform_test.py`, `diag_hand.py`, `pose_align.py` (superseded — see
`docs/萝丝移植进展.md` §11).

## Requirements

* **X4: Foundations** (developed against 9.00) with
  [X Tools](https://www.egosoft.com/download/x4/bonus_en.php) — `XRCatTool.exe`
* [X4 Character Converter](https://www.nexusmods.com/x4foundations/mods/2152)
  (Blender add-on; developed against v0.8.7 on Blender 5.2)
* [RE-Mesh-Editor](https://github.com/Percyqaz/RE-Mesh-Editor) for reading RE
  Engine `.mesh` files
* Blender 4.2+ (tested on 5.2 LTS), Python 3.13, numpy, Pillow

No game assets are included here; you must extract them yourself with the
tools above.

## Usage

```bash
# 1. index the game's catalogs and pull the vanilla reference assets
python tools/xcat.py            # edit DEFAULT_GAME at the top first

# 2. stage 1 — retarget (runs inside Blender, prints the frame fit and transfer)
blender -b --factory-startup --python tools/build_rose_x4.py

# 3. textures (system Python — Blender's bundled build has no Pillow)
python tools/prepare_textures.py

# 4. stage 2 — export the .xac pair
blender -b --factory-startup --python tools/build_mod.py

# 5. assemble and pack  (note: -out must end in .cat)
python tools/make_mod.py
XRCatTool.exe -in x4_rose_mod -out x4_rose_mod/ext_01.cat

# 6. verify before shipping: XML, pool coverage, assets, skeleton compatibility
python tools/verify_mod.py
blender -b --factory-startup --python tools/check_normals.py -- <rose_body.xac> <rose_head.xac>
blender -b --factory-startup --python tools/preview_pose_test.py -- <rose.xac> new
```

Paths are currently absolute and point at the author's machine — see
`WORK`, `ADDON_DIR`, `RE8_MODELS` at the top of each script.

### Test mode: every Argon woman is Rose

While testing you do not want to hunt for the one NPC in four that rolled
Rose. `make_mod.py` has a switch:

```python
REPLACE_ALL_ARGON_FEMALE = True    # False = append her as one random option
```

With it on, every Argon-female appearance pool is **replaced** (not appended
to), using pools auto-discovered from the vanilla `charactergroups.xml` rather
than a hardcoded list — that catches the faction-specific pools
(`antigone.*`, `hatikvah.*`) a fixed list misses:

```
argon.allraces                   96 entries (mixed pool, replaced too)
argon.factiondiplomat.female      1
antigone.factiondiplomat.female   1
hatikvah.factiondiplomat.female   1
argon.service.female              3
argon.marine.female               3
argon.civilian.female             6
argon.pilot.female                3
argon.commander.female            3
```

Mixed developer pools (`benchmark`, `testcharacter`) are deliberately left
alone. `verify_mod.py` replays the diffs against the vanilla library and
asserts each pool resolves to Rose and nothing else.


## Repo layout

```
tools/     pipeline + diagnostics
docs/      feasibility study and running engineering log
examples/  config templates
```

Shared assets (the unpacked game root, the Blender add-on, reference mods) live
in the workspace's `shared/` directory rather than here, and the scripts refer
to them through a `SHARED` variable.  For how to lay out a second X4 mod, see
[§1.3 multi-project workspace](https://github.com/tridkx/dsh-skill-x4-npc-replacement-mod/blob/main/references/00-scope-and-pipeline.md#13-建议的工程布局).

## Licence / credits

Tooling here is original work released under the MIT Licence (see `LICENSE`).

It builds on other people's work and would not exist without them:

* **X4 Character Converter** by DiCrash / Orion
* **RE-Mesh-Editor** by the RE-Mesh-Editor contributors
* **EGOSOFT**'s X Tools and the X4 modding documentation

*Resident Evil* and *X4: Foundations* are trademarks of their respective
owners. No assets from either game, nor any third-party mod, are distributed
in this repository.
