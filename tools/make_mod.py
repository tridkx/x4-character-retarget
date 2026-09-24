# -*- coding: utf-8 -*-
"""
Assemble the finished X4 mod from the two exported packages.

    python tools/make_mod.py --race argon --mode add       # -> work/x4_rose_argon_add
    python tools/make_mod.py --race argon --mode replace   # -> work/x4_rose_argon_replace
    # then pack:  XRCatTool.exe -in work/x4_rose_argon_add \
    #                          -out work/x4_rose_argon_add/ext_01.cat

Two independent choices, both on the command line
-------------------------------------------------
`--mode` picks the shape:

* **add** (default) -- the Rose macro is appended to each Argon-female
  appearance pool as one more candidate.  Every vanilla macro is left alone,
  so she takes 1/(N+1) of the spawns in that job and the other women keep
  their vanilla faces, names and voices.  Story/plot NPCs, which no pool
  reaches, are untouched.
* **replace** -- the older total-conversion shape: the whole pool node is
  rewritten to select Rose only, so *every* Argon woman is Rose.  That is what
  you want while testing a fresh retarget (any NPC you look at shows the
  model), and the wrong default for anything else.

`--race` picks who she replaces.  Both races share
`character_argon_female_01`, so the meshes and the whole animation set work
unchanged; what changes is the base macro she refs (that is where her `race`
flag comes from) and which faction's pools she joins.  Terran women are served
by the Terran *and* Pioneer pools, hence two prefixes for one race.

The two shapes must not overwrite each other, hence two directories: the
release ships them side by side.

Layout produced
---------------
    x4_rose_<race>_<mode>/
      content.xml
      libraries/charactergroups.xml     <- Rose in every <race>-female pool
      libraries/character_macros.xml    <- the Rose NPC macro
      libraries/material_library.xml    <- our own collection
      assets/characters/<race>/rose/... <- XAC + textures

Both `rose_head` and `rose_body` packages land in one extension, because X4
loads extensions by id (`ext_01.cat`), not per asset.
"""

import os
import re
import shutil
import sys

WORK = r"D:\dsh-x4\work"
PKG = os.path.join(WORK, "x4cc_pkg")
MOD_ID = "x4_rose_mod"

#: Both races this mod can target.  They share `character_argon_female_01`
#: (skeleton + animations), so the meshes are identical between the two; the
#: base macro -- the source of her `race` flag -- and the pool prefixes are
#: what differ.
RACES = {
    'argon': {
        'base_macro': 'character_argon_female_cau_base_01_macro',
        'macro': 'character_argon_female_rose_macro',
        'pools': ('argon.',),
        'label': 'Argon',
        'label_cn': '阿贡（Argon）',
    },
    'terran': {
        'base_macro': 'character_terran_female_cau_base_01_macro',
        'macro': 'character_terran_female_rose_macro',
        'pools': ('terran.', 'pioneers.'),
        'label': 'Terran / Pioneer',
        'label_cn': '泰伦（Terran）与先驱者（Pioneers）',
    },
}

#: resolved by main() from --race / --mode
RACE = None
MODE = 'add'
MOD = None
ASSET_BASE = None
MACRO_NAME = None

#: Vanilla pool list, used to discover every female appearance pool instead of
#: hardcoding names (the pools are nested: `argon.trader.female` points at
#: `argon.civilian.female`, which is the one listing real macros).
VANILLA_GROUPS = os.path.join(WORK, 'vanilla', 'libraries',
                              'charactergroups.xml')

#: macro name fragments that identify a vanilla female appearance
FEMALE_MACRO_RE = re.compile(r'^character_arg(?:on)?_f(?:emale)?_', re.I)


def configure(race, mode):
    """Bind the module-level names the writers use.  Called once by main()."""
    global RACE, MODE, MOD, ASSET_BASE, MACRO_NAME
    RACE = RACES[race]
    MODE = mode
    MOD = os.path.join(WORK, 'x4_rose_%s_%s' % (race, mode))
    ASSET_BASE = ('extensions/%s/assets/characters/%s/rose'
                  % (MOD_ID, race))
    MACRO_NAME = RACE['macro']
    return MOD


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


# --------------------------------------------------------------------------

def merge_assets():
    """Copy both packages' assets into the mod tree."""
    dst_root = os.path.join(MOD, 'assets', 'characters',
                            RACE['base_macro'].split('_')[1], 'rose')
    if os.path.exists(dst_root):
        shutil.rmtree(dst_root)
    os.makedirs(dst_root, exist_ok=True)

    xacs, textures = [], {}
    # the macro references <base>/heads/rose_head and <base>/bodies/rose_body,
    # so XACs are re-homed into heads/ and bodies/ while textures stay flat
    # the converter's write_package() hardcodes every XAC into bodies/ (it has
    # no notion of the head/torso split), so re-home them by name here.
    XAC_DEST = {'rose_head.xac': 'heads', 'rose_body.xac': 'bodies'}
    for pkg in ('rose_head', 'rose_body'):
        src = os.path.join(PKG, pkg, 'assets', 'characters', 'mycharacters')
        for root, _dirs, files in os.walk(src):
            for fn in files:
                sp = os.path.join(root, fn)
                if fn.endswith('.xac'):
                    sub = XAC_DEST.get(fn) or ('heads' if 'head' in fn.lower() else 'bodies')
                    dp = os.path.join(dst_root, sub, fn)
                else:
                    dp = os.path.join(dst_root, 'textures', fn)
                os.makedirs(os.path.dirname(dp), exist_ok=True)
                shutil.copyfile(sp, dp)
                if fn.endswith('.xac'):
                    xacs.append(dp)
                else:
                    textures[fn] = dp
    return xacs, textures


