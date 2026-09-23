# -*- coding: utf-8 -*-
"""
Assemble the finished X4 mod from the two exported packages.

    python tools/make_mod.py
    # then pack:  XRCatTool.exe -in x4_rose_mod -out ext_01.cat

Layout produced
---------------
    x4_rose_mod/
      content.xml
      libraries/charactergroups.xml     <- adds Rose to four female pools
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

#: female appearance pools Rose is added to (plan A).
#: Each pool has only 3 vanilla entries, so Rose comes up ~1 in 4.
POOLS = [
    ('argon.pilot.female',     'Pilot / Captain'),
    ('argon.service.female',   'Service Crew'),
    ('argon.marine.female',    'Marine'),
    ('argon.commander.female', 'Manager / Commander'),
]

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
    text = '''<?xml version="1.0" encoding="utf-8"?>
<content id="{id}" name="Rose Winters (RE8)" version="100" date="2026-09-23" save="0"
         description="Adds Rose Winters from Resident Evil Village as an Argon female NPC model.">
  <text language="7"  name="Rose Winters (RE8)" description="Recruitable Argon female NPCs can appear as Rose Winters."/>
  <text language="44" name="Rose Winters (RE8)" description="Recruitable Argon female NPCs can appear as Rose Winters."/>
  <text language="86" name="罗丝·温特斯 (RE8)" description="阿贡女性 NPC 有几率以《生化危机8》的成年萝丝形象出现。"/>
</content>
'''.format(id=MOD_ID)
    return write(os.path.join(MOD, 'content.xml'), text)


def write_charactergroups():
    lines = ['<?xml version="1.0" encoding="utf-8"?>', '<diff>', '']
    for pool, label in POOLS:
        lines += [
            '  <!-- %s -->' % label,
            "  <add sel=\"/characters/character[@name='%s']\">" % pool,
            '    <select macro="%s"/>' % MACRO_NAME,
            '  </add>',
            '',
        ]
    lines += ['</diff>', '']
    return write(os.path.join(MOD, 'libraries', 'charactergroups.xml'),
                 '\n'.join(lines))


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
