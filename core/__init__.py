"""全局热键冲突检测工具 - 核心检测模块。

detector 直接调用 apps 构建来源证据链(进程缓存 + 已知热键库),
扫描前由 detector 自动 refresh 进程缓存。
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
    quick_probe,
)
from . import apps
from .apps import (
    KNOWN_APPS,
    KNOWN_HOTKEYS,
    KnownApp,
    KnownHotkey,
    Evidence,
    scan_running_hotkey_apps,
    build_evidence,
    guess_source,
    refresh_running_processes,
)

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
    "quick_probe",
    # apps
    "apps",
    "KNOWN_APPS",
    "KNOWN_HOTKEYS",
    "KnownApp",
    "KnownHotkey",
    "Evidence",
    "scan_running_hotkey_apps",
    "build_evidence",
    "guess_source",
    "refresh_running_processes",
]