def merge_material_library(textures):
    """Merge the two generated material libraries and fix the placeholder paths."""
    collections = {}
    for pkg in ('rose_head', 'rose_body'):
        p = os.path.join(PKG, pkg, 'libraries', 'material_library.xml')
        if not os.path.exists(p):
            continue
        body = read(p)
        for m in re.finditer(r'<collection name="([^"]+)">(.*?)</collection>',
                             body, re.S):
            name, inner = m.group(1), m.group(2)
            block = collections.setdefault(name, {})
            for mm in re.finditer(r'<material name="([^"]+)".*?</material>',
                                  inner, re.S):
                block[mm.group(1)] = mm.group(0)

    if not collections:
        raise RuntimeError('no material collections found in the exported packages')

    # point every texture reference at our real asset path
    def fix_path(match):
        stem = match.group(1)
        return ('value="%s\\textures\\%s"'
                % (ASSET_BASE.replace('/', '\\'), stem))

    out = ["<?xml version='1.0' encoding='utf-8'?>", '<diff>',
           '  <add sel="/materiallibrary" pos="prepend">']
    total = 0
    for coll, mats in sorted(collections.items()):
        out.append('    <collection name="%s">' % coll)
        for mname in sorted(mats):
            block = mats[mname]
            block = re.sub(r'value="PUT_YOUR_TEXTURE_PATH_HERE\\([^"]+)"',
                           fix_path, block)
            out.append('      ' + block.strip())
            total += 1
        out.append('    </collection>')
    out += ['  </add>', '</diff>', '']
    write(os.path.join(MOD, 'libraries', 'material_library.xml'),
          '\n'.join(out))
    return total


def write_content():
    race = RACE['label']
    if MODE == 'replace':
        desc = ('Replaces every %s female NPC model with Rose Winters from '
                'Resident Evil Village (test build: all appearance pools).'
                % race)
        cdesc = ('%s女性 NPC 全部替换为《生化危机8》的成年萝丝（测试版：覆盖所有外观池）。'
                 % RACE['label_cn'])
    else:
        desc = ('Adds Rose Winters from Resident Evil Village as one more %s '
                'female NPC model, chosen at random from the appearance '
                'pools.' % race)
        cdesc = ('%s女性 NPC 有几率以《生化危机8》的成年萝丝形象出现（其余女性保持原样）。'
                 % RACE['label_cn'])
    text = '''<?xml version="1.0" encoding="utf-8"?>
<content id="{id}" name="Rose Winters (RE8)" version="120" date="2026-09-24" save="0"
         description="{desc}">
  <text language="7"  name="Rose Winters (RE8)" description="{desc}"/>
  <text language="44" name="Rose Winters (RE8)" description="{desc}"/>
  <text language="86" name="罗丝·温特斯 (RE8)" description="{cdesc}"/>
</content>
'''.format(id=MOD_ID, desc=desc, cdesc=cdesc)
    return write(os.path.join(MOD, 'content.xml'), text)


def discover_female_pools():
    """Return [(pool, n_vanilla_selects, pure)] for the pools to write into.

    A pool qualifies when its name is `<race>.*` + `.female` and it selects at
    least one female macro.  Pools that only point at other pools
    (`argon.trader.female` -> `argon.civilian.female`) are skipped: they are
    routers, and in `add` mode a router needs no entry because the leaf it
    points at gets one; in `replace` mode rewriting the leaf covers them too.
    Mixed pools that list men and women together (`benchmark`, `testcharacter`
    -- developer/benchmark groups, not appearance pools) are left alone because
    they are not `<race>.` groups.
    """
    if not os.path.exists(VANILLA_GROUPS):
        print('  !! %s missing, falling back to a fixed pool list'
              % VANILLA_GROUPS)
        return [(p, 0, True) for p in ('argon.pilot.female',
                                       'argon.service.female',
                                       'argon.marine.female',
                                       'argon.commander.female',
                                       'argon.civilian.female',
                                       'argon.factiondiplomat.female')]
    text = read(VANILLA_GROUPS)
    out = []
    for m in re.finditer(r'<character\s+name="([^"]+)"\s*>(.*?)</character>',
                         text, re.S):
        name, body = m.group(1), m.group(2)
        macros = re.findall(r'<select\s+macro="([^"]+)"', body)
        if not macros:
            continue
        females = [x for x in macros if FEMALE_MACRO_RE.match(x)]
        if not females:
            continue
        pure = len(females) == len(macros)
        if pure and name.endswith('.female') \
                and name.startswith(RACE['pools']):
            out.append((name, len(macros), pure))
    return out


