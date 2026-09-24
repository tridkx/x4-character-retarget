# Nexus mod page content

**Mod name**: `Rose Winters (RE8) - Argon Female NPC Replacer`

**Summary / tagline** (one line for the mod card):
`Resident Evil Village's Rose Winters replaces the Argon female NPC models in X4: Foundations.`

---

## Description (paste-ready, plain text)

```
Rose Winters (RE8) - Argon Female NPC Replacer

Replaces the Argon female NPC models in X4: Foundations with Rose Winters from
Resident Evil Village (Shadows of Rose). Built the standard X4 way -- swap the
meshes, keep the skeleton -- so it rides the vanilla shared rig and the full
shared animation set and modifies no game files.


VERSION
  1.1

GAME VERSION
  X4: Foundations 9.00 (built and tested on 9.00)


INSTALLATION

  1. Download x4_rose_mod_v1.1.zip

  2. Unpack it into the game's extensions folder, so you end up with:

       X4 Foundations\extensions\x4_rose_mod\
           content.xml
           ext_01.cat
           ext_01.dat

  3. Start the game, open the Extensions menu from the main menu, and enable
     "Rose Winters (RE8)".

  4. Load a save or start a new one and look at / hire an Argon female crew
     member.

  Note: an NPC's appearance is decided when it is created, so NPCs already
  standing in front of you will not change. Move to an area with Argon women
  (stations, your fleet) or hire new crew.


UNINSTALLATION

  Delete the extensions\x4_rose_mod folder, or just untick it in the Extensions
  menu. Nothing in the game is modified, so saves stay valid either way.


!! THIS BUILD REPLACES ALL ARGON FEMALE APPEARANCE POOLS !!

  So you do not have to hunt for the NPC that rolled Rose, this build replaces
  every Argon female appearance pool outright: every Argon woman you meet is
  Rose, instead of roughly one in four.

  Side effect: if you also run another mod that replaces Argon appearances
  (a 2B replacer, for example), its entries in those same pools get replaced by
  this one. Either run this mod alone, or rebuild it in append mode -- see
  "Want them to coexist" below.


KNOWN ISSUES AND LIMITATIONS

  Please read these. The animation binding is correct (limbs do not bend the
  wrong way), but this is not a 1:1 reproduction. Everything known to be wrong
  is listed here.

  1. Dark vertical stripes on the jacket
     These should be grey trim. A layer of card geometry on the coat (zip
     backing, metal fittings) samples a dark patch of the texture atlas through
     its own UVs. Improved but still visible.

  2. Hands and hair are rigid
     - The fingers are bound to the palm and do not move individually. That is
       the price of a correct hand shape: Rose's fingers are modelled together
       while the X4 skeleton splays them, and matching each finger to its own
       bone tears the web between thumb and index open.
     - The hair is bound to the head bone as a single piece and does not sway.
       The 91-bone X4 rig has no hair chain to bind to.
     - The toes sit about 5 cm from their bones. That is what keeps the soles
       flat on the ground (X4's toe bones are almost on the deck, and matching
       them lifts the heel 5 cm into the air).

  3. Hand surface is not perfectly smooth
     The rings that used to appear around the fingers are gone, but the normal
     map on the hands is still not as clean as vanilla's. Cause: the tangent
     space suffers when a hand is decimated, so the hands are no longer
     decimated at all, which removed most of it.

  4. Lower model detail than the source
     X4 renders NPCs instanced -- dozens on screen in a station -- so an asset
     has to stay near vanilla's ~5k vertices. This one ships at about 6x that,
     and the price is a face and clothing coarser than the source model.
     If your machine starts flickering in stations or the map locks up, VRAM is
     the bottleneck; lower your settings and please report it.

  5. Eyes read pale grey
     RE8 renders the iris and pupil from shader parameters. X4's material system
     only takes diffuse / normal / smoothness maps, so that layer cannot be
     carried over.

  6. Dark patches at the jacket cuffs
     Same cause as issue 1, milder.

  7. No facial expression or lip sync
     X4's procedural face system (facemods) and voice lip sync do not apply.
     Rose has a fixed face and a fixed expression.


COMPATIBILITY

  - Requires X4: Foundations 9.00 or newer.
  - Modifies no game files; coexists with most mods.
  - Conflicts with other Argon appearance replacers: this build overrides their
    entries (see the warning above).
  - Save safe: enable or disable at any time.


WANT THEM TO COEXIST / WANT TO CHANGE IT

  The whole pipeline and the reverse-engineering notes are open source (MIT):
  https://github.com/tridkx/x4-character-retarget

  The switch is at the top of tools/make_mod.py:

      REPLACE_ALL_ARGON_FEMALE = False   # append mode, about 1 in 4

  Set it to False, re-run that script, repack. The repository also has the full
  build documentation and a running engineering log.


REQUIREMENTS

  - A legitimate copy of X4: Foundations. This mod contains only converted
    assets, no game files.
  - To rebuild it from scratch you additionally need X Tools, X4 Character
    Converter, RE-Mesh-Editor and Blender.


CREDITS

  - X4 Character Converter by DiCrash / Orion -- without this exporter none of
    this would exist
  - RE-Mesh-Editor by Percyqaz and contributors
  - EGOSOFT's X Tools and the X4 modding documentation


LEGAL

  Resident Evil is a trademark of CAPCOM. X4: Foundations is a trademark of
  EGOSOFT. This is an unofficial fan work for personal use and contains no game
  assets from either title. The Rose Winters model and textures remain the
  property of CAPCOM.

  The tooling is released under the MIT licence (see the GitHub repository).
```
