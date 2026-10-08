# 图形资产与验证方法（GBA 元气史莱姆1 简中 v20）

本文讲两件事：汉化动过的图形资源分别长什么样、怎么在不瞎猜的前提下继续做；以及这套工程用什么手段验证（以及哪些手段**不能**当证据）。
**图形汉化并未完成**：标题仍是日文，晚期/片尾/HUD 等资源尚未普查完（见 `KNOWN-ISSUES.md`）。

路径约定：

- `tools/`、`data/`、`docs/`：本仓库根下的路径（本仓库只随包核心构建模块与数据）。
- `历史本机记录:...`：历史验证来源名称，不是公开工程依赖；现有摘要与便携验证入口见 `docs/verification.md`。
- 上游出处：SuperDisk/Translimeation（固定提交 `027ba3d7810cec3d5d634cb27402b32bf1a0e6d7`）。解压器接口 `slime_gfx.Decompressor` 对应原 ROM 在 `08098AC8` 的例程；本仓库不分发其源码。

## 1. 0x70 压缩流

- 判定：资源首字节 `0x70` 表示压缩（`tools/gba_main_menu_graphics.py:resources()` 用 `raw[0]==0x70`）；否则直接当原字节。
- 头部 4 字节小端：`(解压长度 << 8) | 0x70`。长度在 bits 8..31，低字节是标志。
- 紧跟一个 mode 字节（位流里按 MSB-first 读）：低 3 位选主体解码方式（简单 LZ / 扩展 LZ / 半字 LZ / **字面拷贝** / RLE），bit3..4 选字面读取器（原样 / 4 位 Huffman / 8 位 Huffman），bit5..7 是后置滤波。
- 本工程写入的新流一律用**字面拷贝**（`tools/gba_graphics_engine.py:literal()`）：`b'\x04' + 数据` 补零到 4 字节对齐，每个 4 字节组反转后接在头部后。`literal()` 会用真实解码器回读自检，`mode` 必须是 4 且消费长度正好等于流长度。
- 原资源里出现的 mode 字节常见值是 `0x02/0x03/0x0B/0x0C/0x12/0x13`（上游 `KNOWN_ASSET_MODES`）。**不要**把"低字节 0x70"和"mode 4"混为一谈：前者是头部标志，后者是主体方式。
- 新流的解压长度必须和原资源容量完全相同（例：文件 atlas 32768、城镇 atlas 24576、主菜单 30720）；`resources()` 之外的调用点也要用 `Decompressor` 抽查，而不是按字段名猜。

## 2. 像素与 map 的位域

- 4bpp tile = 32 字节（8 行 × 4 字节），高半字节是左侧像素。8bpp tile = 64 字节。
- u16 map 项：bit0..9 = tile ID，bit10 = 水平翻转，bit11 = 垂直翻转，bit12..15 = 调色板 bank。
- 起名格用 8bpp + **字节** map（1024 字节 = 32×32 格）；不要拿 u16 map 的解析器去读它，`tools/gba_graphics_engine.py` 为此单独实现。
- OBJ 部件不按 map：`tools/gba_resident_obj_labels.py` 的 `decode_parts/encode_parts` 按"起始 tile + x 偏移 + 宽度"逐像素拼 32×16/72×16 精灵。
- 预览一律用真实 palette 与真实翻转位渲染（`indexed4` / `render_map`），不要用截图重画或半透明叠加来"看起来对"。

### 2.1 OBJ 还是 BG：先判定再动手

资源属于哪一层决定它能不能"改 map / 重排 tile ID"：

- **BG**：tiles + u16 map（+调色板 bank）。可以按格改写、重排未引用槽。例：起名右栏标签（`tools/gba_graphics_engine.py` 明确写着它是 BG 不是 OBJ）、三张状态卡（14×9 map，走原 `0x800D1C` 的 map 拷贝）、各城镇/主菜单页。
- **OBJ**：1D/2D 部件表加 `tile` 编号与 size 位，靠 OAM 解释。重排 tile ID 会让部件错位。例：阅读/尚未交谈（每资源 1024 字节 = 32 tile，`decode_parts/encode_parts` 按部件拼）、标题动画 2BD（解码 14336 字节 = 448 tile 的图集，配 `0x2BE` 的 31 帧 OAM 模板）。
- 判定办法：看消费者是逐格扫 map，还是按"部件起始 tile + 偏移"取像素；再把解码尺寸和显存占用对齐（OBJ 常整块进 OBJ VRAM，BG 进 char/screen base）。判定错了就会得到"预览对、实机花"的结果。

