# x4-character-retarget

Tooling and reverse-engineering notes for **retargeting a RE Engine character
(Resident Evil Village) onto the X4: Foundations NPC skeleton**, so it can
appear as an Argon female NPC in game.

> **Project status: research / unresolved.**
> The pipeline runs end to end and produces a loadable mod, but the result is
> **not usable in game yet**. Skinning error is ~20 cm against a ~1.9 cm
> vanilla baseline, which manifests as limbs bending the wrong way under
> animation. See [Status](#status) for the honest breakdown.

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
RE8 .mesh (weights)  ->  retarget onto the X4 skeleton  ->  .blend
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
| Texture pipeline | `NRMR` split into BC5 normal + BC4 smoothness, own BC1/BC3 encoder |
| Mod packaging | loads in game; no crash, no VRAM blowup, model appears |

### Not working

| Problem | Measurement |
|---|---|
| Limbs bend backwards under animation | skinning error **~20.6 cm** vs vanilla **1.86 cm** |
| Fingers stretch | same root cause |
| Eyes | eyeball overlays dropped, still needs work |

The geometry is in the right place at rest (head/hip/foot land within 2–8 cm of
their bones) but **hands and toes are 24–42 cm off**, so any animation drags
them the wrong way.

## Key technical findings

These are the parts worth keeping regardless of whether the retarget is
finished.

### 1. X4's model space, measured not assumed

Three coordinate conventions are in play and getting them crossed caused most
of the bugs:

| Space | Arrangement | Evidence |
|---|---|---|
| RE8 source | `(x, height, forward)` metres | skeleton JSON |
| X4 `.xac` | `(x, height, forward)` cm | vanilla hand mesh `Y[4,19] Z[81,100]`, hand bone `Y=6.8 Z=98.3` |
| Blender scene | `(x, -forward, height)` cm | importer's `xac_to_blender_vector`; `Bip01 Head z=161.4` |

`X4CharacterConverter` defines the rotation itself:

```python
xac_to_blender_vector(v) = (v.x, -v.z,  v.y)     # on import
blender_to_xac_vector(v) = (v.x,  v.z, -v.y)     # on export
```

Note these are **not** inverses — composing them yields `(x, -y, z)`, a Y
mirror. Treating "Blender space" and "XAC space" as interchangeable (as this
project did for a while) produces silently mirrored meshes.

### 2. Vanilla assets are the ground truth

Comparing against a vanilla asset is the only reliable check. The useful
metric is **mean distance from each vertex to the bone that dominates it**:

```
vanilla Hands_ter   ~1.9 cm      vanilla sweater  ~9.9 cm
```

Anything in the tens of centimetres means weights landed on bones that are
nowhere near the geometry.

### 3. `X4CharacterConverter` constraints

* Object names must match `[A-Za-z0-9_]+`; materials `[a-z0-9_]+\.[a-z0-9_]+`.
* It only *rebuilds* meshes whose `mesh_id` already exists in the template, so
  the exporter is pinned to the host asset's mesh-slot count.
* `write_package()` hardcodes every `.xac` into `bodies/` regardless of type.
* Its DDS reader looks for the DXGI format at byte 128 — which in a DX10 header
  is `dwSize` (=60), so **it only accepts legacy FourCC headers**
  (`DXT1`/`DXT5`/`ATI1`/`ATI2`).
* Textures are looked up by **Blender node name** (`Diffuse`, `Normal`,
  `Smoothness`), not by material property.

### 4. Rigid alignment is the right shape; patchwork affine fitting is not

An earlier revision fitted scale and offset *per body segment* while silently
mixing two axis arrangements. That collapsed the mesh to ~2 cm and then placed
it ~20 cm off. A single **Kabsch** fit over reliable bone pairs is well posed
and diagnoses cleanly:

```
scale = 1.034   t = (0.00, -7.30, 1.92)
Head  2.5 cm   Foot 6.9 cm   Hip 8.3 cm   Hand 41.9 cm   Toe 23.8 cm
```

The residual concentrates in the limbs, i.e. it is **pose**, not frame.

### 5. X4's geometry budget

Vanilla NPC assets are ~5 k vertices *per asset*. A RE8 character arrives at
340 k–359 k — roughly **73×** the budget. Unmodified this exhausts VRAM in
stations (flicker, map lock-ups, corrupted map tiles). Decimation ratios that
land near vanilla:

```python
{'hair': 0.05, 'jacket': 0.06, 'body': 0.10,
 'slingbelt': 0.10, 'hand_l': 0.55, 'hand_r': 0.55,
 'eyes': 0.50, 'face': 0.20}
```

## Tools

| Script | Purpose |
|---|---|
| `xcat.py` | index/read X4 `.cat`/`.dat` catalogs without unpacking |
| `xac.py` | `.xac` parser; byte-compares bone tables between two files |
| `re8_to_x4.py` | bone-name mapping rules (RE8 → X4 Biped) |
| `re_mesh_weights.py` | read positions + skin weights from a RE8 `.mesh` |
| `bc_encode.py` | BC1/BC3/BC4/BC5 DDS encoder (numpy; no texconv needed) |
| `tex_convert.py` | RE8 `_albd`/`_nrmr` → X4 Diffuse/Normal/Smoothness DDS |
| `build_rose_x4.py` | stage 1: extract, Kabsch align, pose-align, build `.blend` |
| `build_mod.py` | stage 2: fill host mesh slots, export `.xac` |
| `prepare_textures.py`, `x4_materials.py` | texture batch + material manifest |
| `make_mod.py` | assemble the mod tree and XML, ready for `XRCatTool` |
| `pose_align.py` | rotate limb vertices onto the bind pose (**work in progress**) |
| `calibrate.py`, `solve_frame.py`, `find_transform.py` | frame/alignment solvers |
| `preview_skeleton.py`, `preview_poses.py` | offline render checks |
| `trace_coords.py`, `trace_one_vertex.py`, `audit_frames.py` | coordinate tracing |

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

# 2. stage 1 — retarget (runs inside Blender, prints Kabsch residuals)
blender -b --factory-startup --python tools/build_rose_x4.py

# 3. textures (system Python — Blender's bundled build has no Pillow)
python tools/prepare_textures.py

# 4. stage 2 — export the .xac pair
blender -b --factory-startup --python tools/build_mod.py

# 5. assemble and pack
python tools/make_mod.py
XRCatTool.exe -in x4_rose_mod -out x4_rose_mod/ext_01.cat
```

Paths are currently absolute and point at the author's machine — see
`WORK`, `ADDON_DIR`, `RE8_MODELS` at the top of each script.

## Repo layout

```
tools/     pipeline + diagnostics
docs/      feasibility study and running engineering log
examples/  config templates
```

## Making it work

The open problem is the ~20 cm pose residual in the limbs. The productive next
step is **not** more manual axis tweaking (which is what stalled this project)
but to sweep `pose_align`'s knobs offline against the skinning-error metric:

* rotation axis derivation (currently from the mesh, may be off)
* ramp interval and minimum swing fraction
* which vertices participate

Everything needed to measure that is in `tools/` — `preview_skeleton.py`
renders bone wireframes over the mesh and is the most trustworthy single check.

## Licence / credits

Tooling here is original work released under the MIT Licence (see `LICENSE`).

It builds on other people's work and would not exist without them:

* **X4 Character Converter** by DiCrash / Orion
* **RE-Mesh-Editor** by the RE-Mesh-Editor contributors
* **EGOSOFT**'s X Tools and the X4 modding documentation

*Resident Evil* and *X4: Foundations* are trademarks of their respective
owners. No assets from either game, nor any third-party mod, are distributed
in this repository.
