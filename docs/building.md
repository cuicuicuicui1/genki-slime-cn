# 构建指南

## 1. 准备与校验

使用 README 的虚拟环境命令安装 `requirements.txt`。必须使用锁定的原版 SHA256，不会接受改版／另一 dump。建议将原版放在 `local-input/`，不是仓库根目录。

```sh
python -X utf8 tools/project.py bootstrap
python -X utf8 tools/project.py extract --rom "local-input/source.gba" --out "outputs/source-inspection"
```

第二条生成 2561 条 `inventory.json` 和覆盖报告，每条包含 ID、来源地址、token、原字节与引用类型。抽取器会做原字节往返检查。上游提交被锁定；不要修改上游工作树绕过检查，扩展应在本工程工具中实现。

## 2. 原样重建

```sh
python -X utf8 tools/project.py build --rom "local-input/source.gba" --out "outputs/v20-rebuilt"
```

全程不需要现成 v15～v20 ROM、历史实验文件夹或旧 manifest。流程为：

1. 核对精确源 SHA／8MiB 大小，核对上游提交及 tracked 工作树。
2. 从源 ROM 抽取原文和引用；复制源码／字体／译文至新的隔离输出目录。
3. 编译正文、plain、小字、片尾，生成 descriptor 与 16／12／8px 字库。
4. 重建起名、教学、文件 BG；使用来源限定的指针和 Thumb hook 写入。
5. 构建居民 12px 字形、主菜单及八地区标题、重绘门、城镇菜单、居民 OBJ 与状态卡。
6. 读回编码记录，检查源消费者／code fingerprints、容量、可用 tile 与写入范围。
7. 核对完整目标 SHA，生成 BPS 并回放核对。

输出重点：

| 文件 | 用途 |
|---|---|
| `slime-cn.gba` | 本地生成 ROM，不提交 |
| `genki-slime-cn.bps` | 本次构建补丁（不是自动正式发行） |
| `manifest.json` | 实际目标 SHA、正文偏移及布局 |
| `asset-profiles.json` | 各阶段入口／资源／hook／append bounds 的真实元数据 |
| `build-report.json` | 源与目标指纹、profile、是否与 v20 相同 |
| `build.log` / `assets.log` | 失败位置；禁止公开含本机路径日志 |
| `build/font-map.json` | 本次生成的完整字形注册表 |

早期 asset 模块保留原固定快照门。公开入口用当前 fresh build 的精确输入合约组合资产，源消费者与容量门仍在。**这允许开发构建，不表示新 SHA 自动得到旧版运行认证。** 正式 v20 默认入口最后必须得到 `b658…bde0`。

## 3. 修改译文后构建

复制或制作只含要改条目的 JSON：

```json
[{"id":"dialogue-714F17","tokens":["……保持原控制序列的完整 tokens……"]}]
```

真实 token 格式请看译文指南，不可直接照这个占位例子构建。

```sh
python -X utf8 tools/project.py build --rom "local-input/source.gba" --translations "my-edits.json" --out "outputs/my-test"
```

`--translations` 按 ID 覆盖已审文件中的条目，可传完整文件或局部列表；未知／重复 ID 拒绝。当前入口只接受已审 2426 条 ID，新增特殊条目要同时修改辅助入口与审计，不偷偷覆盖未审候选。源控制序列、原字节和写入约束仍核对。

新字会追加到本次 `build/font-map.json`。正式接纳前，将确认后的新增 ID 追加回 `data/gba-font-ids.json`；不要重排旧表。字库变化会影响偏移与存档解释，必须重新验证。

## 4. 可选 profile

```sh
# 仅正文引擎 + 早期起名/教学/文件BG；用于把错误范围缩小
python -X utf8 tools/project.py build --rom "local-input/source.gba" --profile text-only --out "outputs/text-debug"

# 基于精确v20的后续文件OBJ/是-否/计时tile冲突修复候选
python -X utf8 tools/project.py build --rom "local-input/source.gba" --profile ui-candidate --out "outputs/ui-experiment"
```

`ui-candidate` 必须基于未改译文的精确 v20，不能任意合并其他版本。它没有完整自然存档／复制／删除／全部 HUD 路线验收，**禁止将其替代 v20 Release 或宣传为标题全部汉化**。

## 5. 常见失败

- `Wrong ROM`：源大小／SHA 不一致，不放宽门；不要使用已有汉化。
- `Modified upstream`：恢复依赖为锁定提交的干净工作树；不要把上游改动冒称汉化源码。
- 输出目录存在：换新 `--out`，不要删原件或用户存档。
- `UnicodeDecodeError`：使用 `-X utf8`；子构建自动设置 `PYTHONUTF8=1`。
- 源控制变化／未知字符／溢出：检查原 token、字体支持与实际窗口，不能删控制或全局缩字硬过。
- 引擎／atlas 合约失败：阅读 `assets.log` 和具体 hook/source bytes，先建立消费者 proof，再更新合约。
- 修改仓库默认译文后想构建：把改稿作为 `--translations` 传入；无该参数的 v20 重建有最终固定 SHA 门。

ROM、存档、BIOS、解压资源和完整原文仅保存在本地忽略目录。不在 CI 中提供 ROM secret，也不下载商业 ROM。

## v22 图形补全

使用 `--profile v22`。默认v20入口保持固定复现。新模块与破解入口见 [graphics-v22.md](graphics-v22.md)。构建依然必须自备严格SHA的原版，不读取历史ROM。
