<div align="center">

# ⌨️ 全局热键冲突检测器

**Hotkey Conflict Detector — 不只告诉你哪个热键被占,还帮你推断是谁占的。**

一个 Windows 桌面工具:秒级扫描所有全局热键组合,推断占用来源嫌疑度,
守望「时好时坏」的间歇占用,快照对比装机前后的差异。

![Version](https://img.shields.io/github/v/release/hss-ai/hotkey-conflict-detector?label=%E7%89%88%E6%9C%AC&logo=git)
![License](https://img.shields.io/github/license/hss-ai/hotkey-conflict-detector?color=blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![CI](https://img.shields.io/github/actions/workflow/status/hss-ai/hotkey-conflict-detector/ci.yml?label=CI&logo=githubactions&logoColor=white)
![Downloads](https://img.shields.io/github/downloads/hss-ai/hotkey-conflict-detector/total?color=brightgreen&label=%E4%B8%8B%E8%BD%BD)

[⬇️ 下载 exe](#-快速开始) · [✨ 功能](#-功能特性) · [📖 工作原理](#-工作原理) · [🤖 AI 分析](#-ai-辅助分析可选) · [🐛 报告问题](https://github.com/hss-ai/hotkey-conflict-detector/issues)

---

<img src="assets/preview.png" alt="主界面:统计卡片 + 组合表格 + 单点检测" width="860">

</div>

## 🎯 解决什么问题

装了一堆软件后,快捷键经常打架:微信截图、QQ 截图、Snipaste、输入法、PowerToys……各自占了一堆 `Ctrl+Alt+X` / `Alt+Y`。你想给新软件设一个全局热键,却总是"注册失败",又不知道是谁在抢。

Windows **不提供**"哪个进程占用了哪个热键"的 API,所以市面工具最多告诉你"被占了"。本工具把能拿到的信号全部串起来,做成一条**诊断链路**:

> 🔍 **扫描**哪些组合被占 → 🕵️ **推断**占用来源嫌疑度(星级证据链)→
> 🔎 **二分定位**逐个关软件实锤 → ⏱ **守望**间歇性占用 → 📊 **快照对比**装机前后差异 → 🤖 可选接入 **AI** 给排查建议

- 哪些组合**已被占用**(无法再注册)、哪些是 **Windows 系统保留**(`Win+D`、`Alt+Tab`…)、哪些**空闲**可用
- 被占用的组合,给出**嫌疑度排序**(命中默认热键 / 进程在运行 / 软件类别启发式,星级区分证据强度)
- 推断不出来?**来源定位助手**引导你二分排查;**守望模式**抓"时好时坏"的间歇占用;**快照对比**直接 diff 出"装了某软件后新增的占用"

## 📦 快速开始

### 方式一:下载 exe(推荐,免装 Python)

前往 [Releases](https://github.com/hss-ai/hotkey-conflict-detector/releases),下载最新版 `HotkeyConflictDetector-x.y.z-windows-x64.exe`,**双击即可运行**。

> 💡 建议右键「以管理员身份运行」——非管理员探测时,可能因 UIPI 把管理员进程占用的热键误判为空闲。

### 方式二:源码运行

需要 **Windows** + **Python 3.10+**(依赖 Win32 `RegisterHotKey` API,零第三方依赖除 PySide6):

```bash
pip install -r requirements.txt
python main.py
```

## ✨ 功能特性

<table>
<tr>
<td width="50%" valign="top">

**🚀 秒级全量扫描**
默认 1300+ 组合,<1 秒完成。后台线程执行,UI 全程不卡;中途停止可**续扫剩余**。

**🔍 单点检测**
顶部捕获框聚焦后按下想设的热键(如 `Ctrl+Alt+J`),即时探测这一个,无需全量扫描。

**🕵️ 嫌疑度排序 + 证据链**
双击任意行 → 详情面板给出 VK 码 / 作用域 / 证据链 / 排障建议。**5★ = 精确命中该软件默认热键,4★ 及以下 = 启发式推断**——星级语义诚实区分"实锤"与"猜测"。

**🤖 AI 辅助来源分析(可选)**
自配 OpenAI 兼容端点,把热键 + 嫌疑排序 + 进程列表发给你的 LLM,换取嫌疑度排序与"改哪个软件的哪个设置"建议。[详见下文](#-ai-辅助分析可选)。

**🔎 来源定位助手(二分定位法)**
Windows 不告知占用者?引导你逐个关闭可疑软件 + 重测,状态变绿即锁定真凶。

</td>
<td width="50%" valign="top">

<img src="assets/detail.png" alt="详情诊断面板:证据链 + 嫌疑度排序 + AI 分析" width="100%">

</td>
</tr>
<tr>
<td width="50%" valign="top">

<img src="assets/locate.png" alt="来源定位(二分定位法)" width="100%">

</td>
<td width="50%" valign="top">

**⏱ 守望模式**
对一个组合持续探测,记录状态时间线,捕捉「时好时坏」的**间歇性占用**及转变瞬间的运行软件,冲突转变蜂鸣提醒。

**📁 快照对比(装机前后 diff)**
扫描结果存快照;两份快照对比「新增占用 / 已释放 / 状态变化」,并关联**当时运行的热键软件变化**——"装了 X 之后多了 3 个占用"直接可见。

**💡 空闲热键推荐**
不只告诉你哪些被占——按友好度推荐当前可安全使用的组合(`Ctrl+Alt+字母` 优先,避开 Win/小键盘)。

**📄 HTML 报告 / CSV 导出**
一键导出自包含 HTML 报告(统计卡片 + 冲突表 + 来源 Top + 嫌疑标注),或 CSV 留档。

**🎛️ 可配置扫描 + 运行软件检测**
字母 / 数字 / 功能键 / 导航 / 符号 / 小键盘 / 媒体键 / Win 组合按需勾选;状态栏实时列出运行中的热键软件、高亮当前焦点应用。

</td>
</tr>
</table>

<details>
<summary>⏱ 守望模式 / 📁 快照对比长什么样?(说明)</summary>

**守望模式**:选一个组合 + 探测间隔,后台定时探测。时间线每行记录「时刻 / 状态 / 当时运行软件」;状态在 冲突↔空闲 之间转变时蜂鸣并在摘要里高亮——专治"某软件周期性注册/注销热键"导致的时好时坏。

**快照对比**:每次扫描可存带元数据的 JSON 快照。之后任意两份对比:

```text
🆕 新增占用 (3)   ← 装机后新出现的占用
✅ 已释放 (1)     ← 装机前被占、现在空闲
🖥 热键软件变化    ← +uTools  −Snipaste(新增占用时优先排查新启动的软件)
```

</details>

<details>
<summary>🔧 用户热键库扩展(JSON)</summary>

在 `~/.hotkey_detector/user_hotkeys.json` 追加自定义软件热键(目录不存在会自动创建,可用环境变量 `HOTKEY_DETECTOR_HOME` 覆盖位置):

```json
{
  "apps": [
    {"name": "我的软件", "processes": ["myapp.exe"]}
  ],
  "hotkeys": [
    {"modifiers": ["Ctrl", "Alt"], "vk": 74, "app": "我的软件",
     "action": "截图", "processes": ["myapp.exe"]}
  ]
}
```

`modifiers` 支持整数位掩码、`["Ctrl","Alt"]` 列表或 `"Ctrl+Alt"` 字符串;`vk` 是 Win32 虚拟键码(A=0x41、J=0x4A …)。文件损坏或缺失不影响内置库;证据链与嫌疑度排序会一并考虑用户条目。

</details>

## 📖 工作原理

Windows **没有提供**"枚举所有已注册全局热键"的官方 API。但 `RegisterHotKey` 是全局唯一的——若某组合已被占用,再次注册会失败。本工具据此逐个组合试探(注册 → 立即注销):

| 注册结果 | GetLastError | 含义 | 分类 |
|---|---|---|---|
| 成功 | — | 当前空闲 | 🟢 空闲 |
| 失败 | **1409** `ERROR_HOTKEY_ALREADY_REGISTERED` | 无法注册——可能是被程序注册、系统保留或键盘钩子占用。Windows **统一返回 1409,无法区分**具体原因 | 🔴 已占用 |
| 命中已知系统键表 | — | Windows 系统级快捷键 | ⚪ 系统保留 |

> ⚠️ 经实测确认:① `RegisterHotKey` 失败**只返回 1409**(无论被谁占用;`1419` 是 `UnregisterHotKey` 的错误码,这里不会出现);② `GetLastError` 在 API 成功时可能保留上一次的残留值,所以代码**先看返回值**,只有失败时错误码才有意义;③ Windows 不提供"哪个进程占用哪个热键"的 API,来源识别只能尽力推断。

**探测期间会短暂占用目标组合(注册 → 立即注销,毫秒级),扫描极快(~0.1 秒 / 千组合),影响可忽略。** 扫描期间请勿同时按下被检测的热键。

### 🧭 能力边界(诚实说明)

本工具能可靠检测的是 `RegisterHotKey` 类全局热键的**注册冲突**(能不能注册成功)。无法可靠区分/检测:

- ☓ 占用方到底是谁(程序注册 / 系统保留 / `WH_KEYBOARD_LL` 钩子,都返回同一个 1409)——所以来源只能给**推断 + 嫌疑度**,配合「二分定位」实锤
- ☓ 应用**内部**快捷键(如 Word 的 `Ctrl+B`,只在程序内生效、不占用全局槽位)
- ☓ 管理员权限进程占用的热键(探测器非管理员时可能因 UIPI 误判为空闲)——建议**以管理员身份运行**以获得更准结果

### 🔎 星级语义(5★ 与 4★ 的区别)

- **★★★★★**:精确命中已知软件的**默认热键**(如 `Ctrl+Alt+A` ↔ QQ 截图)且进程在运行——强证据
- **★★★★☆ 及以下**:启发式累加(同按键不同修饰键 / 软件类别爱占热键 / 进程名特征),**无论怎么叠都到不了 5★**——明确弱于精确命中,不为"看起来确定"而虚标

## 🤖 AI 辅助分析(可选)

不想逐个排查?把热键 + 本地嫌疑排序 + 进程列表发给**你自己配置的** LLM,换取嫌疑度排序与具体排查建议(如"检查 PowerToys Run → Shortcut guide 设置")。

- **端点**:任意 OpenAI 兼容 `/chat/completions`(OpenAI / DeepSeek / GLM / Ollama / 中转站均可)
- **配置**:详情面板 → 「⚙ AI 设置」填 Base URL / API Key / 模型名,可一键测试连通
- **隐私**:API Key 只存本机 `~/.hotkey_detector/ai_config.json`,不进报告/快照;**不配置不联网**,只在点击「AI 分析」时发起请求;`http://` 明文端点会给出风险提示
- 请求在后台线程执行,慢网络不冻结界面

## 🚀 使用说明

1. 在"扫描范围"勾选要检测的按键类别(默认全选主流键)
2. 点 **▶ 开始扫描**——表格按冲突优先级排序,**冲突项排在最前**
3. **双击任意行**进入详情诊断(证据链 + 嫌疑度排序 + 建议)
4. 需要实锤 → 「🔎 定位占用来源」;时好时坏 → 工具栏「⏱ 守望模式」;装机排查 → 「📁 存快照」+「📊 对比快照」
5. **导出 HTML/CSV** 留档,或**复制冲突**到剪贴板

## 🛠️ 技术栈与架构

- **Python 3.10+ / PySide6 (Qt6)**,除 PySide6 外**零第三方依赖**
- Win32 调用一律 **ctypes**(`RegisterHotKey` 探测 / toolhelp32 进程枚举 / `QueryFullProcessImageNameW` 按 PID 直查)
- 分层底线:`core/` 纯检测与数据逻辑**不依赖 Qt**(CI 可在无桌面环境跑全部纯逻辑单测),`ui/` 只做界面与线程封装

```
hotkey-conflict-detector/
├── main.py                     # 入口
├── core/                       # 纯逻辑层(零 Qt,CI Session 0 可测)
│   ├── detector.py             #   RegisterHotKey 探测引擎(纯 ctypes)
│   ├── hotkeys.py              #   修饰键 / 虚拟键码 / 组合生成 / 系统保留表
│   ├── apps.py                 #   进程扫描 + 已知热键来源推断
│   ├── _known_data.py          #   内置热键库 + 用户 JSON 扩展合并
│   ├── suspect.py              #   嫌疑度排序(5★ 精确命中 / 4★ 封顶启发式)
│   ├── ai_analyze.py           #   AI 辅助分析(OpenAI 兼容,零依赖 urllib)
│   ├── snapshot.py             #   快照序列化 / diff(含热键软件环境变化)
│   ├── watch.py                #   守望状态机 + 转变检测
│   ├── recommend.py / report.py / foreground.py
│   └── _version.py             #   版本号单点真源(与 git tag 对应)
├── ui/                         # PySide6 界面层
│   ├── main_window.py          #   主窗口
│   ├── scan_thread.py          #   扫描 QThread(core 不依赖 Qt 的分层底线)
│   ├── workers.py              #   通用后台 FnWorker(网络请求防 UI 冻结)
│   ├── detail_dialog.py / locate_dialog.py / watch_dialog.py
│   ├── snapshot_dialog.py / recommend_dialog.py / ai_settings_dialog.py
│   └── models.py / style.py    #   表格模型 / QSS 语义配色单点
├── tests/                      # 各模块独立单测 + offscreen 冒烟
└── .github/workflows/          # CI(纯逻辑单测阻塞)+ 自动构建发布
```

## 💻 开发与测试

```bash
pip install -r requirements.txt

# 全部纯逻辑单测(零 Qt,任何环境可跑)
python tests/test_suspect.py && python tests/test_snapshot.py && ...

# 离屏冒烟(含真实扫描,需 Windows 桌面会话)
QT_QPA_PLATFORM=offscreen python tests/test_smoke_offscreen.py
```

> ⚠️ **CI 说明**:GitHub-hosted Windows runner 运行在 Session 0(无交互桌面),`import PySide6` / 创建 `QApplication` 会原生崩溃(本地无法复现)。因此 CI 拆两个 job:**unit**(全部纯逻辑单测,core 零 Qt,Session 0 安全,失败阻塞)+ **smoke**(需 Qt,`continue-on-error`,以本地运行为准)。

本地打包 exe:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --clean --name HotkeyConflictDetector main.py
```

## 🗓️ 更新日志

<details>
<summary>📖 展开各版本</summary>

### v1.3.0

- **快照记录热键软件环境**:diff 新增「新启动 / 已退出」的热键软件,与「新增占用」并排展示——装机排查直接看到"谁来了之后热键被抢"
- **星级语义修正**:5★ 专属「精确命中默认热键」,启发式累加封顶 4★,不再伪装确定结论
- **性能**:前台应用探测改为按 PID 直查(`OpenProcess + QueryFullProcessImageNameW`),不再每 3 秒全表扫描进程
- **AI 设置**:`http://` 明文端点风险提示(不拦保存,尊重内网自建)
- 修复:复制按钮反馈落错按钮、AI 线程生命周期、设置页测试连通冻结 UI、API Key 脱敏泄露、core 分层违规(ScanThread 迁至 ui 层)

### v1.2.0

- **嫌疑度排序**:证据链未命中时,按"命中默认热键 / 同按键改修饰键 / 软件类别 / 进程名特征"启发式打分,给出排序列表
- **AI 辅助来源分析**:自配 OpenAI 兼容端点,LLM 给出嫌疑度排序 + 排查建议
- 详情面板集成嫌疑度区块与 AI 按钮

### v1.1.0

- 快照对比 / HTML 报告 / 空闲推荐 / 前台应用上下文 / 守望模式 / 用户热键库扩展 / 扫描续扫

### v1.0.0

- 全量扫描 / 单点检测 / 证据链推断 / 二分定位 / CSV 导出

</details>

## 🏷️ 版本管理

版本号遵循 [语义化版本(SemVer)](https://semver.org/lang/zh-CN/),单点真源为 [`core/_version.py`](core/_version.py),与 git tag 一一对应(`v1.0.0` ↔ `"1.0.0"`)。推送 `v*` tag 后 GitHub Actions 自动构建 Windows exe 并发布 Release。

---

<div align="center">

**如果这个工具帮你揪出了抢热键的"真凶",欢迎点一个 ⭐ Star 让更多人看到。**

发现问题或想提功能?欢迎 [提 Issue](https://github.com/hss-ai/hotkey-conflict-detector/issues) · [提 PR](https://github.com/hss-ai/hotkey-conflict-detector/pulls)

📄 License: [MIT](LICENSE)

</div>
