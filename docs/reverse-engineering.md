# 逆向与文本工程说明（GBA 元气史莱姆1 简中 v20）

本文给接手者看：这套汉化在 ROM 里改了哪些层、每个结论的证据在哪、哪些还没证。
对象是 GBA 一代《元气史莱姆 冲击的尾巴团》。**本版是用户批准的部分汉化交付，不是 100% 汉化，也没有全通关或跨版本存档兼容认证**（范围见 `KNOWN-ISSUES.md`、`DELIVERY-STATUS.json`）。

路径约定：

- `tools/`、`data/`、`docs/`：本仓库根下的路径；本仓库包含便携构建、调试／审计入口与核心数据。
- `历史本机记录:...`：说明旧版验收来源的档案名称，不是本工程构建依赖。历史日志不公开，接手者无需取得作者电脑文件；公开摘要见 `VERIFICATION-SUMMARY.json`，新的复现步骤见 `docs/building.md`、`docs/verification.md`。
- 上游出处：SuperDisk/Translimeation 的英译逆向工程，固定提交 `027ba3d7810cec3d5d634cb27402b32bf1a0e6d7`。本工程只使用它的字码表与自研解码器**接口**（`slime_gfx.Decompressor` 对应原 ROM 解压器 `08098AC8`），不再分发其源码、ROM 或存档。

## 1. 地址模型：文件偏移 vs CPU 地址

- 源 ROM 8 MiB，目标 ROM 16 MiB。文件偏移 `X` 与 CPU 地址的关系是 `0x08000000 + X`（这里指首个 ROM 等待区 `0x08000000..0x09FFFFFF`；后续等待区是镜像，不是继续递增的文件偏移）。
- `tools/cn_codec.py` 的 `BASE = 0x08000000` 就是这层换算；所有追加数据从**文件** `0x800000` 起写，即 CPU `0x08800000` 起（`tools/build_cn.py` 的 `build()`：`result=bytearray(source+b'\xff'*0x800000); cursor=0x800000`）。
- ROM 里存的指针是**绝对 CPU 地址**，写入时统一 `struct.pack('<I', BASE+offset)`；`build_cn.py` 在改指针前会断言原值等于 `BASE+源偏移`，不符就报错，避免照抄提示里的地址。
- 代码常量习惯写法混用两种：文档里 `080C70FC` 是 CPU 地址，代码里 `HOOK=0xC70FC` 是文件偏移。看到裸地址先确认是哪一种，再决定要不要减 `BASE`。
- 资源是否压缩看首字节：`raw[0] == 0x70` 走 `Decompressor`，否则按原字节使用（`tools/gba_main_menu_graphics.py` 的 `resources()`）。压缩流细节见 `docs/graphics-and-debugging.md`。

## 2. 文本层：原字码、控制码与本地扩展

原文码表是上游英译工程提供的两个 `.tbl`（`SlimeDialog.tbl` 主字库、`Slime_Small.tbl` 小字库），读取器接口在 `text_codec.Codec`。注意上游表把若干字形标成了别的 Unicode 字（表写「玉」实为「王」、表写「対」实为「体」、表写「海」实为「毎」等），本工程不改原字节往返表，只在 `data/gba-source-glyph-corrections.json` 记录"表意 ≠ 格式"的纠正视图。

控制码（`OPS`，`tools/cn_codec.py` 与上游 `text_codec.py` 一致）：

| 字节 | 含义 | 备注 |
|---|---|---|
| `00` | 字符串终止 | 隐式；token 列表里不出现 |
| `01 xx` | 双字节前缀 | 字形码 = `256+xx`；也用于 `01 FE` = 分页 `PAGE` |
| `02` | `NEWLINE`；plain 格式里是 `ALIGN` | 同一字节两种语义，由消费者决定 |
| `03/04` | `SCROLL` / `CLEAR` | 必须原样保留 |
| `05` | `NAME` 定界（`05 … 05`） | 说话人名，内层用小字库 |
| `06/07/08/09` | `DELAY`(带1参) / `SHOW-PROMPT` / `WAIT-INPUT` / `YES-NO` | |
| `0A/0B/0C/0D/0E` | `OPEN-MENU`(带1参) / `SWITCH-WINDOW` / `COLOR`(带1参) / `DYNAMIC-TEXT`(带1参) / `PLAYER-NAME` | 动态参数不翻译，宽度按既有合同处理 |
| `0F A B` | 本地扩展（原 `NOP`） | 见下；原文里 `NOP` 出现次数必须为 0，构建时断言 |

