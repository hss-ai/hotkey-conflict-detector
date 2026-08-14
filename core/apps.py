"""占用来源推断(尽力而为)。

Windows 不提供"哪个进程注册了哪个全局热键"的 API,因此来源识别只能做推断:
1. 进程扫描:枚举正在运行的可执行文件,匹配一份"已知会注册全局热键的软件"清单。
2. 已知热键映射:对常见软件的默认热键做映射,扫描到 OCCUPIED 时查表给出候选。

数据源(内置 + 用户扩展)见 core/_known_data:内置常量随包打包,
用户可在 ~/.hotkey_detector/user_hotkeys.json 追加自定义条目,与内置合并。

注意:推断结果不保证准确——用户可能改过快捷键,或软件热键来自配置文件。
UI 中一律显示为"可能来自 X",仅供排障参考。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from ._known_data import (
    KNOWN_APPS,
    KNOWN_HOTKEYS,
    KnownApp,
    KnownHotkey,
    invalidate_merged_cache,
    merged_known_apps,
    merged_known_hotkeys,
)
from .hotkeys import HotkeyCombo


# ---------------------------------------------------------------------------
# 数据源:re-export 自 _known_data(保持向后兼容的导入路径)
# ---------------------------------------------------------------------------
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
    "reload_known_data",
]


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
    for app in merged_known_apps():
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
    已知热键库 = 内置 + 用户扩展(merged_known_hotkeys)。
    """
    matches = merged_known_hotkeys().get((combo.modifiers, combo.vk))
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


def reload_known_data() -> None:
    """用户编辑 user_hotkeys.json 后调用:清合并缓存,下次查询重新加载。"""
    invalidate_merged_cache()


# ---------------------------------------------------------------------------
# 调试用:打印当前运行的热键软件
# ---------------------------------------------------------------------------
def dump_running_apps() -> str:
    lines = [str(app) for app in scan_running_hotkey_apps()]
    return "\n".join(lines) if lines else "(未检测到已知热键软件)"
