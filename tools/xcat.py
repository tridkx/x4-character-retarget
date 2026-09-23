# -*- coding: utf-8 -*-
"""X4 catalog (.cat/.dat) reader: build index / extract by path."""
import glob, os, sys, io

GAME = r"D:\SteamLibrary\steamapps\common\X4 Foundations"

def parse_cat(catpath):
    """returns list of (name, size, mtime, md5)"""
    out = []
    with open(catpath, 'rb') as f:
        for line in f.read().split(b'\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.rsplit(b' ', 3)
            if len(parts) != 4:
                continue
            try:
                out.append((parts[0].decode('utf8', 'replace'), int(parts[1]),
                            int(parts[2]), parts[3].decode('ascii', 'replace')))
            except ValueError:
                continue
    return out

def build_index(game=GAME):
    """Merge all 0N.cat catalogs in load order (later overrides earlier)."""
    idx = {}
    order = []
    cats = sorted(glob.glob(os.path.join(game, '0[0-9].cat')))
    # stop at first missing number per X4 rules - but glob covers existing ones
    for c in cats:
        entries = parse_cat(c)
        dat = c[:-4] + '.dat'
        off = 0
        for name, size, mtime, md5 in entries:
            key = name.lower()
            idx[key] = dict(name=name, size=size, mtime=mtime, md5=md5,
                            dat=dat, off=off, cat=os.path.basename(c))
            off += size
    return idx

_CACHE = {}
def index(game=GAME):
    if game not in _CACHE:
        _CACHE[game] = build_index(game)
    return _CACHE[game]

def read(game, path):
    idx = index(game)
    e = idx.get(path.lower())
    if not e:
        return None
    with open(e['dat'], 'rb') as f:
        f.seek(e['off'])
        return f.read(e['size'])

if __name__ == '__main__':
    idx = index()
    print('total files indexed:', len(idx))
    for k in ['libraries/character_macros.xml', 'libraries/charactergroups.xml',
              'assets/characters/argon/heads/char_arg_f_dyn_blend_head.xac',
              'assets/characters/argon/bodies/char_arg_f_body_civjacket_01.xac']:
        e = idx.get(k)
        print(k, '->', (e['cat'], e['off'], e['size']) if e else 'NOT FOUND')
