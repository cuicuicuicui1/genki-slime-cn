# 验证记录与边界

## 发布版与工程构建不是同一类结论

| 验证层 | 可以说明什么 | 不能说明什么 |
|---|---|---|
| ROM-free CI | 工具与数据结构、编码／布局纯函数、BPS错误处理、ID契约 | 自然游戏画面、全通关 |
| 源码结构构建 | 精确源、原文往返、控制、布局、指针、容量、写入区域及最终读回 | 新译文精翻、新字体全部场景可读 |
| 原样重建目标SHA | 本工程输出与已验证v20逐字节一致 | 旧版自身未测的场景变成已测 |
| BPS 回放 | 给定源+补丁可精确生成目标，错误输入拒绝 | 游戏运行正确 |
| Unicorn 源消费者片段 | 指定入口、内存模型及fixture下结果正确 | 自然解锁、硬件或全流程 |
| mGBA自然按键路线 | 指定core+SHA+输入范围冷启动及画面 | 全通关／100居民／跨版存档 |
| 明确fixture状态卡 | 受控状态窗口／atlas生命周期 | 同状态能自然到达或自然剧情已验证 |

v20交付摘要在根目录 `VERIFICATION-SUMMARY.json` 与 `DELIVERY-STATUS.json`。早先226项本机GBA单元检查不是当前ROM-free CI测试数量，不混用。完整本机日志含路径和输入，不作为仓库分发内容。

## 此次工程复现验证

维护者会在 `evidence/engineering-portability.json` 记录：干净Git目录、固定依赖、完整v20重建SHA、修改译文构建与编码读回、BPS回放、后续候选SHA、原版与旧交付不动。该记录只保存脱敏结果；不得把失败尝试或未完成检查写成通过。

`--translations` 构建被明确标为开发版。自动 source diff 与输入contract不是运行证据，不能给其他SHA继承v20自然截图测试。

## 自己跑早期自然路线

mGBA libretro core需要自行从官方项目获得，仓库不带二进制或BIOS。工具适配Windows DLL／Linux SO／macOS dylib；本项目已验证的是记录在报告中的特定Windows core，不声称所有平台均跑过。

```sh
python -m pip install -r requirements-test-emulator.txt
python -X utf8 tools/smoke_mgba.py --rom "outputs/v20-rebuilt/slime-cn.gba" --core "你自己的/mgba_libretro.dll" --out "outputs/smoke-v20"
```

- 7000帧全新HLE启动；只按实际按钮，不写RAM、不载入用户存档、不载入Nintendo BIOS。
- 输出每150帧截图和run.json（ROM／core SHA、输入范围、环境）。
- Core没有打包或自动下载。不同core版本不保证逐像素相同。
- 不自动在游戏窗口接管输入，不动用户当前模拟器进程或电池存档。

有RAM／savestate注入时必须另标controlled fixture，不能借用这个“自然输入”标签。

## 新版提交时建议附带

- 精确源／目标／补丁／coreSHA与命令。
- 改了哪些指针、代码入口、atlas／map／OBJ模板及字形IDs。
- 对照源消费者的负例：错误指针、外来ID、非中文、菜单返回／重绘等。
- 窗口包含动态名字／数字时，以最长真实case测容量。
- 源、旧交付、用户存档保护检查，BPS独立回放。
- 尚未做的玩法、晚期、硬件与存档兼容，而不是笼统“稳定”。

## 复现原生文本／起名消费者

```sh
python -X utf8 tools/verify_native.py --rom "local-input/source.gba" --build "outputs/v20-rebuilt" --out "outputs/native-v20"
```

在新目录复制构建结果后，运行公开 `audit_gba.py`、`test_engine.py` 与 `test_gba_name.py`。核对原文／当前tokens／字体ID／写入区域／读回，以及ARMv4T字形／文本／起名消费者。保留每脚本exit code与具体report。它们是受控测试，不能代替自然路线；逐审稿digest测试不接受未经重审的译文，这不是开发构建不支持修改。

## v22 图形补全验证

新增39项ROM-free测试、标题31/砸壶15模板、三类排行榜/救援/文件配对图集和姓名消费者测试。具体同SHA结果见 [graphics-v22-delivery.json](../evidence/graphics-v22-delivery.json)。自然标题3000与早期7000帧没有读取用户存档；其他菜单/晚期小游戏运行片段为明确fixture，不标成自然全通关。旧v20表格是历史证据，v22不靠版本号自动继承。
