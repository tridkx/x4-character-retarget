# x4-character-retarget

> **English**: [`README.md`](README.md)
> **成品 mod 下载**：[Releases → x4_rose_argon_add_v1.3.zip](https://github.com/tridkx/x4-character-retarget/releases)（加入外观池）
> · [x4_rose_argon_replace_v1.2.zip](https://github.com/tridkx/x4-character-retarget/releases)（全部替换）

把 **RE Engine 角色（《生化危机8：萝丝之影》的成年萝丝）重定向到《X4：基石》的
NPC 骨架**上的工具与逆向工程笔记，让她作为 Argon 女性 NPC 出现在游戏里。

**这是一个「工具 + 文档」仓库，不是 mod 发布仓库** —— 仓库里放的是可复现的管线
脚本与全部逆向结论；成品 mod 以 [Release](../../releases) 附件形式分发
（二进制资产不进 git 历史）。

> **当前状态：管线跑通、实机可用。**
> 曾经卡住项目的「动作时四肢朝反向弯」（蒙皮误差约 20 cm）已经解决。
> 同一口径下（每个顶点到其主导骨线段的平均距离）：

| 部位 | 修复前 | 现在 | 原版参照 |
|---|---|---|---|
| 手指 | 23.9 cm | **0.96** | 1.11 |
| 脚趾 | 27.9 cm | 5.8 | 4.36 |
| 手掌 | 17.3 cm | 5.2 | 5.34 |
| 整体 | 17.2 cm | ~10 | 7.2 |

---

## 下载与安装成品 mod

**同一个 mod 有两种形态，下载时二选一**：

| 文件 | 形态 | 你会得到什么 |
|---|---|---|
| `x4_rose_argon_add_v1.3.zip` | **`--mode add`**（默认，正式版） | 萝丝**加入** Argon 女性外观池，是**随机出现的其中一个**。原版 macro 一个都不动，其余女性保持自己的脸/名字/语音。3 候选的池里约占 **1/4**，6 候选的平民池里约占 **1/7**。**剧情/任务 NPC 不经过外观池，保持原版外观。** |
| `x4_rose_argon_replace_v1.2.zip` | `--mode replace`（测试版） | 6 个 Argon 女性外观池**整池替换**成只选萝丝，遇到的每个 Argon 女性都是萝丝（含剧情 NPC）。调试新模型时好用，其它场合都不该用 —— 它也会覆盖其它 Argon 外观替换 mod 的条目。 |

1. 到 [Releases](../../releases) 下载你需要的那个 zip
2. 解压到 `X4 Foundations/extensions/`，得到 `extensions/x4_rose_mod/`
3. 启动游戏 → 「扩展」菜单 → 启用
4. 游戏内招募 Argon 女性船员即可看到

两个包由同一份源码生成，差别只在 `make_mod.py` 写出的 `charactergroups.xml`
里是 `<add>` 还是 `<replace>`，所以换包即可切换 —— **不要两个同时装**。

> ⚠️ 需要正版《X4：基石》（开发于 9.00）。Release 包里只有**转换产物**，
> 不含任何游戏本体文件。

## 已知取舍（不是 bug，是换来的）

| 取舍 | 换来什么 | 代价 |
|---|---|---|
| 手指绑手掌 | 虎口不再裂到掌根 | 手指不单独做动作（NPC 看不出来） |
| 头发绑 `Bip01 Head` | 91 根骨里没有发丝链可绑 | 头发是跟着头转的硬壳 |
| 脚部共用踝关节位移 | 脚掌平贴地面 | 脚趾离骨约 5 cm |
| 减面比例 | 顶点预算（超了会让空间站频闪） | 脸和手比源数据粗 |

**仍未解决**：手部法线贴图仍不如原版干净（环纹已消除，下一处该查切线基）；
眼球偏灰白（RE8 靠 shader 参数出虹膜，X4 材质只认三张图）；夹克袖口有深色斑块。

## 管线做了什么

```
RE8 .mesh（含权重）  →  逐骨绑定姿态转移  →  .blend
                    →  X4CharacterConverter 导出  →  .xac + DDS + xml
                    →  XRCatTool 打包  →  ext_01.cat
```

核心是第一步：**X4 的 NPC 替换是「换网格、留骨架」**，
`character_components.xml` 里的共享 component 拥有骨骼与 1100+ 条动画，
macro 只挑 head/torso/props 三个网格槽位 —— 所以替换物必须带上
**逐字节相同的 91 骨骼 Biped 骨架**。

## 关键技术结论

1. **坐标映射是一个反射**。RE8 是 `(x, up, forward)`、X4 是 `(x, forward, up)`，
   `(x, z, y)` 的行列式 = **−1**，所以**必须反转三角形绕序**，否则顶点位置全对、
   但每个面都朝内（实机表现为衣服透明、脸消失）。
   而如果写成 `(x, −z, y)`（保向），角色会**前后镜像** —— 镜像修不回来，
   残差会堆在四肢（手 42 cm、脚趾 23 cm）而躯干正常，**这个分布极易被误判成"姿态差异"**。
2. **一次刚体变换无法跨越两套骨架的姿态 + 比例差异**。必须**逐骨**把几何搬到
   X4 的绑定姿态（`retarget_core.BindPoseRetarget`）。
3. **骨轴推导只能用"主链第一个子骨"**。用"子骨均值"会让骨盆旋转 **161°**，
   把所有下摆/裤子顶点转翻（实机看是腰部一块浅褐色补丁）。
4. **没有 albedo 的材质要继承主材质的颜色与粗糙度**，否则军绿夹克上会出现
   一条深色横带（那些"缝线"其实是成片几何，不是细线）。
5. **两段式管线里两段都要开平滑着色**。stage2 用 `from_pydata` 重建网格时默认
   平面着色，而导出器读 `loop.normal` —— 结果就是满脸面片。
   顺带的好处：平滑法线消掉法线接缝，**导出顶点少 70%**。

完整版在 [`docs/萝丝移植进展.md`](docs/萝丝移植进展.md)，逐轮记录了
「症状 → 测量 → 根因 → 修法」。

## 想自己重建 / 换角色

工具都在 `tools/`，按顺序跑：

```bash
python tools/xcat.py                                     # 先改文件顶部的 DEFAULT_GAME
blender -b --factory-startup --python tools/build_rose_x4.py    # 阶段1：重定向
python tools/prepare_textures.py                         # 贴图（需系统 Python + Pillow）
blender -b --factory-startup --python tools/build_mod.py        # 阶段2：导出 .xac
python tools/make_mod.py --race argon --mode add         # 组装 mod 树（默认 add）
python tools/make_mod.py --race argon --mode replace     # 或者：全部替换版
python tools/verify_mod.py --race argon --mode add       # 发版前自检（模式要跟产物一致）
XRCatTool.exe -in work/x4_rose_argon_add -out work/x4_rose_argon_add/ext_01.cat
```

脚本里的路径（`WORK` / `ADDON_DIR` / `RE8_MODELS`）写死在作者机器上，需要自己改。

**两种形态（`--mode`）**

- `--mode add`（**默认**）：新增一条 macro（`<add sel="/macros">`，`ref` 该种族的
  cau base macro，继承 identification/eyepositions/facemods），并往每个 Argon
  女性外观池追加一条 `<select>`。**原版 macro 一个不动、池里原有条目一条不删**，
  所以她只是"随机出现的其中一个"，且**剧情/任务 NPC 不走外观池，保持原版**。
- `--mode replace`：把这 6 个池整节点 `<replace>` 掉，池里没有原版 fallback，
  所以每个 Argon 女性（含剧情 NPC）都是萝丝。

覆盖的 6 个池（两种模式同一批叶子池，自动从原版 `charactergroups.xml` 发现；
`antigone.*` / `hatikvah.*` 这类只是路由到这些叶子池，不需要单独写）：

```
argon.civilian.female             6 个原版候选
argon.commander.female            3
argon.marine.female               3
argon.pilot.female                3
argon.service.female              3
argon.factiondiplomat.female      1
```

输出目录按形态分开（两者不能互相覆盖）：`work/x4_rose_argon_add` /
`work/x4_rose_argon_replace`。`verify_mod.py` 也带同样的 `--race` / `--mode`，
并按模式断言：add 模式要求每个池**既多了萝丝、又一条原版都没少**（残留
`<replace>` 会把"多一个选项"悄悄变回"唯一选项"，不盯着剧情 NPC 根本看不出来）；
replace 模式要求补丁集完整、没有池还能选到原版。

> 配方表里还有 `--race terran`（Terran 女性与 Argon 女性共用同一个 component，
> 网格完全一样），但萝丝**没有做 Terran 产物**。

**换角色/换来源游戏时，所有具体数字都要重新量**；方法与坑位可以照搬，
见配套 skill：[`x4-npc-replacement-mod`](https://github.com/tridkx/dsh-skill-x4-npc-replacement-mod)。

## 目录

```
tools/      管线与诊断脚本
docs/       可行性验证报告 + 逐轮工程日志（中文）
examples/   配置模板
```

**跨项目共享的资产不在这里**（解包的游戏根、Blender 插件、参考 mod）——
它们放在工作区的 `shared/` 下，脚本用 `shared` 变量引用。
打算做第二个 X4 mod 时，目录怎么分层见 skill 的
[§1.3 多项目工作区布局](https://github.com/tridkx/dsh-skill-x4-npc-replacement-mod/blob/main/references/00-scope-and-pipeline.md#13-建议的工程布局)。

## 依赖

- **X4: Foundations**（开发于 9.00）+ [X Tools](https://www.egosoft.com/download/x4/bonus_en.php)（`XRCatTool.exe`）
- [X4 Character Converter](https://www.nexusmods.com/x4foundations/mods/2152)（Blender 插件 v0.8.7）
- [RE-Mesh-Editor](https://github.com/Percyqaz/RE-Mesh-Editor)（读 RE Engine `.mesh`）
- Blender 4.2+（实测 5.2 LTS）、Python 3.13、numpy、Pillow

## 许可

工具与文档：MIT（见 `LICENSE`）。

《Resident Evil》与《X4：Foundations》是各自权利人的商标。
本仓库不含任何游戏本体资产；Release 中的 mod 包为**转换产物**，仅供个人使用。