## 3. 各消费者与它们的私有 atlas

| 用途 | 源资源（文件偏移） | 解码容量/格式 | 消费者与实现 |
|---|---|---|---|
| 起名格两页 | 指针表 `0x7656E4 + page*8`（每页一对 tiles/map 流） | 16384 B/8bpp（256 tile）+ 1024 B 字节 map | 消费者就是这张表；palette 源 `0x755AD8`（预览用，不改）；`tools/gba_graphics_engine.py` |
| 起名右栏标签（换字/完成） | tiles `0x74F90C`、map `0x74FE74` | 8192 B/4bpp + 1280 B u16 map | 字库基址 literal `0xD20BC`（存的是相对 `0x755AD8` 的 32 位有符号偏移，源值 `0xFFFF9E34`）、map 指针 `0xD3594` |
| 操作教学（两个消费者） | tiles `0x558BCC`、map `0x5597D4`、palette `0x559A34` | 8192 B/4bpp + 1280 B u16 map | `0x811DC/0x811E4/0x811EC` 与 `0xC5F40/0xC5F48/0xC5F50`；`tools/gba_ui_v03.py:tutorial_engine` |
| 冒险之书共用 atlas | `0x751B90`（palette `0x751AB0`、背景 map `0x74FE54`） | 32768 B/4bpp（1024 tile） | 标题 overlay `0x755344`；`tools/gba_file_labels.py` |
| 六张删除/睡眠说明 map | `0x7565BC`、`0x756770`、`0x756A58`、`0x756C58`、`0x756E70`、`0x757030` | 各 2048 B u16 map | 解压器网关 `0x98AC8`（`tools/gba_ui_v03.py:file_ui_engine`） |
| 暂停主菜单 | archive `0x765FA8`（count `0x2E1`）内 ID `0xDF` tiles / `0xE0` palette / `0xD3`、`0xD4` map / `0x103..0x10A` 地区标题 | 30720 B/4bpp（960 tile）、每张 map 2048 B、每标题 48 B | hook `0xC70FC`、标题 hook `0xC8214`；`tools/gba_main_menu_graphics.py` |
| 城镇/名单/搬运 | 同 archive：ID `0x1C6` tiles、`0x1C7` palette、`0x1CE/0x1D7/0x1E4` map、`0x1E7..0x1EE` 地区标题 | 24576 B/4bpp（768 tile）、12 宽标题 48 B | getter 网关 `0x858`；`tools/gba_town_resident_graphics.py` |
| 居民名单 12px 缓存 | 追加的 100 条 512 字节位图 + 指针表 | 原生 64×16 承载区 | hook `0xCB678`、重绘门 `0x96FE8`；`tools/gba_resident_font12.py`、`tools/gba_resident_scroll12.py` |
| 阅读 / 尚未交谈 | 私有 archive ID `0x2D9`、`0x2DB` | 各 1024 B/4bpp | 原消费者 `0xB7298..0xB72E8`，只改 `0xB72CC` 的 archive literal；`tools/gba_resident_obj_labels.py` |
| 三张状态卡 | 私有 map + scatter tile，ID `0x1E0/0x1E1/0x1E2` | 每张 252 B（14×9） | hook `0xCFCBC/0xCFC54/0xD00EC`；`tools/gba_resident_status_cards.py` |

几个必须记住的共享契约：

- **0 号 tile 保持透明**：教学关 BG2 的 map 在 `0x0600D000`、与 BG3 共用 char base；重排只改 BG3 的 map 会让 BG2 出现不透明条纹。`pack4(..., fixed_tiles={0:...})` 就是为此。
- **动态 scratch 不是空闲槽**：地点菜单数字在 `5800..5FFF`、文件菜单数字会在 `0x3A0..0x3FF` 一带被原代码写入，主菜单计数槽 `0x3C0..0x3D7`/`0x3E0..0x3F7` 不在 atlas 里。做"空闲图块普查"时必须先把这些范围排除。
- **每个消费者用自己的私有 atlas 副本**：改 A 菜单的 atlas 不能顺带改到 B 菜单的 map；每个模块都要有"哪些 ID 被别的 map/raw 表引用"的枚举证据（`consumer_tiles()`、`free_template` 之类），而不是笼统假设"没人用的槽"。