**0F A B 扩展**（`CNCodec.escape/read_glyph`）：`A,B ∈ 0x10..0xFF`，字形码 `0x200 + (A-16)*240 + (B-16)`，可编码到 `0xE2FF`。两个命名空间都用这一种转义，运行时 hook 只是原样重建这个码：

- `PRIMARY = 0x200`（512）：存档格与姓名用的稳定 ID 空间。
- `COMPACT = 0x4000`（16384）：同索引副本 `+ (COMPACT-FIRST)`，走 12px 紧凑字库。
- 描述符查找网关在文件 `0x971EC`（`cn_engine.engine()` 的 `selector` 存根）：落在 `PRIMARY` 空洞或 `COMPACT` 之后的码一律回落到安全码 `16`，不会读到未初始化描述符。

**起名网格不是转义空间**：名录入画面用的是预先渲染好的 8bpp 资源与 u16 网格，那里的 `0E/0F` 是浊音/半浊音标记，不能拿来塞中文（`data/gba-name-entry.json`、`tools/gba_graphics_engine.py`）。

## 3. 六个文本消费者与 hook 台账

这些文本入口使用 8 字节 literal `veneer`（`ldr rN,[pc,#imm] / bx rN / .word 目标|1`；寄存器取值以入口源码为准，不全都用 r3），归档在 `tools/cn_engine.py`、`tools/gba_speaker_font.py`、`tools/gba_name_engine.py`：

| 消费者 | hook（文件偏移） | 原始恢复地址 | 关键寄存器 | 说明 |
|---|---|---|---|---|
| 字形描述符选择 | `0x971EC` | 追加存根内 | `r1` 暂存表基址 | 全字库描述符表的唯一入口 |
| 对白 reader | `0x961E8` | `080961F7`（原路径）/`08096289`（扩展） | `r2` = 上下文，流指针在 `[r2+0x10C]` | 支持 `05 NAME`、控制码 |
| plain/菜单 reader | `0x96C70` | `08096CB9`；前缀 `08096C7F`；`ALIGN` `08096C8D` | `r4` = 源指针 | 保留 `ALIGN` 语义 |
| 说话人 NAME 栏 | `0x965A4` | `080965AD` | `r0` 源，`r5` 存流指针 | 见 `tools/gba_speaker_font.py` |
| 小字 reader | `0x97014` | `0809701D` | `r6` 源、`r7` 字库基址、`r10` 关联 | 8px 小字消费者 |
| 地点名指令 ticker | `0xD2A28` | `080D2A33` / `080D2A69` | `r1` 指针槽 | 命中时加 `COMPACT-FIRST` |

写完每条记录后，`build_cn.py` 会立刻从**成品 ROM** 回读并和作者 token 归一化结果逐项比对，不等同于只看编码函数自测。

## 4. 字号、命名空间与实际渲染宽度

| 用途 | 码空间 | 像素 | 字库 | 证据 |
|---|---|---|---|---|
| 正文对白（2311 条） | `PRIMARY` | 16 | Unifont 16.0.03，stride 64 | `data/gba-font-profile.json` 的 `main_px` |
| 紧凑对白（30 条）、plain 窗（85 条） | `COMPACT` | 12 | Fusion Pixel 12px，stride 48 | 同上 `compact_px` |
| 说话人 NAME 栏 | `PRIMARY` | 12 | 合成栈，advance 中文 12 / 原字 8，上限 96px | `tools/gba_speaker_font.py` 的 `speaker_engine` |
| 通用存档姓名 / 居民 list 原消费者（102 条 `small`） | 原小字码 | 8 | 原 `0x73CAE8` 字库，64 字节/tile | `tools/gba_resident_layout.py` |
| 起名格 | 预先渲染资源 | 12 | 见图形文档 | `tools/gba_graphics_engine.py` |

实现内的已知不一致：`tools/gba_graphics_engine.py` 的注释仍写起名格墨色 116，实际生效的是 `data/gba-font-profile.json` 的 `name_grid_ink = 119`（代码用 `profile.get('name_grid_ink',116)`，默认值只在字段缺失时生效）。以 profile 文件为准。

## 5. 小字 u16 与存档字段：1878 个 ID 只追加

