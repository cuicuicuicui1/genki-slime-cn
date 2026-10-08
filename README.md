# 元气史莱姆1：冲击的尾巴团 · 简体中文汉化工程

## 新增：v22 图形补全版本

标题Logo和31帧文字动画、砸壶15帧动画、文件命令/复制提示、救援结算、三类排行榜、开始/通关/选择/确认提示及文件卡中文姓名已加入独立v22流水线。旧v20补丁和Release保持不变。见 [本轮图形破解与构建](docs/graphics-v22.md)、[v22补丁目录](releases/v22) 和 [验证摘要](evidence/graphics-v22-delivery.json)。

```sh
python -X utf8 tools/project.py build --rom "自己的原版.gba" --out "outputs/v22" --profile v22
```

本轮验证：39项ROM-free测试、实际ARMv4T图形/文件卡消费者、正文/姓名原生检查、独立Python与Flips补丁回放，以及隔离mGBA的3000帧标题/7000帧新游戏路线。

**边界：这不是100%汉化或全通关认证。** 已定位的本轮图形项目与仍未穷尽普查的晚期/联机场景分开记录。


**Game Boy Advance / GBA · 日版 A9KJ · 公开的可复现开发工程**

[![ROM-free CI](https://github.com/cuicuicuicui1/genki-slime-cn/actions/workflows/rom-free-tests.yml/badge.svg)](https://github.com/cuicuicuicui1/genki-slime-cn/actions/workflows/rom-free-tests.yml)

这个仓库不只是补丁下载页：它保存中文译文、字形 ID、字体、补丁生成源码、图形资源处理器、逆向记录和贡献流程。你可以用自己合法持有的原版 ROM **原样重建 v20**，也可以改译文后生成新的开发版。

> **状态说明**：已发布 v20 是“大部分汉化”交付版，不是全汉化／全通关认证版。该描述仅针对固定旧v20；新增图形补全版本见上方v22章节。`ui-candidate` 是可复现的后续菜单修复实验，不能当正式版。项目只涉及 **GBA 一代**，不是 GBC，也不是 NDS 二代。

## 按你的目的选择入口

| 你想做什么 | 从哪里开始 |
|---|---|
| 使用本轮图形补全 | [v22补丁](releases/v22) / [本轮使用与破解](docs/graphics-v22.md) |
| 使用旧v20固定版 | [v20 Release](https://github.com/cuicuicuicui1/genki-slime-cn/releases/tag/v20) / [补丁使用](#只想玩现有-v20) |
| 从源码重建 v20 | [构建指南](docs/building.md) |
| 精修译文／换成其他语言 | [译文编辑指南](docs/translation-format.md) |
| 理解字库、字码、窗口、指针破解 | [文本与引擎逆向](docs/reverse-engineering.md) |
| 修改标题、菜单、HUD 等图形字 | [图形与调试](docs/graphics-and-debugging.md) / [资源台账](docs/resource-index.md) / [后续清单](docs/roadmap.md) |
| 理解哪些测试真的做过 | [验证边界](docs/verification.md) |
| 报乱码／提交修改 | [贡献指南](CONTRIBUTING.md) / Issues |

## 开发者快速开始

需要 **Python 3.12、Git**。工程验证环境为 Python 3.12.10；使用虚拟环境，不必安装全局工具。Windows PowerShell：

```powershell
git clone https://github.com/cuicuicuicui1/genki-slime-cn.git
cd genki-slime-cn
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 tools/project.py bootstrap
.\.venv\Scripts\python.exe -X utf8 tools/project.py build --rom "你的原版.gba" --out "outputs/v20-rebuilt"
```

macOS／Linux 使用 `.venv/bin/python` 替代上述 Python 路径。`bootstrap` 只拉取固定提交的上游工具，**不下载 ROM、BIOS、存档或模拟器**。

- 原文、指针清单从你提供的 ROM 逐字节抽取，完整日文转储不在 Git 中。
- 译文全部来自 `data/`，不需要作者的历史工作目录、旧 ROM 或旧 manifest。
- 所有构建都写到新的 `--out` 目录；拒绝覆盖已有目录及原版。
- 默认构建必须得到 v20 的固定 SHA256；改稿请用 `--translations`，详见构建指南。
- 字库、姓名、菜单、状态卡均从源码重建；不是偷偷把现成汉化 ROM 当作构建基座。

## 工程目录

```text
assets/fonts/       实际用到的 16／12／8px BDF 与字体许可
data/               已审译文、辅助名称、术语、ID 注册表、复核摘要
  review-overrides.json      2426 条已审作者记录（控制序列仍保留）
  auxiliary-translations.json 113 条辅助输入（不冒称全部精翻通过）
  gba-font-ids.json           1878 个持久姓名字形 ID，只追加
  gba-review-ledger.json     逐记录复核摘要与 token digest
tools/              字码、字库、ARM Thumb 注入、BG／OBJ、BPS、便携入口
docs/               构建、译文、逆向、图形、验证与资源导航
research/           标题 31 模板及资源消费者等结构化发现（不含图集二进制）
tests/              不依赖游戏 ROM 的工程测试
.github/            ROM-free CI、问题模板
```

`upstream/`、`outputs/`、`local-input/`、`.venv/` 是本地生成／输入目录，已忽略。禁止把 ROM、存档、BIOS、解压图集、个人配置或密钥提交到仓库。

## 已验证工程可用性

- 干净Git克隆、独立虚拟环境、固定上游依赖，从原版完整重建的目标与v20逐字节一致。
- 修改既有译文能生成新的开发版；新增字形测试保留全部1878旧ID、只追加1字，并完成实际编码读回。
- 31项ROM-free测试在GitHub Windows／Ubuntu通过。可选原生源码审计／字形／起名消费者检查通过。
- 重建ROM用隔离mGBA HLE冷启动7000帧，47对早期画面与原v20记录完全相同；不读取用户存档。

证据见 [engineering-portability.json](evidence/engineering-portability.json)。这些验证不覆盖全通关，也不给改稿或UI候选继承运行认证。

## 现有汉化与剩余范围

v20 已涵盖：

- 大部分剧情对白、系统正文、中文起名与姓名、操作教学。
- 冒险之书标题及部分删除／睡眠说明。
- 主要城镇、救出名单、搬运记录菜单、地区标题。
- 完整居民姓名和“阅读”“尚未交谈”等状态提示。
- 诺克森林／诺克之井／乌鲁奥塔河译名统一。

2528 条编码记录写入 ROM；其中 2341 条源对白与 85 条短标签有逐源复核。计数包括重复和特殊记录，**不是场景数，也不是汉化百分比**。多数正文原生 16px，姓名与小窗 12px，通用保存姓名仍有 8px 限制。

标题 Logo／动画、部分保存／复制图形、HUD／地图／小游戏仍需后续工作。新发现的文件菜单计时字形冲突和是／否布局问题已形成源码候选；正式 v20 补丁保持不变，见 [已知问题](KNOWN-ISSUES.md)。

## 只想玩现有 v20

自己准备合法持有的未修改 **8MiB 日版原件**，在原版上应用 `genki-slime-cn.bps`。不要对旧汉化重复打补丁。

```sh
python apply_bps.py "原日版.gba" genki-slime-cn.bps "元气史莱姆1-简中-v20.gba"
```

也可使用 Flips。生成的 `.gba` 用支持 GBA 的模拟器启动；Snes9x 不是本作的平台入口。脚本核对源、补丁、目标 SHA256 并拒绝覆盖已有文件。

| 对象 | SHA256 |
|---|---|
| 原日版（8MiB，仓库不含） | `a4f8d475eb877bc370cead79876caf7418864b1497d237650ff738c3afdf27a2` |
| 发布 v20（16MiB，仓库不含） | `b658e3bea80ce1deb024298583d5743332bdbb5101109bcdf0d1404501c9bde0` |
| 已发布 BPS | `a62326c7f8af4a377d3669aa8685d9a03f0aae48b4cc581f5daf5fe78f262c0c` |

自己构建的 BPS metadata 与已发布补丁可能不同，所以 BPS 文件 SHA 不必相同；**重建目标 ROM 的 SHA 必须相同**。修改译文后的开发版不能继承正式版测试结论。

## 验证、贡献与权利

已发布版有独立 Python／Flips 回放、失败输入检查和 7000 帧早期冷启动记录。受控城镇／居民测试不等于自然救出全部居民；没有自然全通关、全部晚期／联机或跨版电池存档认证。先备份存档，调试使用隔离目录。

欢迎提交精翻、图形消费者追踪、复现步骤和可审计的小范围 PR。不要只上传新 ROM 或含糊的“全汉化”补丁；请说明来源、修改位置、截图／测试和未覆盖场景。

参考 SuperDisk／Translimeation，固定上游提交 `027ba3d7810cec3d5d634cb27402b32bf1a0e6d7`。未确认其根许可，因此上游源码不再分发，仅由 `bootstrap` 拉取。字体来自 GNU Unifont 16.0.03 与 Fusion Pixel；保留字体署名及许可。字体许可不覆盖游戏、译文或整个工程。详见 [权利与来源](COPYING.md)。

维护状态更新：2026-10-08。新图形汉化正在开发，本次工程整理不把未完成部分伪装为完成。

## 固定版与当前图形版不要混用

仓库根目录 `genki-slime-cn.bps`、`apply_bps.py`、`DELIVERY-STATUS.json`、`VERIFICATION-SUMMARY.json`仍属于历史v20。v22的补丁、独立应用器、校验和与边界说明放在 `releases/v22/`。使用同一目录下的一套文件，不要拿v20应用器验证v22补丁。