### 3.1 色板索引与底色（既有取值，全部不改原色板字节）

| 画面 | 墨 / 底 | 备注 |
|---|---|---|
| 起名格 | 119 / 113 | `data/gba-font-profile.json`；代码注释里的 116 是旧值 |
| 起名右栏标签 | 15 / 11 | 11 是原纸底，不是窗边 |
| 教学静态标签 | 11 | 深蓝提高对比；START 说明保持白 1（动态黑底上会消失） |
| 冒险之书标题 | 12（bank 8） | 原生 16px 单色深蓝，无投影 |
| 空记录提示 | 15 / 1（bank 5） | 深褐字 + 亮绿实心填充 |
| 主菜单绿底文字 | 10 或 11 | 依 bank 7/8 选底；按钮只擦原黑色字（15→7），保留高光描边 |
| 城镇/名单标签 | 15，底 7 或 10 | 地区标题墨 4、底 7 |
| 三张状态卡 | 9 / 5 | 与原卡一致，边框与装饰不动 |
| 阅读 / 尚未交谈 OBJ | 6，bank 14 | 原白底 1 背板，避免透明 12px 被信纸纹干扰 |

改字时"擦底"和"写字"是两步：先把原日文占的矩形恢复成该画面的原底色，再用原生字号的 BDF 位图逐像素写墨色。任何一步跨出授权矩形都要报错，而不是让笔画糊在边框上。

## 4. 居民名单重绘与 resident 卡

- 名单首屏的消费者指纹是 `0xCB676..0xCB68A`（SHA `5e57ace1…`）。`tools/gba_resident_font12.py` 在 `0xCB678` 装 veneer，只对表里 100 个中文姓名指针换成 12px 位图（每条 512 字节 = 原有承载区），返回 16 tile；未知/空记录回落到原读者。
- 翻页不只首屏一处：真实重绘还有三个调用点 `0xCB9FC/0xCBB2A/0xCBF7C`。`tools/gba_resident_scroll12.py` 在 `0x96FE8`（原小字 reader 序言 `f0b557464e464546`）装**LR + 字符串指针 + style0 三重限定**的网关；不命中就复演原序言再进原读者，通用 8px 与存档姓名一格都不动。
- 状态卡：三句 `秘密哟 / 未到访地点 / 快救我吧！` 用原生 16px，卡片保持 112×72/14×9/252 字节与墨 9 底 5，仅三张卡各自 scatter 重载 13/20/18 个 tile 到"源独占 + v17 未用"的槽位（三张同屏放不下是既知事实，不缩字解决）。文字矩形以源目标 `0x0600C220` 加局部 8,32..104,48 计算，正确边界是 `[136,96,232,112]`；早期守卫把右边界算成 224 的失败报告保留在档，**没有为了迁就错误守卫改 ROM**。
- 文案语义有父审判断，别按字面机械翻：`ヒミツじゃ♥` 是"秘密哟"（隐藏地点的俏皮说法，不是指令），`行ったコトないばしょ` 是"未到访地点"（玩家没去过，不是居民没去过）。

## 5. 文件菜单时间数字 1004..1023 的冲突（新候选，未发布）

- 早期"空闲图块普查"把文件 atlas 的 `0x3EC..0x3FF`（十进制 1004..1023）当可复用槽写进了中文名/数字，实际这 20 个 tile 是**原代码动态生成的时间数字**（原生成器 `0xD7930` 一带），于是全新存档的时间栏会花屏——不是用户存档损坏。
- `tools/gba_user_ui_v21.py` 是修这个的工作区候选（从精确v20字节基座构建，公开入口先从源码重建该基座）：把 14 个被占用的空白记录槽改配到真正独占的槽位、把 20 个时间数字 tile 从原 ROM 还原到全部 7 份配对 atlas，并重做文件命令 OBJ 模板（复用原 0..207 tile 区）和"是/否"行布局（原消费者固定 24px + 32px 两段，用补白 + `ALIGN` 保持 56px/14 tile）。
- 该候选**未发布、未进 v20 交付**（`docs/` 与 `KNOWN-ISSUES.md` 的范围仍以 v20 为准）。接手时先跑它的断言（`len(safe)==30 and len(bad)==14`、模板 `n==60`、动画表与指针目录不变），再走第 9 节的自然验证。