- 玩家姓名占 **4 个 u16 主字库字形码**，输入横幅里未用的格是 `0x1D` 空白字形；`name-default` 存根把默认名（`data/gba-name-entry.json`）连同补零写 5 个半字到 `0x02010280`，名字比较存根只比 4 格、再要求流结束（`tools/gba_name_engine.py`）。
- `data/gba-font-ids.json` 当前 1878 项，**连续**占用 `512..2389`。`CNCodec.__init__` 强制"注册表必须连续、且 `PRIMARY`/`COMPACT` 不重叠"，否则直接抛错。
- 规则：**只允许在尾部追加新字**。重排、删除或按最新译文字集重新编号会让旧存档里的姓名变成别的字；公开 `tools/audit_gba.py` 核对发布基线注册表与生成font-map；开发新字由 `CNCodec` 只追加并输出到 `build/font-map.json`，需人工接纳回注册表。
- 起名网格写入固定指针 `0xD2118` 指向的 180 项 u16 数组：前 120 项是 12 行 × 10 列中文候选，后 60 项保留原样（拉丁/符号页）。`0xD3468` 的读取存根只在指针命中这张私有表时走中文拷贝，其它调用方仍走原逻辑。
- 默认名比较走私有流：`0xD31FC` 存流指针，`0xD32C4` 的比较存根只读这条流，不去解析原网格。
- 旧存档的假名/拉丁名由 `0x8400C` 的独立有界映射处理：未知或越界码回落成 `？`，不再沿原表越界走。原网格里 120 格以外的内容、旧假名与保留名一律不动，`build_cn.py` 用 `UNSAFE_PLAIN = (0x714091, 0x714144)` 把 11 条相关 plain 记录放进 `holds` 不注入。

## 6. ARMv4T 跳板：为什么不能用 Thumb-2

- `veneer()` 生成的 8 字节绝对跳转要求 hook 处 4 字节对齐（`gba_resident_font12.HOOK % 4 == 0`、`gba_main_menu_graphics.HOOK % 4` 都有断言）。
- Keystone 默认可能给高寄存器两操作数指令挑 32 位编码：`adds r2,r4` 曾生成 Thumb-2；必须写**三操作数** `adds r2,r2,r4`。防线是 `tools/gba_file_labels.py` 的 `thumb16_only()` 与 `tools/gba_resident_status_cards.py` 里"除 `bl` 外出现 size==4 指令即报错"的检查。
- 存根内部只允许 16 位 Thumb 或 32 位 Thumb `BL`；需要跳远时用 `veneer`（`ldr`+`bx` 绝对跳转），不受 Thumb 相对分支 ±4 MB 限制。
- 受控执行模型固定为 pre-v6 ARMv4T（Unicorn `TI925T`），片段从 hook 跑到恢复地址，见 `历史本机记录:work/gba-v20-parent-native01/native-tests.json` 的 `cpu_model`。**默认模型过测不算验证**：必须同 SHA 再走自然路线，见 `docs/graphics-and-debugging.md` 第 8 节。

## 7. VRAM 与显存写入契约

- GBA 显存不能当普通字节 RAM：**8 位写会复制到整个半字**。所以说话人合成器（`gba_speaker_font.py`）逐像素写 tile 时用对齐半字读改写（`strh`），而不是 `strb`。片段测试要带这个行为模型，再同 SHA 自然截图。
- 共享 char base 的图层不能按一个 map 重排：教学关 BG2 的透明 map 用 0 号 tile，而 BG3 自己的 map 已被汉化；`gba_ui_v03.pack4(..., fixed_tiles={0:...})` 固定保留 0 号，否则整屏会出现不透明条纹。
- 运行时会写数字/计数器的 scratch 槽（如地点菜单的 `5800..5FFF`）不属于可回收图块，任何"重排/收紧图块编号"的改动必须先把这些区域排除。

## 8. 布局与指针移位

