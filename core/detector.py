"""全局热键冲突检测引擎。

原理:Windows 没有提供"枚举所有已注册全局热键"的官方 API,
但 `RegisterHotKey` 是全局唯一的——若某组合已被占用,再次注册会失败并返回
`ERROR_HOTKEY_ALREADY_REGISTERED (1419)`。本模块据此逐个组合试探,
立即注销探测用的注册项,从而判断每个组合当前是否被占用。

注意:
- 探测会"短暂占用"目标组合(注册→注销之间,通常在毫秒级),期间若用户正好按下
  该热键可能被拦截。扫描很快,影响极小,但 UI 仍会提示用户。
- 此法可判断"是否被占用",但 Windows 不直接告知"被谁占用"。来源识别由
  `core.apps` 做尽力而为的推断(进程扫描 + 已知热键映射)。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from PySide6 import QtCore

from .hotkeys import HotkeyCombo, SYSTEM_RESERVED


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
    source: str = ""  # 推断的占用来源(可能为空)

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


# ---------------------------------------------------------------------------
# 来源推断钩子(由 core.apps 注入,避免循环依赖)
# ---------------------------------------------------------------------------
SourceGuesser = Callable[[HotkeyCombo], str]
_source_guesser: Optional[SourceGuesser] = None


def set_source_guesser(fn: Optional[SourceGuesser]) -> None:
    """注入来源推断函数(探测到 OCCUPIED 时调用)。"""
    global _source_guesser
    _source_guesser = fn


def _guess_source(combo: HotkeyCombo) -> str:
    if _source_guesser is None:
        return ""
    try:
        return _source_guesser(combo) or ""
    except Exception:
        return ""


def _build_source(status: HotkeyStatus, err: int, combo: HotkeyCombo) -> str:
    """根据状态推断占用来源(尽力而为)。

    重要:RegisterHotKey 失败时**统一返回 1409**,无法据此区分"被程序注册 /
    系统保留 / 被键盘钩子占用"——这三类都返回 1409。因此:
    - SYSTEM(命中硬编码系统表)→ 明确"Windows 系统保留";
    - OCCUPIED → 优先用已知热键库(_guess_source)推测;推测不出就给中性诚实文案,
      不编造具体占用机制。
    """
    if status == HotkeyStatus.SYSTEM:
        return "Windows 系统保留"
    if status == HotkeyStatus.OCCUPIED:
        known = _guess_source(combo)
        if known:
            return known
        return "无法注册(已被程序/系统/钩子占用,Windows 不提供具体来源)"
    if status == HotkeyStatus.ERROR:
        return f"探测失败(错误码 {err})"
    return ""


# ---------------------------------------------------------------------------
# 后台扫描线程(QThread)
# ---------------------------------------------------------------------------
class ScanThread(QtCore.QThread):
    """在后台逐个探测组合,通过信号实时回报进度与结果。"""

    # 每探测完一个组合发出:(result)
    result_ready = QtCore.Signal(object)
    # 进度:(已完成数, 总数)
    progress = QtCore.Signal(int, int)
    # 全部结束:(统计字典)
    finished_scan = QtCore.Signal(dict)

    def __init__(self, combos: list[HotkeyCombo], parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._combos = list(combos)
        self._stop_flag = False

    def request_stop(self) -> None:
        """请求停止(在下一个组合前生效)。"""
        self._stop_flag = True

    def run(self) -> None:  # noqa: D401 - QThread 入口
        total = len(self._combos)
        stats = {"free": 0, "occupied": 0, "system": 0, "error": 0, "skipped": 0}

        for i, combo in enumerate(self._combos):
            if self._stop_flag:
                break  # 用户已请求停止,剩余项不再探测

            ok, err = _probe_raw(combo.modifiers, combo.vk)
            status = _classify(ok, err)
            source = _build_source(status, err, combo)
            result = HotkeyResult(combo=combo, status=status, source=source)
            self.result_ready.emit(result)

            key = status.value
            stats[key] = stats.get(key, 0) + 1
            self.progress.emit(i + 1, total)

        stats["scanned"] = sum(
            v for k, v in stats.items() if k != "skipped"
        )
        stats["total"] = total
        self.finished_scan.emit(stats)


__all__ = [
    "HotkeyStatus",
    "HotkeyResult",
    "HotkeyDetector",
    "ScanThread",
    "probe",
    "is_hotkey_occupied",
    "set_source_guesser",
]


# 兼容别名(便于直接 import HotkeyDetector)
class HotkeyDetector:
    """同步扫描器的薄封装(非 GUI 场景或单测使用)。"""

    def __init__(self, combos: list[HotkeyCombo]) -> None:
        self._combos = combos

    def scan(self) -> list[HotkeyResult]:
        results: list[HotkeyResult] = []
        for c in self._combos:
            ok, err = _probe_raw(c.modifiers, c.vk)
            status = _classify(ok, err)
            source = _build_source(status, err, c)
            results.append(HotkeyResult(combo=c, status=status, source=source))
        return results
