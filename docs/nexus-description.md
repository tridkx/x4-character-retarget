# Nexus mod page content

**Mod name**: `Rose Winters (RE8) - Argon Female NPC Replacer`

**Summary / tagline** (one line for the mod card):
`Resident Evil Village's Rose Winters joins (or replaces) the Argon female NPC models in X4: Foundations.`

**Two files, two shapes** -- the mod ships in both, and the file name says which
is which:
* `x4_rose_argon_add_v1.3.zip` -- **add** (the normal build): Rose is one more
  random candidate in the Argon female appearance pools.
* `x4_rose_argon_replace_v1.2.zip` -- **replace** (test build): every Argon
  woman becomes Rose, story and mission NPCs included.

---

## Description (paste-ready, plain text)

```
Rose Winters (RE8) - Argon Female NPC Replacer

Brings Rose Winters from Resident Evil Village (Shadows of Rose) into
X4: Foundations as an Argon female NPC model. Built the standard X4 way -- swap
the meshes, keep the skeleton -- so it rides the vanilla shared rig and the full
shared animation set and modifies no game files.

There are two downloads of the same mod. Pick one; do not install both.


WHICH FILE DO I WANT?

  x4_rose_argon_add_v1.3.zip   <- normal play, start here
    Rose JOINS the Argon female appearance pools as one more random candidate.
    Every vanilla model is left in place, so the other Argon women keep their
    own faces, names and voices. She is about one in four of the women that job
    spawns (one in seven in the civilian pool, which has six candidates).
    Story and mission NPCs never come from an appearance pool, so they keep
    their vanilla appearance.

  x4_rose_argon_replace_v1.2.zip
    Rose REPLACES the Argon female appearance pools outright: every Argon woman
    you meet is Rose. This is the build for inspecting the model everywhere at
    once (and it is the one that makes story NPCs Rose too). It overrides any
    other Argon appearance replacer you may have installed.


VERSION
  add     1.3
  replace 1.2

GAME VERSION
  X4: Foundations 9.00 (built and tested on 9.00)


INSTALLATION

  1. Download the zip you want.

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

  The two builds write the same file names, so switching between them means
  replacing the folder contents -- not merging them.


UNINSTALLATION

  Delete the extensions\x4_rose_mod folder, or just untick it in the Extensions
  menu. Nothing in the game is modified, so saves stay valid either way.


HOW THE "ADD" BUILD WORKS

  One new NPC macro is appended (it inherits the vanilla base macro, so her
  race/gender identification, eye positions and face-shaping all still run),
  and one line is added to each of the six Argon female appearance pools:

    civilian, commander, marine, pilot, service, factiondiplomat

  Not a single vanilla macro and not a single existing pool entry is removed.
  The pools are read from the game itself, so a pool added by a DLC would be
  picked up rather than missed. Faction pools that merely route to these (for
  example the Antigone and Hatikvah diplomat pools) need no entry of their own.

  A stray "replace" where an "add" belongs is exactly the mistake this build has
  to avoid: it would quietly turn "one more option" back into "the only option",
  and no screenshot would ever show it unless you happened to be looking at a
  story NPC. The project's pre-flight check asserts the difference for both
  builds, so the two cannot drift into each other.


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
  - The ADD build sits alongside other Argon appearance replacers: it only
    appends a candidate to those pools, so you and they share them -- the more
    replacers you stack, the lower each one's share of the spawns.
  - The REPLACE build overrides other Argon appearance replacers (see above):
    run it on its own.
  - Save safe: enable or disable at any time.


REQUIREMENTS

  A legitimate copy of X4: Foundations. This mod contains only converted assets,
  no game files.


AI USAGE

  The tooling behind this mod -- the reverse-engineering analysis, the skeleton
  retargeting algorithm, the texture and packaging pipeline -- was written with
  the help of an AI assistant. The design decisions, the in-game testing and the
  diagnosis of every issue were done by the author; the AI implemented the code
  and analysed the data.

  The project keeps a full git commit history and a round-by-round engineering
  log, which serves as the development record.

  The model and textures are taken from the game and converted; they are not
  AI-generated.


CREDITS

  - X4 Character Converter by DiCrash / Orion -- without this exporter none of
    this would exist
    https://www.nexusmods.com/x4foundations/mods/2152
  - RE-Mesh-Editor by Percyqaz and contributors
  - EGOSOFT's X Tools and the X4 modding documentation

  (These are the tools used to build this mod.  Players do not need to install
  any of them.)


LEGAL

  Resident Evil is a trademark of CAPCOM. X4: Foundations is a trademark of
  EGOSOFT. This is an unofficial fan work for personal use and contains no game
  assets from either title. The Rose Winters model and textures remain the
  property of CAPCOM.
```