- 作者控制顺序永不变：`gba_text_layout.reflow()` 只插入换行/翻页控制，`COLOR` 当零宽软边界，`same_controls()` 逐 token 校验；`DYNAMIC-TEXT` 按既有合同算 55px，`PLAYER-NAME` 按 4 格主字库宽度算，不改成 4×12。
- 正文默认 208px 宽、两行后自动 `SHOW-PROMPT`+`WAIT-INPUT` 分页；放不下才启用 `compact12`（这就是 30 条紧凑对白的来源）。
- 固定 plain 窗（如小游戏提示框 `plain-713F35`）：每字形宽度 **+1px**，`ALIGN` 向上圆整到 8px 列，`field_end_pixels=[88,184,264]`、`tile_count=66` 是源消费者指纹；越界只能报错，不许缩字号。补白只用原空白字形 `0x1D`，不新增字库项（`tools/gba_plain_layout.py`、`data/gba-plain-window-profiles.json`）。
- 居民 `small` 字段源容量就是 8 个 8px 格：只允许裁掉尾随空格重新补白，**不许截断语义名**（`gba_resident_layout.fit_resident_cells`，消费者指纹 `0xCB676..0xCB68A`）。
- 指针只在 `RELOCATABLE` 种类上重写（`dialogue-table`/`credits-table`/`resident-name-table`/`item-label-table`/`window-descriptor`/`code-literal-candidate`）；每写一处都断言原值与 `BASE+源偏移` 相等，并收集进 `write_regions` 做最终全 ROM 差异门。
- 历史v20交付的文字修订走等容量 rebase（旧等容量profile（历史流程，未作为公开构建输入））：只允许 30 条父审记录的等容量差异，其余字节必须与钉死的资产快照完全相同；任何长度/ID/指针/布局/code/font 变化都会让 rebase 拒绝，不放宽门。公开工程不依赖那些旧快照：`project.py` 从当前译文fresh编译，再按精确输入contract重建资产，末尾核对完整v20 SHA；改稿是新的开发版，不继承运行认证。

## 9. 记录模型与合并流水线（改文本时最常碰的一层）

- 构建输出的 `data/inventory.json` 是源记录清单：每条含 `id`、`offset`/`end`（文件偏移）、`format`、`original_hex`（源字节指纹）、`tokens`（作者视角 token）、`references`（指针出现位置）。构建第一步就是逐条核对 `original_hex`，源 ROM 一变立刻报"Stale source inventory"。
- `format` 有四种：`dialogue`（对白，含 `05 NAME`）、`plain`（固定窗/菜单，只有 `ALIGN`）、`small`（居民/短标签，8 格）、`credits`（片尾，按 tile_row/x 定位）。三种之外的记录进 `holds`，不注入。
- `references[].kind` 决定能不能改指针：只有 `dialogue-table`、`credits-table`、`resident-name-table`、`item-label-table`、`window-descriptor`、`code-literal-candidate` 允许重定位。没有任何可重定位引用的记录进 `orphans`，构建会把它列出来而不是静默丢弃。
- 合并顺序（`tools/build_cn.py:merge`）：`data/auxiliary-translations.json` → `data/review-overrides.json` → `data/term-normalization.json` 术语改写 → 英文/俄文等专名再走 `data/canonical-names.json`。公开入口没有历史worker目录依赖。可用 `--translations` 按ID覆盖reviewed文件；不接受未知或重复ID。
- 控制码与结构必须一致：`same_controls()` 逐 token 比对，长度或控制码结构一变就拒绝该稿。这条对 `NAME`（说话人）和小字串同样适用，防止把控制码当正文翻译。
- 专名替换是**源文限定、一次最长匹配**：`normalize_name_mentions()` 只用 `canonical` 里出现过的源实体、按长度降序、带词典序打破平局，绝不遍历 set 递归 replace——否则会出现"八世八世"这类重复，且不同 `PYTHONHASHSEED` 会造出不同 ROM。序数后缀等特例写在 `data/gba-name-body-rules.json`。
- 居民 `small` 记录的完整姓名匹配只去尾随空白后做 canonical 全名匹配（`small_name_identity`），不做子串替换；名字内部的假名/汉字混写不要机械补"的"。
- 片尾记录只允许改文案，`tile_row`/`x`/`separator` 必须与源一致，单行编码不超过 31 字节、像素不超过 240px，且编码里不能出现 `00/02`（否则原 `00/02` 扫描器会把字形切断）。
- 父审账本：`data/gba-review-ledger.json` 的每条 entry 记录 `token_digest_encoding`（`json-utf8-compact` 或 `json-utf8-default-spaces`），审计时按该编码重算 `accepted_tokens_sha256`。**digest 编码是账本的一部分**，不要用另一种 JSON 空格风格重算后宣称不一致。

## 10. v20 交付的构成（接手时的起点数字）

