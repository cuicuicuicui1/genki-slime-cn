# 图形资源与消费者台账

地址为 **未修改日版 ROM 文件偏移**。CPU 地址 = 文件偏移 + `0x08000000`，不要把 RAM／VRAM 地址套用此公式。资源 ID 为 archive 索引，不是文件偏移。本文台账不是全游戏图形普查。

## 入口与状态

| 系统 | 源资源／消费者 | 实现／状态 |
|---|---|---|
| Archive | `0x765FA8`，737 (`0x2E1`) entries | `gba_main_menu_graphics.resources`；默认 archive 不全局重排 |
| 中文起名网格 | 两 8bpp tile／byte-map，网格表 `0x7656E4` 附近 | `gba_graphics_engine`；不是 4bpp u16 BG 格式 |
| 教学 | tiles `0x558BCC`、map `0x5597D4`、palette `0x559A34` | `gba_ui_v03.tutorial_engine`；两个消费者 `0x8116C…8118A`／`0xC5EC8…C5EE6` |
| 文件 BG | tiles `0x751B90`、palette `0x751AB0`、raw overlays | `gba_file_labels` + `gba_ui_v03.file_ui_engine`；v20 标题／空记录A／六说明图 |
| 是／否固定窗 | plain `0x713F08`，descriptor pointer `0x73840C` | v20 短译文存在固定列分配问题；`gba_user_ui_v21` 候选以布局 padding 解决 |
| 文件命令 OBJ | IDs `219` tiles／`21A` palette／`21B` templates | `gba_user_ui_v21.file_assets`；仅 file loader literal `0xD6104` 改为私有 archive；未正式发布 |
| 文件时间数字 | renderer `0xD7930`，tiles `0x3EC…0x3FF` | v20 静态 census 漏掉动态使用；候选恢复 20 tiles 并移走空记录字体 |
| 主暂停菜单／8地区标题 | IDs 见 `gba_main_menu_graphics.py` 的常量及 `CAPTIONS` | 来源限定私有 atlas、hook 与 runtime caption gate，v20已包含 |
| 城镇／居民菜单 | `gba_town_resident_graphics` `LABELS`／variants | 成对 atlas／map 载入，原始 R3 保留，不能只改全局 archive |
| 居民小名单 | renderer hook `0x96FE8`，三个 redraw caller | `gba_resident_scroll12`，LR+string-pointer 限定，非 generic 存档渲染 |
| 居民 阅读／尚未交谈 OBJ | archive 及 loader 见 `gba_resident_obj_labels` | native16，v20已包含，原图边框／背板独立 |
| 居民三状态卡 | `gba_resident_status_cards.CARDS` 与 card profiles | 状态特定 native16 scatter/hook，v20已包含 |
| 标题 Logo／动画 | IDs `2BD` tiles／`2BE` 31 templates／`2BF` palette | **未汉化**；`research/title-parent-source-census.json` |
| 救出菜单 | tiles `0x790FB4`、palette `0x7930E4`，IDs `16D/16E/170/171` | 已定位，当前公开流水线没有对应中文资产模块 |
| 排名／小游戏 | tiles `0x78D810`、palette `0x790278`，IDs `134/136/139/13A` | 已定位，消费者 `0xC2392…C23F0`／`0xC256A…C2584`；未完整汉化 |
| HUD／地图／其余小游戏 | 不属于上述小范围 preview census 的全部资源 | **未完整普查**；不能因 archive 有737 entries 就说737项全部处理 |

## 自己抽取，不下载／提交原图

```sh
python -X utf8 tools/inspect_graphics.py --rom "local-input/source.gba" --ids 2BD,2BE,2BF --out "outputs/title-source"
python -X utf8 tools/inspect_graphics.py --rom "local-input/source.gba" --ids 219,21A,21B --out "outputs/file-obj-source"
```

工具输出每个资源的文件偏移、stored／decoded bytes、decoded SHA 和本地 `.bin`。这些是游戏资源，留在忽略目录。当前工具用于原版，开发版的私有 archive 要从实际 hook literal 追踪，不能仍读取原 archive 就误判“补丁没生效”。

## 标题追踪中特别重要的发现

- `2BD` 为 14336 bytes／448个4bpp tiles；`2BE` raw2036 bytes 在 `0x7C7080`。
- `2BE` 有31模板，不是稳定帧一张图片。原日文字形 union 共186 tiles，范围 `121…134`、`150…217`、`321…424`。
- `321…404` 是蓝字变形，`405…424` 是另一组动画字；不能把它们当无关艺术而漏掉。
- 两条标题加载路径都需追踪：`0xD3BB4/0xD3BB8` 与 `0xD4484/0xD4488`。
- Raw模板 palette bank 与 live context palette 不同，必须核对 emitter 及 tile/palette base。
- 英文 DRAGON QUEST、角色脸、闪光应保留；不要只翻最后定格帧而把动画中间帧留日文。

## 完成新图形模块的最低门槛

1. 给 source SHA、source literal/caller bytes、archive entries 和 decompressed hash。
2. 找到真实消费者，标记 BG／OBJ、palette／tile base、目的 VRAM 与生命周期。
3. 静态 map census **加动态数字／名字／光标／重绘 writes**，证明可用 tile。
4. 私有 atlas 必须与 map 同批载入；所有共用 overlay 可用。
5. 所有动画帧／变体中文一致，艺术部分保留；文字原生点阵不糊缩。
6. 输出每段写入和 append bounds；在实际目标 SHA 上检查真实路线／明确fixture。
7. 披露未测的晚期、其他返回路径、保存与联机。以 candidate 发布前不沿用旧证据。
