"""占用来源推断(尽力而为)。

Windows 不提供"哪个进程注册了哪个全局热键"的 API,因此来源识别只能做推断:
1. 进程扫描:枚举正在运行的可执行文件,匹配一份"已知会注册全局热键的软件"清单。
2. 已知热键映射:对常见软件的默认热键做硬编码映射,扫描到 OCCUPIED 时查表给出候选。

注意:推断结果不保证准确——用户可能改过快捷键,或软件热键来自配置文件。
UI 中一律显示为"可能来自 X",仅供排障参考。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from .hotkeys import (
    HotkeyCombo,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    modifier_name,
    vk_name,
)


# ---------------------------------------------------------------------------
# 已知热键软件:进程名(小写) → 应用展示名
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KnownApp:
    name: str          # 展示名
    processes: tuple[str, ...]  # 可能的进程名(小写)


KNOWN_APPS: tuple[KnownApp, ...] = (
    KnownApp("Microsoft PowerToys", ("powertoys.exe", "fancyzones.exe", "keyboardmanagerengine.exe", "powerlauncher.exe")),
    KnownApp("AutoHotkey", ("autohotkey.exe", "autohotkey64.exe", "autohotkey32.exe", "autohotkey64_unicode.exe")),
    KnownApp("微信 WeChat", ("wechat.exe",)),
    KnownApp("QQ", ("qq.exe",)),
    KnownApp("TIM", ("tim.exe",)),
    KnownApp("钉钉 DingTalk", ("dingtalk.exe", "dingtalklauncher.exe")),
    KnownApp("企业微信", ("wxwork.exe",)),
    KnownApp("Snipaste", ("snipaste.exe",)),
    KnownApp("ShareX", ("sharex.exe",)),
    KnownApp("Windows 截图工具", ("snippingtool.exe", "screenclippinghost.exe")),
    KnownApp("Everything", ("everything.exe",)),
    KnownApp("Listary", ("listary.exe",)),
    KnownApp("Flow Launcher", ("flow.launcher.exe",)),
    KnownApp("Wox", ("wox.exe",)),
    KnownApp("uTools", ("utools.exe",)),
    KnownApp("Quicker", ("quicker.exe",)),
    KnownApp("网易云音乐", ("cloudmusic.exe",)),
    KnownApp("QQ音乐", ("qqmusic.exe",)),
    KnownApp("PotPlayer", ("potplayermini64.exe", "potplayermini.exe", "potplayer.exe")),
    KnownApp("VLC", ("vlc.exe",)),
    KnownApp("OBS Studio", ("obs64.exe", "obs32.exe")),
    KnownApp("Bandicam", ("bdcam.exe",)),
    KnownApp("Ditto(剪贴板)", ("ditto.exe",)),
    KnownApp("腾讯会议", ("wemeetapp.exe",)),
    KnownApp("Zoom", ("zoom.exe",)),
    KnownApp("网易有道词典", ("youdaodict.exe",)),
    KnownApp("火绒安全", ("hipstray.exe", "hipsdaemon.exe", "usysdiag.exe")),
    KnownApp("360 系列", ("360tray.exe", "360safe.exe", "zhudongfangyu.exe")),
    KnownApp("搜狗输入法", ("sogoucloud.exe", "sgtool.exe", "soGouSvc.exe")),
    KnownApp("Fluent Search", ("fluentsearch.exe",)),
    KnownApp("Raycast(若跨平台)", ("raycast.exe",)),
)


# ---------------------------------------------------------------------------
# 已知默认热键:(modifiers, vk) → 候选来源描述
# 多个软件可能用同一组合时,都列出。键名仅供参考。
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KnownHotkey:
    """一条已知软件默认热键记录。"""

    app: str                    # 展示名
    action: str                 # 功能描述
    processes: tuple[str, ...]  # 判断"是否在运行"用的进程名(小写)


# 已知软件的默认全局热键 → 应用记录(用于来源证据链推断)
# 注意:这是"默认值",用户可能改过;仅作排障参考。
KNOWN_HOTKEYS: dict[tuple[int, int], tuple[KnownHotkey, ...]] = {
    (MOD_CONTROL | MOD_ALT, 0x41): (KnownHotkey("QQ", "截图", ("qq.exe",)),),
    (MOD_ALT, 0x41): (
        KnownHotkey("微信", "截图", ("wechat.exe",)),
        KnownHotkey("企业微信", "截图", ("wxwork.exe",)),
    ),
    (MOD_CONTROL | MOD_SHIFT, 0x41): (KnownHotkey("钉钉", "截图", ("dingtalk.exe", "dingtalklauncher.exe")),),
    (MOD_WIN | MOD_SHIFT, 0x53): (KnownHotkey("Windows 截图工具", "截图", ("snippingtool.exe", "screenclippinghost.exe")),),
    (MOD_ALT, 0x20): (
        KnownHotkey("PowerToys Run", "启动器", ("powerlauncher.exe", "powertoys.exe")),
        KnownHotkey("Flow Launcher", "启动器", ("flow.launcher.exe",)),
        KnownHotkey("uTools", "启动器", ("utools.exe",)),
    ),
    (MOD_CONTROL | MOD_ALT, 0x55): (KnownHotkey("uTools", "超级面板", ("utools.exe",)),),
    (MOD_CONTROL, 0xC0): (KnownHotkey("Ditto", "剪贴板", ("ditto.exe",)),),
    (MOD_CONTROL | MOD_ALT, 0x44): (KnownHotkey("网易有道词典", "划词", ("youdaodict.exe",)),),
    (MOD_WIN | MOD_SHIFT, 0x46): (KnownHotkey("Snipaste", "截图", ("snipaste.exe",)),),
    (MOD_CONTROL | MOD_SHIFT | MOD_ALT, 0x53): (KnownHotkey("ShareX", "截图", ("sharex.exe",)),),
}


@dataclass
class Evidence:
    """单条占用来源的证据链 + 置信度。"""

    app: str                       # 主来源(应用名)
    action: str                    # 功能
    checks: list[tuple[str, str]]  # (检查项, 符号 ✓/△/✗/?)
    stars: int                     # 0-5
    confidence: str                # 高/中/低

    @property
    def summary(self) -> str:
        """表格/列表用的一句话摘要。"""
        star = "★" * self.stars + "☆" * (5 - self.stars)
        return f"可能来自:{self.app}{self.action}(置信度{self.confidence} {star})"


# ---------------------------------------------------------------------------
# 进程枚举(toolhelp32,纯 ctypes 无第三方依赖)
# ---------------------------------------------------------------------------
TH32CS_SNAPPROCESS = 0x00000002
_MAX_PATH = 260


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * _MAX_PATH),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


def list_process_names() -> set[str]:
    """返回当前所有进程的可执行文件名集合(小写)。"""
    names: set[str] = set()
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return names
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if _kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                names.add(entry.szExeFile.lower())
                if not _kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        _kernel32.CloseHandle(snapshot)
    return names


@dataclass
class RunningApp:
    name: str           # 应用展示名
    matched: str        # 匹配到的进程名

    def __str__(self) -> str:
        return f"{self.name} ({self.matched})"


# 当前运行进程缓存(build_evidence 判断"app 是否运行"用;扫描前 refresh 一次)
_running_processes: set[str] = set()


def refresh_running_processes() -> set[str]:
    """刷新进程缓存,返回当前所有进程名集合(小写)。"""
    global _running_processes
    _running_processes = list_process_names()
    return _running_processes


def scan_running_hotkey_apps() -> list[RunningApp]:
    """扫描正在运行的、已知会注册全局热键的软件(顺带刷新进程缓存)。"""
    running = refresh_running_processes()
    found: list[RunningApp] = []
    seen: set[str] = set()
    for app in KNOWN_APPS:
        for proc in app.processes:
            if proc in running and app.name not in seen:
                found.append(RunningApp(name=app.name, matched=proc))
                seen.add(app.name)
                break
    return found


# ---------------------------------------------------------------------------
# 单组合来源证据链
# ---------------------------------------------------------------------------
def build_evidence(combo: HotkeyCombo) -> Evidence | None:
    """对某个被占用的组合,构建来源证据链(尽力而为)。

    置信度依据:命中已知默认热键(★2)+ 该软件进程在运行(★2)+ 探测到注册失败(★1)。
    Windows 不提供"哪个进程占用"的 API,故即便全部命中也只能到 5★,无法"已确认"。
    """
    matches = KNOWN_HOTKEYS.get((combo.modifiers, combo.vk))
    if not matches:
        return None
    kh = matches[0]  # 多候选时取首个,详情面板可展开全部
    running = any(p in _running_processes for p in kh.processes)
    checks: list[tuple[str, str]] = [
        (f"{kh.app} 进程{'在运行' if running else '未检测到'}", "✓" if running else "△"),
        (f"命中 {kh.app} 默认热键", "✓"),
        ("RegisterHotKey 注册失败(本工具探测)", "✓"),
        ("API 直接确认归属", "✗ Windows 不支持"),
    ]
    stars = (2 if running else 0) + 2 + 1  # 最多 5
    confidence = "高" if stars >= 5 else "中" if stars >= 3 else "低"
    return Evidence(app=kh.app, action=kh.action, checks=checks, stars=stars, confidence=confidence)


def guess_source(combo: HotkeyCombo) -> str:
    """对某个被占用的组合,返回来源摘要(兼容旧接口)。"""
    ev = build_evidence(combo)
    return ev.summary if ev else ""


# ---------------------------------------------------------------------------
# 调试用:打印当前运行的热键软件
# ---------------------------------------------------------------------------
def dump_running_apps() -> str:
    lines = [str(app) for app in scan_running_hotkey_apps()]
    return "\n".join(lines) if lines else "(未检测到已知热键软件)"


__all__ = [
    "KNOWN_APPS",
    "KNOWN_HOTKEYS",
    "KnownApp",
    "KnownHotkey",
    "RunningApp",
    "Evidence",
    "list_process_names",
    "refresh_running_processes",
    "scan_running_hotkey_apps",
    "build_evidence",
    "guess_source",
    "dump_running_apps",
]
