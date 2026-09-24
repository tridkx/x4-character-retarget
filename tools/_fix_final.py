# -*- coding: utf-8 -*-
"""迁移收尾（七·终）：把路径锚点收敛成唯一、规范的一处。

为什么还需要这一步
------------------
前几步是按"见招拆招"补的，结果同一份文件里可能同时存在：

    _X4_SHARED = os.path.join(_X4_DEV_ROOT, 'shared')
    _X4_SHARED = os.path.join(_X4_DEV_ROOT, 'shared')      # 重复
    ...
    _X4_DEV_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 旧式，反向覆盖！
    _X4_SHARED = ...
    _X4_SHARED = ...                                        # 又重复

旧式单行定义会把锚点好不容易算对的值覆盖成仓库根，于是 `_X4_SHARED`
之类全部失效。本步做一次**规范收敛**：

1. 删除所有非规范的 `_X4_DEV_ROOT = ...` 赋值（含旧式单行）；
2. 在文件头部（三引号模块文档之后、首个 import 之前）插入唯一锚点块；
3. 按需追加 `_X4_SHARED` / `_X4_WORK`（各一次）；
4. 清理重复的派生变量定义。

幂等：重复运行不会再改动。

用法::

    python tools/_fix_final.py            # 预览
    python tools/_fix_final.py --apply    # 写入
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

HEAD_COMMENT = '# --- 项目根自动定位（work 已并入 x4-character-retarget）---'
PKG_DEF = '_X4_WORK_PKG = os.path.dirname(os.path.abspath(__file__))'
ANCHOR_END = '_X4_DEV_ROOT = os.path.dirname(_X4_DEV_ROOT)'
SHARED_DEF = "_X4_SHARED = os.path.join(_X4_DEV_ROOT, 'shared')"
WORK_DEF = "_X4_WORK = os.path.join(_X4_DEV_ROOT, 'x4-character-retarget', 'work')"

ANCHOR_BLOCK = [
    HEAD_COMMENT,
    'import os',
    PKG_DEF,
    '_X4_DEV_ROOT = _X4_WORK_PKG',
    "while os.path.basename(_X4_DEV_ROOT) != 'x4-character-retarget':",
    '    _X4_UP = os.path.dirname(_X4_DEV_ROOT)',
    '    if _X4_UP == _X4_DEV_ROOT:',
    '        break',
    '    _X4_DEV_ROOT = _X4_UP',
    ANCHOR_END,
]

DEV_ASSIGN_RE = re.compile(r'^[ \t]*_X4_DEV_ROOT[ \t]*=[^=]')
DERIVED_RE = re.compile(r'^[ \t]*_X4_(SHARED|WORK)[ \t]*=')


def rel(path):
    return os.path.relpath(path, REPO).replace(os.sep, '/')


def find_targets():
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in files:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(root, fn)
            if p == os.path.abspath(__file__):
                continue
            if fn.startswith('_fix_'):
                continue          # 一次性修复脚本自身不参与收敛
            t = open(p, encoding='utf-8').read()
            if re.search(r'_X4_(DEV_ROOT|SHARED|WORK)\b', t):
                out.append(p)
    return sorted(out)


def module_docstring_end(lines):
    """返回模块级三引号文档结束行号（0-based，含），没有则 -1。"""
    started = False
    quote = None
    for i, line in enumerate(lines[:80]):
        s = line.lstrip()
        if not started:
            if s.startswith('"""') or s.startswith("'''"):
                quote = s[:3]
                if s.count(quote) >= 2 and len(s) > 3:
                    return i                      # 单行文档
                started = True
                continue
            if s and not s.startswith('#'):
                return -1                          # 还没进文档就遇到代码
        else:
            if quote in line:
                return i
    return -1


def insert_index(lines):
    """锚点插入点：模块文档之后、首个 import/代码之前的空行处。"""
    doc_end = module_docstring_end(lines)
    start = doc_end + 1 if doc_end >= 0 else 0
    for i in range(start, len(lines)):
        s = lines[i].lstrip()
        if s.startswith('# -*- coding') or not s:
            continue
        return i
    return start


def process(path, apply_changes):
    src = open(path, encoding='utf-8').read()
    lines = src.split('\n')
    notes = []

    uses_shared = bool(re.search(r'_X4_SHARED\b', src))
    uses_work = bool(re.search(r'_X4_WORK\b(?!_PKG)', src))
    if not (uses_shared or uses_work or '_X4_DEV_ROOT' in src):
        return None

    # 1) 移除所有已有锚点块：以头部注释或 _X4_WORK_PKG 起头，到锚点尾结束。
    #    兼容历史上产生的各种残缺形态（import os 位置不一、夹杂派生变量）。
    anchors, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if s != HEAD_COMMENT and not lines[i].startswith(PKG_DEF):
            i += 1
            continue
        j = next((k for k in range(i, min(i + 14, len(lines)))
                  if lines[k].strip() == ANCHOR_END), None)
        if j is None:
            i += 1
            continue
        # 向前吞掉紧邻的空行 / 旧注释，让删除更干净
        while s == HEAD_COMMENT and i > 0 and lines[i - 1].strip() in ('', HEAD_COMMENT):
            i -= 1
        anchors.append((i, j))
        i = j + 1
    for s, j in reversed(anchors):
        del lines[s:j + 1]

    # 2) 删除残留的旧式 _X4_DEV_ROOT 赋值（锚点内那些已随块删除）
    kept, removed_dev = [], 0
    for line in lines:
        if DEV_ASSIGN_RE.match(line):
            removed_dev += 1
            continue
        kept.append(line)

    # 3) 删除所有旧派生变量定义 —— 它们将统一由锚点块提供，避免"去重后
    #    又插入一份"变成两个（曾因此产生重复定义）。
    out, removed_dup = [], 0
    for line in kept:
        if DERIVED_RE.match(line):
            removed_dup += 1
            continue
        out.append(line)

    # 4) 在头部插入唯一规范锚点（import os 已含在块内）
    ins = insert_index(out)
    block = list(ANCHOR_BLOCK)
    if uses_shared:
        block.append(SHARED_DEF)
    if uses_work:
        block.append(WORK_DEF)
    out[ins:ins] = block + ['']

    new = '\n'.join(out)

    # 自检：收敛后每类定义只应有一处
    for name in ('_X4_SHARED', '_X4_WORK', '_X4_WORK_PKG'):
        cnt = len(re.findall(r'^[ \t]*' + name + r'[ \t]*=', new, re.M))
        if cnt > 1:
            raise AssertionError(
                f'{path}: 收敛后 {name} 仍有 {cnt} 处\n' +
                '\n'.join(l for l in new.split('\n')
                          if re.match(r'^[ \t]*' + name + r'[ \t]*=', l)))

    if removed_dev:
        notes.append(f'删旧定义 {removed_dev}')
    if removed_dup:
        notes.append(f'去重 {removed_dup}')
    notes.append(f'收敛锚点(原 {len(anchors)})')

    if new == src:
        return None
    if apply_changes:
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(new)
    return {'file': rel(path), 'notes': '; '.join(notes)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    print(f'模式: {"写入" if args.apply else "预览"}')
    print('=' * 72)
    changed = []
    for p in find_targets():
        r = process(p, args.apply)
        if r:
            changed.append(r)
    for r in changed:
        print(f"  {r['file']:52s} {r['notes']}")
    print('=' * 72)
    print(f'涉及文件: {len(changed)}')
    if not args.apply:
        print('（预览完成；加 --apply 生效）')


if __name__ == '__main__':
    sys.exit(main())