## 6. 标题（现有发现，尚未完成）

- 标题 tileatlas为独立资源 `0x2BD`（14336字节）；模板资源 `0x2BE` 位于 ROM `0x7C7080`，raw 2036 字节，头部动画表在相对偏移 `0x656`，**31 帧**，每帧 `u16 部件数 + 每部件 6 字节原生 OAM 模板`，31 帧描述整体精确分区、末帧正好到动画表锚点。
- 原像素渲染（原 palette / 翻转位）表明 `321..404` 是"スライム"字形的变形动画、`405..424` 是"もりもり"的变形；该资源里日文字形并集是 **186** 个 tile（不是早期 worker 说的 82）。英文商标字母 `9..17`、闪光 `218..320`、脸部 `135..149` 必须原样保留。
- 早期"9 个简单表搜索零命中 → 布局是 CPU 生成"的结论**已被推翻**：原 ROM 里就有正面的 31 帧静态模板。两个加载点 `0xD3BB4/0xD3BB8` 与 `0xD4484/0xD4488` 的生命周期、发射函数与对象 tile/palette base 变换仍未查清。
- 结论：**标题尚未汉化，现有发现只是下一步的起点**。已归档的证据足够接手后重新起步：
  - `research/title-parent-source-census.json`（本节的数字来源）
  - `历史本机记录:work/gba-v20-title-parent-review/raw-native-letter-frame-comparison.png`（原生字形变体对照，不是汉化预览）
  - `research/title-parent-resource-decodes.json`；源loader/emitter需使用自己的ROM按资源台账追踪
- 另有 21 层静态 BG 预览的普查清单（`data/graphics-ui-backlog.json`，状态 `extracted-not-localized`），这份旧普查状态不是实时完成台账；部分文件说明和菜单已由源码模块处理，接手以 `docs/resource-index.md` 的实际消费者范围为准。

## 7. 状态一览（已验证 / 候选 / 未知）

**已验证（有同 SHA 证据）**

| 项 | 证据 |
|---|---|
| 教学关两消费者、六张说明 map 的原解压器行为与 tile 预算 | `历史本机记录:evidence/gba-graphics-tests.json`、`历史本机记录:tools/test_gba_graphics.py` |
| 起名格/右栏标签资源与墨色底色的源限定 | `tools/gba_graphics_engine.py`、`历史本机记录:evidence/gba-name-graphics-v02/` |
| 冒险之书标题 + 空记录（变体 A）与消费者指纹 | `历史本机记录:evidence/gba-file-label-tests.json` |
| 三张状态卡 26 项原生检查 / 216 配对 hook | `历史本机记录:work/gba-v20-parent-native01/native-tests.json` |
| 受控三状态 27 界面、城镇循环 22 界面（含文字矩形外不变量） | `历史本机记录:work/gba-v20-three-status01.log`、`历史本机记录:work/gba-v20-town-cycle01.log` |

**模块状态（按交付实际范围，不按旧实验命名）**

| 项 | 位置 |
|---|---|
| 居民 12px 名单、城镇菜单、阅读/尚未交谈 OBJ、状态卡 | `tools/gba_resident_font12.py`、`tools/gba_resident_scroll12.py`、`tools/gba_town_resident_graphics.py`、`tools/gba_resident_obj_labels.py`、`tools/gba_resident_status_cards.py`（已随v20交付；公开构建默认包含） |
| 文件菜单 OBJ + 时间数字修复 | `tools/gba_user_ui_v21.py`（工作区候选，未发布） |
| 空记录变体 B、部分 HUD/地图/小游戏图形 | 尚未处理，未列入任何通道 |

**未知（不要写成已完成）**

