# v22 图形补全工程（GBA 一代）

本轮在v20正文/字库基础上处理用户点名的图形文字。**不是全通关认证，也不冒称全游戏图形已经无遗漏普查。** 原版、旧v20和用户存档不覆盖；发布物只含补丁和工程，不含ROM/BIOS/save。

## 可复现入口

```sh
python -X utf8 tools/project.py bootstrap
python -X utf8 tools/project.py build --rom "自己的原版.gba" --out "outputs/v22" --profile v22
```

默认 `--profile v20` 不变，继续用于固定v20复现；新增v22从原版、作者数据、字体及固定上游依赖完整构建，不依赖任何作者旧ROM或work快照。修改译文可搭配 `--translations`。旧姓名ID只追加、不重排。

## 模块与破解所得

| 新模块 | 来源、消费者及行为 |
|---|---|
| `gba_title_graphics_v22.py` | `765FA8` archive `2BD/2BE`，31帧；原日文union186tiles。第6帧也是完整Logo，不能漏。两动画loader及等待按键loader `D5384` 都选择私有archive。`19F/1A1`按START提示同批替换；英文商标、角色脸、闪光、原动画payload与色板不改。 |
| `gba_rescue_menu_v22.py` | `BB95C..BB9D4`配对载入 `169` atlas、`16D/16E/170/171`地图；救出史莱姆、搬回怪物/物资及只/个单位。保留所有数字overlay和`3E0..3FF`动态银行。`16F`是另一个tileset，不是64行BG地图。 |
| `gba_ranking_minigames_v22.py` | `C2392..C23F0/C256A..C2584`，`132` atlas、`134..13A`全部七图。金币单位“枚”，砸壶计时单位“秒”；十行单位原坐标金币x192、计时x184，y112+16n。`135`是“初级”，不是删除。排行榜、冲浪捞金币、心动砸壶、关闭提示。 |
| `gba_pot_title_v22.py` | `1D9FEC` archive `BC/BE`及`765FA8`的`2C2/2C3`重复组；15帧“心动砸壶”，英文字标和壶图不变，2种palette选择分别保留。 |
| `gba_minigame_wordmarks_v22.py` | `2C6/2C8/2CE`开始/成功通过关卡，仍按原4/6个字对象显示，帧目录和时间不动；倒计时3/2/1不动。`2D7/2D8`六选择/确认提示保留SELECT/A按钮和闪烁。 |
| `gba_user_ui_v21.py` | 纳入v22的前置修复：文件命令OBJ（开始冒险/复制/通信/删除/说明/睡眠模式开关）、是/否24+32px布局；恢复被旧空记录字体误占的20个时间数字图块。 |
| `gba_file_extra_graphics_v22.py` | 复制不允许/复制确认/睡眠快捷键三张遗漏BG。每图私有配对atlas，不把所有新字强塞进共用图集。用本地BL+BX串接旧`98AC8` gateway，旧六删除/睡眠说明路径保持；空绿框返回时明确恢复default atlas。 |
| `gba_file_saved_name_v22.py` | `D7988`两张卡、8个`96BC8`调用LR限定。完整动态四u16姓名，原生12px在16px格中绘制，aligned halfword VRAM stores；旧假名/Latin和其他调用者走原代码，非法中文ID有界空白，不伪造固定名字。 |
| `gba_graphic_labels_v22.py` | 通用但非无条件的私有archive/图块合成器：完整source SHA、原caller/literal guards、FF尾区、所有writes和越界检查。跨palette文字边界逐像素映射原RGB并验证非文字区域不变；不能只检查调色板索引。 |

上述模块公开的是可复用思路和源限定实现，不表示这些地址/资源格式适用于另一游戏。保存姓名与v20持久ID相同不等于已认证跨版存档兼容。

## 验证命令

```sh
python -X utf8 -m unittest discover -s tests -v
python -X utf8 tools/verify_native.py --rom "自己的原版.gba" --build "outputs/v22" --out "outputs/v22-native"
python -X utf8 tools/verify_graphics_v22.py --rom "自己的原版.gba" --build "outputs/v22" --out "outputs/v22-graphics-native"
```

图形验证运行目标ROM本身的ARMv4T getter/解压器、救援loader、文件卡绘制和旧gateway回退。Unicorn的DMA是明确建模，不是自然解锁所有晚期小游戏。自然mGBA HLE验证另行记录目标SHA、3000帧标题和7000帧新游戏路线；不读取用户存档，不把fixture说成全通关。

## 仍不宣称完成的事项

- 全游戏每个晚期/联机/片尾场景均无日文；尚未建立这种穷尽性证明。
- 未明确的staff人名汉字、部分信纸/场景装饰/未定位资源不得猜译。
- 实机、全通关、所有小游戏自然解锁、日版/跨版存档兼容均未认证。

不要把审阅记录数、archive条目数或截图数量当成汉化百分比。