def write_charactergroups():
    pools = discover_female_pools()

    lines = ['<?xml version="1.0" encoding="utf-8"?>', '<diff>', '']
    if MODE == 'replace':
        lines += [
            '  <!-- TOTAL CONVERSION: every %s-female appearance pool resolves'
            % RACE['label'],
            '       to Rose only, so any woman you meet is Rose.  Switch to',
            '       mode add in make_mod.py to append her as one option',
            '       among the vanilla faces instead. -->',
            '',
        ]
    else:
        lines += [
            '  <!-- Rose joins the pool as one more candidate.  Every vanilla',
            '       entry stays, so the other women keep their own faces,',
            '       names and voices; she takes 1 in N+1 spawns.  Story and',
            '       plot NPCs, which no pool reaches, are untouched. -->',
            '',
        ]
    for pool, n, pure in pools:
        if MODE == 'replace':
            # replace the whole node: the vanilla macros are gone, so the pool
            # cannot fall back to an original face
            lines += [
                '  <!-- %s (%d vanilla entries replaced%s) -->'
                % (pool, n, '' if pure else ', mixed pool'),
                "  <replace sel=\"/characters/character[@name='%s']\">" % pool,
                '    <character name="%s">' % pool,
                '      <select macro="%s" />' % MACRO_NAME,
                '    </character>',
                '  </replace>',
                '',
            ]
        else:
            lines += [
                '  <!-- %s (%d vanilla entries kept) -->' % (pool, n),
                "  <add sel=\"/characters/character[@name='%s']\">" % pool,
                '    <select macro="%s" />' % MACRO_NAME,
                '  </add>',
                '',
            ]
    lines += ['</diff>', '']
    path = write(os.path.join(MOD, 'libraries', 'charactergroups.xml'),
                 '\n'.join(lines))
    mode = 'REPLACE ALL' if MODE == 'replace' else 'append (1 in N+1)'
    print('charactergroups: %s -- %d pools' % (mode, len(pools)))
    for pool, n, pure in pools:
        print('   %-32s %2d vanilla entries%s'
              % (pool, n, '' if pure else '  (mixed)'))
    return path


def write_character_macros():
    """Rose's own macro.

    Inherits `character_argon_female_cau_base_01_macro` so it keeps the shared
    component (skeleton + animation set) and only overrides the model slots.
    `props` is forced to `none` because Rose's hair and cap are baked into the
    head asset -- letting the vanilla random hair props spawn would leave
    floating hair over her head.
    """
    text = '''<?xml version="1.0" encoding="utf-8"?>
<diff>

  <!-- Rose Winters: head and torso are our own meshes; props disabled.
       ref="{basemacro}" is what makes her selectable for this
       race; the identification inherited through it carries
       race="{race}" female="true". -->
  <add sel="/macros">
    <macro name="{macro}" class="npc"
           ref="{basemacro}">
      <component ref="character_argon_female_01" />
      <properties>
        <models>
          <model type="head"  ref="{base}/assets/characters/{race}/rose/heads/rose_head" />
          <model type="torso" ref="{base}/assets/characters/{race}/rose/bodies/rose_body" />
          <model type="props" ref="none" />
          <model type="props2" ref="none" />
        </models>
      </properties>
    </macro>
  </add>

</diff>
'''.format(macro=MACRO_NAME, base='extensions/' + MOD_ID,
               basemacro=RACE['base_macro'],
               race=RACE['base_macro'].split('_')[1])
    return write(os.path.join(MOD, 'libraries', 'character_macros.xml'), text)


# --------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--race', choices=sorted(RACES), default='argon',
                    help="whose women she joins (default: argon)")
    ap.add_argument('--mode', choices=('add', 'replace'), default='add',
                    help="add = one more pool option (default); "
                         "replace = every woman of that race")
    ap.add_argument('--out', default=None,
                    help='override the output directory (default: '
                         'work/x4_rose_<race>_<mode>)')
    args = ap.parse_args()

    configure(args.race, args.mode)
    if args.out:
        globals()['MOD'] = os.path.abspath(args.out)

    if os.path.exists(MOD):
        shutil.rmtree(MOD)

    xacs, textures = merge_assets()
    print('assets copied : %d xac, %d textures' % (len(xacs), len(textures)))
    for x in sorted(xacs):
        print('   %s (%d bytes)' % (os.path.relpath(x, MOD), os.path.getsize(x)))

    n = merge_material_library(textures)
    print('materials     : %d merged into one collection' % n)
    write_content()
    write_charactergroups()
    write_character_macros()
    print('xml written   : content.xml + 3 libraries  [%s / %s]'
          % (args.race, args.mode))

    total = sum(os.path.getsize(os.path.join(r, f))
                for r, _d, fs in os.walk(MOD) for f in fs)
    print('mod size      : %.1f MB -> %s' % (total / 1e6, MOD))


if __name__ == '__main__':
    main()