- 目标 ROM 16 MiB，`target_sha256 = b658e3be…01c9bde0`；`appended_used = 1479404` 字节（从文件 `0x800000` 起）。
- 注入 2528 条：对白 `clear16` 2311 条、对白 `compact12` 30 条、`plain` 紧凑窗 85 条、`small` 8px 102 条；`holds` 11 条（全部是起名相关的 `plain-7140xx`）。
- 字形：`count = 18262`（= `COMPACT + 1878`），`primary_count = 2390`（= `FIRST + 1878`）；通用正文 16px、紧凑窗 12px、通用保存姓名/居民 list 8px。
- 源对白 2341 条、短标签 85 条经父审逐源接受；**这是审过的记录数，不是游玩场景数，也不是汉化百分比**。
- 文档层不要把这些数字写成"接近完成"：标题、晚期、存档兼容、全通关都在 `KNOWN-ISSUES.md` 里明确列为未完成。

## 11. 状态一览（已验证 / 候选 / 未知）

**已验证（有同 SHA 证据）**

| 项 | 证据 |
|---|---|
| 2528 条记录编码、指针、回读、全 ROM 差异门 | `tools/build_cn.py`、`tools/audit_gba.py`、`历史本机记录:work/gba-v20-final-contracts/gba-final-audit.json` |
| 226 项 GBA 单元契约 + 6 个通用脚本 | `历史本机记录:work/gba-v20-unit-contracts/summary.json`、`历史本机记录:work/gba-v20-final-contracts/summary.json` |
| 26 项原生执行检查、216 配对 hook 用例 | `历史本机记录:work/gba-v20-parent-native01/native-tests.json` |
| 字形 bank 无阴影、1878 ID 连续且与 font-map 相同 | `历史本机记录:tools/test_gba_font_style.py`、`data/gba-font-ids.json` |
| 交付补丁 / 独立回放 / 负例拒绝 | `历史本机记录:evidence/gba-partial-v20-final-delivery-verification.json` |
| 7000 帧早期自然路线 47 对画面 | 同上 `fresh_coldboot_*` 字段（只证明该早期路线） |

**工程模块与候选状态**

| 项 | 位置 / 触发 |
|---|---|
| 清晰字体居民 12px、城镇菜单、OBJ 16px、状态卡 16px | `tools/gba_resident_font12.py`、`tools/gba_town_resident_graphics.py`、`tools/gba_resident_obj_labels.py`、`tools/gba_resident_status_cards.py`；已随v20交付，`project.py build` 默认重建 |
| 文件菜单 OBJ 与"是/否"布局修复 | `tools/gba_user_ui_v21.py`（公开入口先从源码重建精确v20，再生成候选，**未发布、未进交付**） |
| 11 条起名相关 plain 记录 | `build` manifest 的 `holds` |

**未知（未验证、不要写成已完成）**

- 标题 logo 与标题动画文字；晚期/片尾/联机资源；其它 HUD、地图、小游戏图形。
- 自然救出 100 名居民、自然解锁城镇菜单、全通关、实体硬件。
- 原版与跨版本电池存档兼容（保存字形 ID 不变只是必要条件，不是证明）。

## 12. 接手步骤

1. **改文本**：动 构建输出的 `data/inventory.json` 对应的作者稿（`历史本机记录:work/translation-*/out/chunk-*.json`）与 `data/review-overrides.json`，然后 `python -X utf8 tools/build_cn.py --rom <原日版>`；构建后用 `tools/audit_gba.py` 复核。不要手改 `build/slime-cn.gba`（该目录也不随本仓库分发）。
2. **加新字**：只往 `data/gba-font-ids.json` 尾部追加；运行一次构建，确认注册表仍连续、`build/font-map.json` 与之一致。任何时候都不要重排旧 ID。
3. **新增/修改消费者**：先用 capstone 定位真实调用点（`ldr rX,[pc,#N]` 求 literal、`bl 0x8000858` 找资源 getter、`0x98AC8` 序言 `f0b544464d4646` 找解压器），把源字节指纹写进断言，再追加存根并留恢复地址；不要凭提示里的地址直接改。
4. **测**：先跑离线契约（`历史本机记录:tests/test_gba_*.py`，不需要 ROM）；需要 ROM 的受控与自然路线口径见 `docs/graphics-and-debugging.md` 第 8、9 节。
5. **发布前**：确认 manifest 的 `target_sha256`、BPS、ZIP 三者互相对得上，`KNOWN-ISSUES.md` 里的未证事项仍成立。
