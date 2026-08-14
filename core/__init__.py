"""全局热键冲突检测工具 - 核心检测模块。

导入本包即自动把 `apps.guess_source` 注入为 detector 的来源推断钩子,
使扫描到的"已占用"组合能附带推测来源。
"""

from .hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    MOD_ORDER,
    MOD_NAMES,
    VK_MAP,
    SYSTEM_RESERVED,
    HotkeyCombo,
    generate_combos,
    format_combo,
    modifier_name,
    vk_name,
)
from .detector import (
    HotkeyStatus,
    HotkeyResult,
    HotkeyDetector,
    ScanThread,
    probe,
    is_hotkey_occupied,
    set_source_guesser,
)
from . import apps
from .apps import (
    KNOWN_APPS,
    KNOWN_HOTKEYS,
    scan_running_hotkey_apps,
    guess_source,
)

# 自动注入来源推断钩子
set_source_guesser(guess_source)

__all__ = [
    # hotkeys
    "MOD_ALT",
    "MOD_CONTROL",
    "MOD_SHIFT",
    "MOD_WIN",
    "MOD_ORDER",
    "MOD_NAMES",
    "VK_MAP",
    "SYSTEM_RESERVED",
    "HotkeyCombo",
    "generate_combos",
    "format_combo",
    "modifier_name",
    "vk_name",
    # detector
    "HotkeyStatus",
    "HotkeyResult",
    "HotkeyDetector",
    "ScanThread",
    "probe",
    "is_hotkey_occupied",
    "set_source_guesser",
    # apps
    "apps",
    "KNOWN_APPS",
    "KNOWN_HOTKEYS",
    "scan_running_hotkey_apps",
    "guess_source",
]
