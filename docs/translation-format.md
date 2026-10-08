# 译文入口与格式

## 数据职责

- `review-overrides.json`：2426 条逐源复核作者记录，主要修改入口。
- `auxiliary-translations.json`：113 条辅助输入，主要是 small 名称及特殊 plain；不冒称全部自然场景验收。
- `canonical-names.json`、`gba-name-body-rules.json`：按**源文限定**的姓名统一与完整后缀规则。
- `glossary.json`、`term-normalization.json`：术语，不是全局无条件替换所有字符串的授权。
- `gba-review-ledger.json`：审核 digest 和摘要；改稿会使旧 token digest 过期，不能继续声称旧条目已通过语义审校。
- `credits-cn.json`：片尾坐标及特殊分隔语法；未知 staff 写法保留假名，不猜人名汉字。
- `gba-font-ids.json`：保存姓名持久 ID，不按新字集重新排序。

ID 如 `dialogue-714F17` 是原版文件偏移，不是“第几句”。一个 ID 可能被多个指针引用，多个 ID 也可能重复同一场景。

## tokens 示例（真实结构）

```json
{
  "id": "dialogue-714F17",
  "tokens": [
    "史兰小镇是史莱姆们的家园……",
    ["NEWLINE"],
    "这里一直宁静又欢乐。",
    ["SHOW-PROMPT"],
    ["WAIT-INPUT"],
    ["NEWLINE"],
    "小家伙们个个精神十足。",
    ["NEWLINE"],
    "今天又在琢磨恶作剧了……",
    ["SHOW-PROMPT"],
    ["WAIT-INPUT"]
  ]
}
```

字符串为文本，数组为控制。`["NAME","中文姓名"]` 的姓名可以翻译；控制名、参数、顺序必须按原消费者保留。`PLAYER-NAME`、`DYNAMIC-TEXT` 不是可替换成固定人名／数字的占位符。`COLOR` 后的数字、菜单编号与延迟参数不要凭感觉改。

先用 `project.py extract` 得到自己的原文 inventory，按 ID 对照。构建会检测控制或结构变化；不能只对照正文字符串。手动合并文本时特别检查跨行语义、说话人、前后互动和否定表达。

## 布局与字体

- 多数对白：原生 16px Unifont；特定溢出短窗使用 12px compact。
- plain、小窗与姓名栏：12px；存档姓名／某些小字消费者独立 8px。
- 作者控制与自动排版是两层：`gba_text_layout.py` 处理正文，`gba_plain_layout.py` 处理 source-qualified 特殊窗。
- `ALIGN` 是列对齐，不是“下一行”；是／否窗使用固定 tile 分配，单纯翻成更短的字仍可能错位。
- 对白里的 NAME 栏和存档姓名不是同一个 renderer。不要通过改 generic small font 全局解决居民名单。
- 静态行数超限不自动等于错误；NEWLINE／SCROLL／CLEAR 的实际窗口生命周期决定可见范围。

新译名优先查系列资料与社区习惯，给出来源并注明其不是官方中文定名。NAME 与正文变体要同时修，保护城镇等非人名实体，避免短姓名误替换地名和“八世”重复。

## 建议修改循环

1. 抽取 inventory，找到 ID 及其所有 references。
2. 对照源文和上下文，制作 `my-edits.json`，保留完整 tokens。
3. 用 `--translations` 生成独立开发目录。
4. 看 `manifest.json` 的实际布局、compact profile 与注入范围；确认没有新增异常 holds/rejected。
5. 在独立模拟器目录测试真实路线，记录目标 SHA、窗口和按键。
6. 提交译文 diff、来源说明、测试范围，附原文对比的必要短摘录；不附商业 ROM／存档。
7. 新字注册表只追加。更新审核记录后才可标记新稿接受，旧 digest 不沿用。

为了可复现，合并姓名使用 longest-match、固定排序和一次性源文匹配，不允许遍历 set 递归 replace。相关测试在 `tests/`；实现看 `tools/build_cn.py`。
