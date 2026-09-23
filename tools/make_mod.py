# -*- coding: utf-8 -*-
"""
Assemble the finished X4 mod from the two exported packages.

    python tools/make_mod.py
    # then pack:  XRCatTool.exe -in x4_rose_mod -out ext_01.cat

Layout produced
---------------
    x4_rose_mod/
      content.xml
      libraries/charactergroups.xml     <- Rose in every Argon-female pool
      libraries/character_macros.xml    <- the Rose NPC macro
      libraries/material_library.xml    <- our own collection
      assets/characters/argon/rose/...  <- XAC + textures

Both `rose_head` and `rose_body` packages land in one extension, because X4
loads extensions by id (`ext_01.cat`), not per asset.
"""

import os
import re
import shutil
import sys

WORK = r"D:\dsh-x4\work"
PKG = os.path.join(WORK, "x4cc_pkg")
MOD = os.path.join(WORK, "x4_rose_mod")
MOD_ID = "x4_rose_mod"
ASSET_BASE = "extensions/%s/assets/characters/argon/rose" % MOD_ID

#: Vanilla pool list, used to discover every Argon-female appearance pool
#: instead of hardcoding names (the pools are nested: `argon.trader.female`
#: points at `argon.civilian.female`, which is the one listing real macros).
VANILLA_GROUPS = os.path.join(WORK, 'vanilla', 'libraries',
                              'charactergroups.xml')

#: True  -> every Argon-female appearance pool resolves to Rose only, so any
#:          NPC you look at is Rose (what you want while testing).
#: False -> Rose is appended to the pools as one more random option (~1 in 4
#:          for the 3-entry pools), leaving the vanilla faces in rotation.
REPLACE_ALL_ARGON_FEMALE = True

#: macro name fragments that identify a vanilla female appearance
FEMALE_MACRO_RE = re.compile(r'^character_arg(?:on)?_f(?:emale)?_', re.I)

MACRO_NAME = 'character_argon_female_rose_macro'


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
    dst_root = os.path.join(MOD, 'assets', 'characters', 'argon', 'rose')
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
    if REPLACE_ALL_ARGON_FEMALE:
        desc = ('Replaces every Argon female NPC model with Rose Winters from '
                'Resident Evil Village (test build: all appearance pools).')
        cdesc = ('阿贡女性 NPC 全部替换为《生化危机8》的成年萝丝（测试版：覆盖所有外观池）。')
    else:
        desc = ('Adds Rose Winters from Resident Evil Village as an Argon '
                'female NPC model.')
        cdesc = '阿贡女性 NPC 有几率以《生化危机8》的成年萝丝形象出现。'
    text = '''<?xml version="1.0" encoding="utf-8"?>
<content id="{id}" name="Rose Winters (RE8)" version="101" date="2026-09-23" save="0"
         description="{desc}">
  <text language="7"  name="Rose Winters (RE8)" description="{desc}"/>
  <text language="44" name="Rose Winters (RE8)" description="{desc}"/>
  <text language="86" name="罗丝·温特斯 (RE8)" description="{cdesc}"/>
</content>
'''.format(id=MOD_ID, desc=desc, cdesc=cdesc)
    return write(os.path.join(MOD, 'content.xml'), text)


def discover_female_pools():
    """Return [(pool, n_vanilla_selects, pure)] for the pools to replace.

    A pool qualifies when it selects at least one female macro.  Pools that
    only point at other pools (`argon.trader.female` -> `argon.civilian.female`)
    are skipped, because replacing the leaf covers them.  Mixed pools that list
    men and women together (`benchmark`, `testcharacter` -- developer/benchmark
    groups, not appearance pools) are left alone unless they are Argon groups.
    """
    if not os.path.exists(VANILLA_GROUPS):
        print('  !! %s missing, falling back to a fixed pool list'
              % VANILLA_GROUPS)
        return [(p, 0, True) for p in ('argon.pilot.female', 'argon.service.female',
                                       'argon.marine.female', 'argon.commander.female',
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
        if pure or name.startswith('argon.'):
            out.append((name, len(macros), pure))
    return out


def write_charactergroups():
    pools = discover_female_pools()

    lines = ['<?xml version="1.0" encoding="utf-8"?>', '<diff>', '']
    if REPLACE_ALL_ARGON_FEMALE:
        lines += [
            '  <!-- TEST MODE: every Argon-female appearance pool resolves to',
            '       Rose only, so any Argon woman you meet is Rose.  Set',
            '       REPLACE_ALL_ARGON_FEMALE = False in make_mod.py to go back',
            '       to appending her as one option among the vanilla faces. -->',
            '',
        ]
    for pool, n, pure in pools:
        if REPLACE_ALL_ARGON_FEMALE:
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
    mode = 'REPLACE ALL' if REPLACE_ALL_ARGON_FEMALE else 'append (~1 in 4)'
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

  <!-- Rose Winters: head and torso are our own meshes; props disabled. -->
  <add sel="/macros">
    <macro name="{macro}" class="npc"
           ref="character_argon_female_cau_base_01_macro">
      <component ref="character_argon_female_01" />
      <properties>
        <models>
          <model type="head"  ref="{base}/assets/characters/argon/rose/heads/rose_head" />
          <model type="torso" ref="{base}/assets/characters/argon/rose/bodies/rose_body" />
          <model type="props" ref="none" />
          <model type="props2" ref="none" />
        </models>
      </properties>
    </macro>
  </add>

</diff>
'''.format(macro=MACRO_NAME, base='extensions/' + MOD_ID)
    return write(os.path.join(MOD, 'libraries', 'character_macros.xml'), text)


# --------------------------------------------------------------------------

def main():
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
    print('xml written   : content.xml + 3 libraries')

    total = sum(os.path.getsize(os.path.join(r, f))
                for r, _d, fs in os.walk(MOD) for f in fs)
    print('mod size      : %.1f MB -> %s' % (total / 1e6, MOD))


if __name__ == '__main__':
    main()
