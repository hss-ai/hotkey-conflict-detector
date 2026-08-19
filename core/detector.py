"""全局热键冲突检测引擎。

原理:Windows 没有提供"枚举所有已注册全局热键"的官方 API,
但 `RegisterHotKey` 是全局唯一的——若某组合已被占用,再次注册会失败并返回
`ERROR_HOTKEY_ALREADY_REGISTERED (1409)`。本模块据此逐个组合试探,
立即注销探测用的注册项,从而判断每个组合当前是否被占用。

注意错误码区分:RegisterHotKey 失败返回 1409(已被占用);
1419 是 UnregisterHotKey 注销不存在项时的错误码,RegisterHotKey 不会产生。

注意:
- 探测会"短暂占用"目标组合(注册→注销之间,通常在毫秒级),期间若用户正好按下
  该热键可能被拦截。扫描很快,影响极小,但 UI 仍会提示用户。
- 此法可判断"是否被占用",但 Windows 不直接告知"被谁占用"。来源识别由
  `core.apps` 做尽力而为的推断(进程扫描 + 已知热键映射)。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .hotkeys import HotkeyCombo, SYSTEM_RESERVED
from .apps import build_evidence as _build_evidence, refresh_running_processes


# ---------------------------------------------------------------------------
# Win32 绑定
# ---------------------------------------------------------------------------
# 经实测确认(注册两次相同组合失败返回 1409;注销未注册项返回 1419):
ERROR_HOTKEY_ALREADY_REGISTERED = 1409  # RegisterHotKey 失败的标准码(被占用)
ERROR_HOTKEY_NOT_REGISTERED = 1419      # 仅 UnregisterHotKey 注销不存在项时返回
ERROR_INVALID_PARAMETER = 87

# use_last_error=True 让 ctypes.get_last_error() 能取到真实的 GetLastError 值
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [wintypes.HWND, wintypes.INT, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, wintypes.INT]
_user32.UnregisterHotKey.restype = wintypes.BOOL

# 探测用的热键 id(应用自己一般用 0xC000 以下,这里取高位避开)
_PROBE_IDS = (0xC000, 0xC001, 0xC002)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
class HotkeyStatus(Enum):
    """单个组合的占用状态。"""

    FREE = "free"        # 当前空闲,可成功注册
    OCCUPIED = "occupied"  # 已被某个程序/进程占用
    SYSTEM = "system"    # Windows 系统保留(常见 Win+* 组合)
    ERROR = "error"      # 探测异常(无效组合等)
    SKIPPED = "skipped"  # 扫描被停止

    @property
    def label(self) -> str:
        return {
            HotkeyStatus.FREE: "空闲",
            HotkeyStatus.OCCUPIED: "已占用",
            HotkeyStatus.SYSTEM: "系统保留",
            HotkeyStatus.ERROR: "检测异常",
            HotkeyStatus.SKIPPED: "已跳过",
        }[self]

    @property
    def is_conflict(self) -> bool:
        """是否构成"冲突"——占用或系统保留都算用户难以再注册。"""
        return self in (HotkeyStatus.OCCUPIED, HotkeyStatus.SYSTEM)


@dataclass
class HotkeyResult:
    """单个组合的检测结果。"""

    combo: HotkeyCombo
    status: HotkeyStatus
    source: str = ""        # 推断的占用来源(可能为空)
    evidence: object = None  # apps.Evidence 或 None(详情面板用)

    @property
    def name(self) -> str:
        return self.combo.name

    @property
    def modifiers(self) -> int:
        return self.combo.modifiers

    @property
    def vk(self) -> int:
        return self.combo.vk


# ---------------------------------------------------------------------------
# 同步检测(单次探测)
# ---------------------------------------------------------------------------
# 特殊标记:表内系统保留键直接返回此"错误码",不实际调用 RegisterHotKey
_SYSTEM_FLAG = -1


def _probe_raw(modifiers: int, vk: int) -> tuple[bool, int]:
    """底层探测:返回 (是否注册成功, last_error)。

    表内系统保留键直接返回失败标记,避免实际注册带来的副作用。
    """
    if (modifiers, vk) in SYSTEM_RESERVED:
        return (False, _SYSTEM_FLAG)
    ok = _user32.RegisterHotKey(None, _PROBE_IDS[0], modifiers, vk)
    err = ctypes.get_last_error()
    if ok:
        _user32.UnregisterHotKey(None, _PROBE_IDS[0])
    return (bool(ok), err)


def _classify(ok: bool, err: int) -> HotkeyStatus:
    """把 (成功, 错误码) 归类为占用状态。

    关键 1:last_error 在 API 成功时可能保留上一次的残留值(实测会残留),
    因此**必须先看返回值 ok**,只有 ok=False 时错误码才有意义。
    关键 2:RegisterHotKey 失败**统一返回 1409**,无法区分是被程序注册/系统保留/
    键盘钩子占用——所以失败一律归类 OCCUPIED,细分靠 SYSTEM 表与来源推断。
    """
    if ok:
        return HotkeyStatus.FREE
    if err == _SYSTEM_FLAG:
        return HotkeyStatus.SYSTEM
    if err == ERROR_HOTKEY_ALREADY_REGISTERED:  # 1409:已被占用(程序/系统/钩子统一)
        return HotkeyStatus.OCCUPIED
    if err == ERROR_HOTKEY_NOT_REGISTERED:  # 1419:防御性,RegisterHotKey 实际不产生此码
        return HotkeyStatus.OCCUPIED
    return HotkeyStatus.ERROR


def probe(modifiers: int, vk: int) -> HotkeyStatus:
    """探测单个组合的占用状态(便捷封装)。"""
    ok, err = _probe_raw(modifiers, vk)
    return _classify(ok, err)


def is_hotkey_occupied(modifiers: int, vk: int) -> bool:
    """便捷封装:仅返回是否被占用(系统保留也算 True)。"""
    return probe(modifiers, vk).is_conflict


def quick_probe(modifiers: int, vk: int) -> HotkeyResult:
    """单次探测一个组合,返回完整 HotkeyResult(含证据链)。供「单点检测」用。"""
    refresh_running_processes()
    return probe_result(modifiers, vk)


def probe_result(modifiers: int, vk: int) -> HotkeyResult:
    """探测单组合并解析来源(不刷新进程缓存——扫描循环先 refresh 一次再批量调)。"""
    ok, err = _probe_raw(modifiers, vk)
    status = _classify(ok, err)
    source, evidence = _resolve_source(status, err, HotkeyCombo(modifiers, vk))
    return HotkeyResult(combo=HotkeyCombo(modifiers, vk), status=status, source=source, evidence=evidence)


# ---------------------------------------------------------------------------
# 来源证据链(直接调 core.apps,无循环依赖)
# ---------------------------------------------------------------------------
def _resolve_source(status: HotkeyStatus, err: int, combo: HotkeyCombo) -> tuple[str, object]:
    """返回 (来源文本, 证据链对象)。证据链仅 OCCUPIED 且匹配已知热键时有。"""
    if status == HotkeyStatus.SYSTEM:
        return "Windows 系统保留", None
    if status == HotkeyStatus.OCCUPIED:
        ev = _build_evidence(combo)
        if ev:
            return ev.summary, ev
        return "无法注册(已被程序/系统/钩子占用,Windows 不提供具体来源)", None
    if status == HotkeyStatus.ERROR:
        return f"探测失败(错误码 {err})", None
    return "", None


# ---------------------------------------------------------------------------
# 后台扫描支持(filter_combos 纯逻辑;QThread 封装在 ui/scan_thread.py,
# core 不依赖 Qt —— 分层底线)
# ---------------------------------------------------------------------------
def filter_combos(
    combos: list[HotkeyCombo], exclude: set[tuple[int, int]] | None
) -> list[HotkeyCombo]:
    """续扫过滤:剔除已扫过的 (modifiers,vk) 组合,返回待扫列表。纯逻辑,可单测。"""
    excl = set(exclude) if exclude else set()
    return [c for c in combos if (c.modifiers, c.vk) not in excl]


__all__ = [
    "HotkeyStatus",
    "HotkeyResult",
    "HotkeyDetector",
    "filter_combos",
    "probe",
    "is_hotkey_occupied",
    "quick_probe",
    "probe_result",
]


# 兼容别名(便于直接 import HotkeyDetector)
class HotkeyDetector:
    """同步扫描器的薄封装(非 GUI 场景或单测使用)。"""

    def __init__(self, combos: list[HotkeyCombo]) -> None:
        self._combos = combos

    def scan(self) -> list[HotkeyResult]:
        refresh_running_processes()
        results: list[HotkeyResult] = []
        for c in self._combos:
            ok, err = _probe_raw(c.modifiers, c.vk)
            status = _classify(ok, err)
            source, evidence = _resolve_source(status, err, c)
            results.append(HotkeyResult(combo=c, status=status, source=source, evidence=evidence))
        return results
