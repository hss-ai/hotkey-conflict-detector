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
    KnownApp("Snipaste / 截图", ("snippingtool.exe", "screenclippinghost.exe", "snipaste.exe")),
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
KNOWN_HOTKEYS: dict[tuple[int, int], tuple[str, ...]] = {
    (MOD_CONTROL | MOD_ALT, 0x41): ("QQ 截图(默认 Ctrl+Alt+A)",),
    (MOD_ALT, 0x41): ("微信/企业微信 截图(默认 Alt+A)",),
    (MOD_CONTROL | MOD_SHIFT, 0x41): ("钉钉 截图(默认 Ctrl+Shift+A)",),
    (MOD_WIN | MOD_SHIFT, 0x53): ("Windows 截图工具(Win+Shift+S)",),
    (MOD_ALT, 0x20): ("PowerToys Run / Flow Launcher / uTools(默认 Alt+Space)",),
    (MOD_CONTROL | MOD_ALT, 0x55): ("uTools 超级面板(默认 Ctrl+Alt+U)",),
    (MOD_CONTROL, 0xC0): ("Ditto 剪贴板(默认 Ctrl+`)",),
    (MOD_CONTROL | MOD_ALT, 0x44): ("网易有道词典 划词(默认 Ctrl+Alt+D)",),
    (MOD_ALT, 0x4A): ("Jietu/截图 默认(Alt+J)",),
    (MOD_WIN | MOD_SHIFT, 0x46): ("Snipaste 截图(可设 Win+Shift+F)",),
    (MOD_CONTROL | MOD_SHIFT | MOD_ALT, 0x53): ("ShareX 截图(默认 Ctrl+Shift+Alt+S)",),
}


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


def scan_running_hotkey_apps() -> list[RunningApp]:
    """扫描正在运行的、已知会注册全局热键的软件。"""
    running = list_process_names()
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
# 单组合来源推断(注入到 detector 作为 source guesser)
# ---------------------------------------------------------------------------
def guess_source(combo: HotkeyCombo) -> str:
    """对某个被占用的组合,尽力推断来源。"""
    key = (combo.modifiers, combo.vk)
    if key in KNOWN_HOTKEYS:
        candidates = KNOWN_HOTKEYS[key]
        return "可能来自:" + " / ".join(candidates)
    return ""


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
    "RunningApp",
    "list_process_names",
    "scan_running_hotkey_apps",
    "guess_source",
    "dump_running_apps",
]
