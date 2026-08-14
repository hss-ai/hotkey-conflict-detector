# hotkey-conflict-detector 工作区约定

> 引用全局规则:`~/.zcode/AGENTS.md`(通用协作规则)。本文件只写本项目专属内容,不重复通用规则。

## 项目概述
Windows 全局热键冲突检测器(Python 3.10+ / PySide6)。用 `RegisterHotKey` 探测法判断哪些全局热键组合被占用,帮助排查快捷键冲突。

## 架构分层(底线)
- `core/` 纯检测/数据逻辑,**不依赖 Qt**:`detector` / `apps` / `hotkeys` / `snapshot` / `report` / `recommend` / `foreground` / `watch` / `_known_data` / `_version`。core **不 import ui**(分层底线,HTML 报告等"展示逻辑"也定义自己的配色常量)。
- `ui/` PySide6 界面:`main_window` + 各 `*_dialog` + `models` / `style`。Win32 调用经 core。
- `tests/` 各模块独立单测 + offscreen 冒烟。

## 测试约定(重要)
- 风格:`tests/test_xxx.py` 可独立 `python tests/test_xxx.py` 运行,`main()` 返回 0/1,**不用 pytest**。
- 纯逻辑测试**必须 CI(Session 0)可跑**,不依赖真实 RegisterHotKey;需要真实 Win32 的部分用 monkeypatch 或构造数据。
- offscreen:`QT_QPA_PLATFORM=offscreen python tests/test_smoke_offscreen.py`。CI 检测 `CI=true` 走构造数据,本机走真实扫描。
- 冒烟里每个验证是独立 `_verify_xxx()` 函数 + 在 `main()` 调用,便于聚合与新功能扩展。

## MOD 位掩码(Win32,易踩坑)
`MOD_ALT=0x1 / MOD_CONTROL=0x2 / MOD_SHIFT=0x4 / MOD_WIN=0x8`。常见组合:Ctrl+Alt=3、Ctrl+Shift=**6**、Ctrl+Alt+Shift=7。**6 是 Ctrl+Shift 不是 Ctrl+Alt**(写测试期望组合名字符串时曾踩坑)。

## 版本与发版
- 单点真源 `core/_version.py`(SemVer),与 git tag `vX.Y.Z` 一一对应。
- 发版流程:改版本号 → 提交 → `git tag vX.Y.Z && git push origin vX.Y.Z` → `.github/workflows/release.yml` 自动 PyInstaller 构建 exe + 发布 GitHub Release。
- 本地打包:`pyinstaller --noconsole --onefile --clean --name HotkeyConflictDetector main.py`(产物约 48MB)。
- 错误码:RegisterHotKey 占用失败 = **1409**(1419 是 UnregisterHotKey 注销不存在项的码,易混)。

## 零依赖原则
除 PySide6 外**不引入第三方依赖**;Win32 调用一律 ctypes(进程枚举用 toolhelp32,前台窗口用 GetForegroundWindow)。配色从 `ui/style.py` 取语义色,不散落硬编码 #xxx。

## 用户热键库扩展(v1.1+)
`~/.hotkey_detector/user_hotkeys.json`(可用环境变量 `HOTKEY_DETECTOR_HOME` 覆盖目录)。与内置库(`core/_known_data.py`)合并;损坏/缺失不影响内置。`modifiers` 支持 int 位掩码、`["Ctrl","Alt"]` 列表或 `"Ctrl+Alt"` 字符串。`build_evidence` 会一并考虑用户条目。

## 并发提交注意
本仓库可能有并发会话(如 CI 诊断优化)用 `git add -A` 提交。**每次提交用具体文件 `git add <files>`**(不用 -A),减少互相卷入;合并 main 前 `git fetch` 确认不落后,必要时 rebase 整理 message 与内容不符的 commit。

## UI 对话框循环导入规避
子对话框(如 `watch_dialog`)若需组合捕获框,**内联实现**而非 `import main_window.HotkeyCaptureEdit`,避免循环导入(范例见 `ui/watch_dialog.py:_ComboCapture`)。

## 已知能力边界(诚实,写入 README/详情面板)
- RegisterHotKey 失败统一返回 1409,**无法区分**被程序注册 / 系统保留 / `WH_KEYBOARD_LL` 钩子占用;来源靠 `core/apps.build_evidence` 尽力推断(置信度标注)。
- 应用**内部**快捷键(Word 的 Ctrl+B)不占全局槽位,探测不到。
- 管理员进程占用的热键,非管理员探测可能因 UIPI 误判空闲 → 建议以管理员身份运行。
- **CI 冒烟测试受限于 Session 0**:GitHub-hosted Windows runner 无交互桌面,`import PySide6`/创建 `QApplication` 原生崩溃,本地无法复现。CI smoke job 设 `continue-on-error`(失败不阻塞),冒烟测试以本地 `QT_QPA_PLATFORM=offscreen python tests/test_smoke_offscreen.py` 为准。
