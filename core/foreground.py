"""前台窗口进程探测:取当前焦点窗口的进程,判断是否为已知热键软件。

app-specific 概念的检测器化:在状态栏提示"当前焦点是 X(已知热键软件)",
让用户意识到前台应用可能占用某些全局热键。

注意:应用"内部"快捷键(如 Word 的 Ctrl+B)不占全局槽位、本工具探测不到,
这里只提示该软件"可能是热键软件",不声称能列出其内部快捷键。
Win32 调用一律 ctypes,失败(无前台窗口/Session 0)返回空,不崩溃。
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from ._known_data import merged_known_apps
from .apps import _kernel32


# ---------------------------------------------------------------------------
# Win32 绑定
# ---------------------------------------------------------------------------
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD

# 按 PID 直查进程名(避免 toolhelp32 全表扫描——主窗口 3s 轮询一次太浪费)
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


def process_name_by_pid(pid: int) -> str:
    """按 PID 直接查询进程可执行文件名(小写);查不到返回空串。

    OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + QueryFullProcessImageNameW,
    不做全进程表快照。权限不足(受保护进程)或进程已退出时返回空串。
    """
    if pid <= 0:
        return ""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle or handle == wintypes.HANDLE(-1).value:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        _kernel32.CloseHandle(handle)


def get_foreground_process() -> tuple[int, str]:
    """返回 (pid, 进程名小写)。无前台窗口/失败时返回 (0, "")。"""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return (0, "")
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_val = pid.value
    if not pid_val:
        return (0, "")
    return (pid_val, process_name_by_pid(pid_val))


def get_foreground_hotkey_hint() -> tuple[str, bool]:
    """返回 (展示名, 是否已知热键软件)。

    - 已知热键软件:(应用展示名, True)
    - 普通应用:(进程名, False)
    - 无前台窗口/查不到:("", False)
    UI 据此决定是否高亮/加图标提示。
    """
    _pid, name = get_foreground_process()
    if not name:
        return ("", False)
    for app in merged_known_apps():
        if name in app.processes:
            return (app.name, True)
    return (name, False)


__all__ = [
    "process_name_by_pid",
    "get_foreground_process",
    "get_foreground_hotkey_hint",
]
