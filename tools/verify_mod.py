# -*- coding: utf-8 -*-
"""Pre-flight check for the assembled mod, without launching the game.

    python tools/verify_mod.py

Checks, in order:
  1. every XML we ship is well formed;
  2. every `sel=` XPath in our diffs actually matches a node in the vanilla
     library (a typo there is silently ignored by the game);
  3. after applying our diffs, the appearance pools really do resolve to Rose
     and nothing else (this is what makes "replace all" trustworthy);
  4. the macros/components/textures the macro references exist;
  5. both .xac files carry the vanilla skeleton byte-for-byte.

Exit code is non-zero when something is wrong, so it can gate a build.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WORK = r"D:\dsh-x4\work"
MOD = os.path.join(WORK, 'x4_rose_mod')
VANILLA = os.path.join(WORK, 'vanilla', 'libraries')
MACRO_NAME = 'character_argon_female_rose_macro'

FAIL = []


def ok(msg):
    print('  [ok]   %s' % msg)


def bad(msg):
    print('  [FAIL] %s' % msg)
    FAIL.append(msg)


def warn(msg):
    print('  [warn] %s' % msg)


# ---------------------------------------------------------------- XPath bits
def match_sel(root, sel):
    """Minimal XPath: /a/b[@name='v'] -> list of matching elements.

    The leading step names the document element itself (ElementTree's root),
    not a child of it -- `/characters/character[...]` must match the root when
    the file's own tag is `characters`.
    """
    parts = [p for p in sel.strip('/').split('/') if p]
    cur = [root]
    if parts and parts[0] == root.tag:
        parts = parts[1:]
    for part in parts:
        m = re.match(r"^([A-Za-z0-9_]+)(?:\[@([A-Za-z0-9_]+)='([^']*)'\])?$", part)
        if not m:
            raise ValueError('unsupported selector step: %r' % part)
        tag, attr, val = m.group(1), m.group(2), m.group(3)
        nxt = []
        for node in cur:
            for child in node:
                if child.tag != tag:
                    continue
                if attr and child.get(attr) != val:
                    continue
                nxt.append(child)
        cur = nxt
    return cur


def load(path):
    return ET.parse(path).getroot()


def check_xml(path, label):
    if not os.path.exists(path):
        bad('%s missing: %s' % (label, path))
        return None
    try:
        root = load(path)
    except ET.ParseError as e:
        bad('%s is not well-formed XML: %s' % (label, e))
        return None
    ok('%s is well-formed' % label)
    return root


# ---------------------------------------------------------------- the checks
def check_charactergroups():
    mod_path = os.path.join(MOD, 'libraries', 'charactergroups.xml')
    van_path = os.path.join(VANILLA, 'charactergroups.xml')
    root = check_xml(mod_path, 'charactergroups.xml')
    if root is None:
        return
    if not os.path.exists(van_path):
        warn('vanilla charactergroups.xml not extracted, skipping pool checks')
        return
    van = load(van_path)

    replaced = 0
    for node in root:
        sel = node.get('sel')
        if not sel:
            bad('<%s> without sel=' % node.tag)
            continue
        targets = match_sel(van, sel)
        if node.tag == 'replace':
            if len(targets) != 1:
                bad('replace sel=%s matched %d nodes' % (sel, len(targets)))
                continue
            replaced += 1
            pools = [e for e in node if e.tag == 'character']
            if len(pools) != 1:
                bad('replace sel=%s does not carry exactly one <character>'
                    % sel)
                continue
            macros = [s.get('macro') for s in pools[0] if s.tag == 'select']
            if macros != [MACRO_NAME]:
                bad('pool %s resolves to %s, expected only %s'
                    % (pools[0].get('name'), macros, MACRO_NAME))
            else:
                ok('pool %-32s -> Rose only' % pools[0].get('name'))
        elif node.tag == 'add':
            if not targets:
                bad('add sel=%s matched nothing' % sel)
            else:
                ok('add sel=%s matched %d node(s)' % (sel, len(targets)))
        elif node.tag in ('remove',):
            if not targets:
                bad('remove sel=%s matched nothing' % sel)
        else:
            warn('unhandled diff element <%s>' % node.tag)
    if replaced:
        print('  -> %d appearance pool(s) fully replaced' % replaced)


def check_macros():
    root = check_xml(os.path.join(MOD, 'libraries', 'character_macros.xml'),
                     'character_macros.xml')
    if root is None:
        return
    van = None
    van_path = os.path.join(VANILLA, 'character_macros.xml')
    if os.path.exists(van_path):
        van = load(van_path)

    for node in root.iter('macro'):
        name = node.get('name')
        ref = node.get('ref')
        if ref and van is not None:
            if match_sel(van, "/macros/macro[@name='%s']" % ref):
                ok('macro %s inherits %s (exists)' % (name, ref))
            else:
                bad('macro %s inherits missing macro %s' % (name, ref))
        comp = node.find('component')
        if comp is not None and van is not None:
            comps = os.path.join(VANILLA, 'character_components.xml')
            if os.path.exists(comps):
                if match_sel(load(comps),
                             "/components/component[@name='%s']" % comp.get('ref')):
                    ok('component %s exists' % comp.get('ref'))
                else:
                    bad('component %s not found in vanilla' % comp.get('ref'))
        for model in node.iter('model'):
            ref = model.get('ref')
            if not ref or ref == 'none':
                continue
            rel = ref.split('extensions/%s/' % os.path.basename(MOD))[-1]
            p = os.path.join(MOD, rel.replace('/', os.sep) + '.xac')
            if os.path.exists(p):
                ok('model %-6s -> %s' % (model.get('type'), rel + '.xac'))
            else:
                bad('model %s points at missing %s' % (model.get('type'), p))


def check_assets():
    van = {
        'rose_body.xac': os.path.join(
            WORK, 'vanilla', 'assets', 'characters', 'argon', 'bodies',
            'char_arg_f_sweater_leggings_civ_01.xac'),
        'rose_head.xac': os.path.join(
            WORK, 'vanilla', 'assets', 'characters', 'argon', 'heads',
            'char_arg_f_dyn_blend_head.xac'),
    }
    import xac
    for fn, van_path in van.items():
        sub = 'bodies' if 'body' in fn else 'heads'
        p = os.path.join(MOD, 'assets', 'characters', 'argon', 'rose', sub, fn)
        if not os.path.exists(p):
            bad('%s missing' % p)
            continue
        if not os.path.exists(van_path):
            warn('vanilla reference for %s not extracted' % fn)
            continue
        r = xac.compare_skeletons(van_path, p, verbose=False)
        if r['names_match'] and r['blocks_identical'] == r['blocks_compared']:
            ok('%s skeleton identical to vanilla (%d bones)'
               % (fn, r['blocks_compared']))
        else:
            bad('%s skeleton differs from vanilla (%d/%d payloads identical)'
                % (fn, r['blocks_identical'], r['blocks_compared']))

    tex_dir = os.path.join(MOD, 'assets', 'characters', 'argon', 'rose',
                           'textures')
    n_tex = len(os.listdir(tex_dir)) if os.path.isdir(tex_dir) else 0
    if n_tex:
        ok('%d textures present' % n_tex)
    else:
        bad('no textures in %s' % tex_dir)

    mats = check_xml(os.path.join(MOD, 'libraries', 'material_library.xml'),
                     'material_library.xml')
    if mats is not None:
        missing = 0
        for node in mats.iter('material'):
            for v in node.iter('value'):
                text = (v.text or '').strip()
                if not text:
                    continue
                p = os.path.join(MOD, text.replace('\\', os.sep))
                if not os.path.exists(p):
                    missing += 1
        if missing:
            bad('%d material texture paths do not exist in the mod' % missing)
        else:
            ok('every material texture path resolves inside the mod')


def main():
    print('verifying %s' % MOD)
    if not os.path.isdir(MOD):
        print('mod directory does not exist -- run tools/make_mod.py first')
        return 1
    check_xml(os.path.join(MOD, 'content.xml'), 'content.xml')
    check_charactergroups()
    check_macros()
    check_assets()
    print()
    if FAIL:
        print('FAILED: %d problem(s)' % len(FAIL))
        for f in FAIL:
            print('  - %s' % f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