- 标题 logo 与标题动画文字：未完成；现有结构census已公开，后续可继续独立验证。
- 晚期/片尾/联机资源、其它 HUD/地图/小游戏图形、未普查的信纸缩略图与装饰字。
- 自然救出 100 名居民、自然解锁城镇菜单、全通关、有效电池存档兼容、实体硬件。

**明确尚未处理的图形项（接手时不要误以为已覆盖）**

- 空记录提示的变体 B（`fill 0x502A` 的第二份表）在 **v20 交付里仍是日文**，也未在真实画面验证；v21 候选把 A/B 两份一起改并各自断言，但该候选未发布。
- `data/graphics-ui-backlog.json` 的 21 层静态 BG 预览仍标 `extracted-not-localized`；修好其中的若干张不等于整份清单完成。
- 主菜单运行时叠加（奖杯/心/助手 raw `0xE8..0xF2`）与计数槽是原样保留，不是"已汉化"。
- 文件菜单命令 OBJ、统计单位与时间冲突在v21候选处理；保存文件姓名的独立消费者尚未修复，不要误称已涵盖。

## 8. 验证手段与它们的边界

| 手段 | 能证明 | 不能证明 |
|---|---|---|
| Unicorn 受控片段（`TI925T` pre-v6，含 DMA3 与 VRAM 字节写别名） | 某条路径在给定寄存器/内存状态下行为正确；hook 到恢复地址的字节级结果 | 自然流程会走到该状态；不支持 Thumb-2 的指令若混入会失败 |
| mGBA 自然输入（`历史本机记录:tools/run_mgba.py` 的 libretro `Core`，HLE BIOS，按脚本送按键） | 真实开机到某帧的画面/内存；同输入下改版与原版的逐像素相同 | 未走到的分支；把受控 WRAM fixture 当自然解锁 |
| 受控 WRAM fixture + 真实按键 | 指定界面/列表在真实显存里的布局与寄存器不变量 | 自然救出/解锁/存档；fixture 数字不能写成游玩进度 |
| 静态预览（`indexed4`/`render_map` 渲 PNG） | 资源解码与图块分配是否正确 | 实机生命周期、动态叠加、OBJ 层 |
| 负例测试（坏源、损坏补丁、截断、拒覆盖） | 工具链的拒绝路径 | 正向功能 |
| Mesen | 工程内留有该模拟器目录，但 GBA 的 BIOS 依赖路线未通过 | 不作为任何通过证据，也不要写成已验证 |

## 9. 接手步骤（图形）

1. **先定位消费者，不要先画图**：用 capstone 扫目标函数附近的 `ldr rX,[pc,#N]` 求 literal 地址，看它是否等于候选资源偏移；`archive` 类资源再确认调用点是否走 `0x8000858`（城镇 getter）或 `0x98AC8`（解压），把源码字节指纹写进断言。
2. **做空闲槽普查**：枚举所有会读同一 atlas 的 map/raw 表，加上第 3 节的动态 scratch 范围，得到"确实没人引用"的集合；`tools/gba_file_labels.py:consumer_tiles()` 是现成范式。
3. **改写只在独占槽上做**，并把"被改图块之外逐字节不变"写成断言（各模块末尾都有这类 assert）。预览渲染必须用真 palette 与翻转位。
4. **受控验证**：先用 Unicorn 跑原解压器与 hook 片段，检查 VRAM 目标区与授权范围外的字节；再按第 8 节的口径做同 SHA 自然路线对照，记录帧号与按键序列。
5. **不要扩范围**：标题先按第6节覆盖全部31模板／两条loader／palette上下文；不要为了对齐而缩字、裁字、加阴影或改原色板；文件 atlas 的 `0x3A0..0x3FF` 一律当动态区，先跑 `tools/gba_user_ui_v21.py` 的断言再谈复用。

### 9.1 一批图形改动的最低证据门槛

想把手上的图形改动从"候选"提升为随版交付，至少要有四项：源消费者字节指纹断言（不是地址注释）、"授权区外逐字节不变"的自动化证据、同 SHA 的受控原生执行（Unicorn 片段或等价物）、以及同 SHA 的自然路线截图对照并写明走到了哪一段。
只有前两项的叫静态候选；只有受控没自然的，不能写"玩家能看到"；自然路线只覆盖早期教学时，不能外推到城镇解锁或全通关。
