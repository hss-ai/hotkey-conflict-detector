"""热键定义:修饰键标志、虚拟键码表、组合生成与格式化。

本模块纯数据/逻辑,不依赖任何 GUI 或系统调用,方便单测。
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import chain
from typing import Iterator


# ---------------------------------------------------------------------------
# 修饰键标志(与 Win32 MOD_* 常量一致)
# ---------------------------------------------------------------------------
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# 修饰键 → 可读名(按 Ctrl/Alt/Shift/Win 习惯顺序输出)
MOD_ORDER: tuple[int, ...] = (MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN)
MOD_NAMES: dict[int, str] = {
    MOD_CONTROL: "Ctrl",
    MOD_ALT: "Alt",
    MOD_SHIFT: "Shift",
    MOD_WIN: "Win",
}

# 所有单修饰键,用于生成非空子集
_ALL_MODS: tuple[int, ...] = (MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN)


# ---------------------------------------------------------------------------
# 虚拟键码(VK)→ 可读名
# ---------------------------------------------------------------------------
def _build_vk_map() -> dict[int, str]:
    base: dict[int, str] = {
        0x08: "Backspace",
        0x09: "Tab",
        0x0D: "Enter",
        0x13: "Pause",
        0x14: "CapsLock",
        0x1B: "Esc",
        0x20: "Space",
        0x21: "PageUp",
        0x22: "PageDown",
        0x23: "End",
        0x24: "Home",
        0x25: "Left",
        0x26: "Up",
        0x27: "Right",
        0x28: "Down",
        0x2D: "Insert",
        0x2E: "Delete",
        # 数字 0-9
        **{0x30 + i: str(i) for i in range(10)},
        # 字母 A-Z
        **{0x41 + i: chr(ord("A") + i) for i in range(26)},
        # 功能键 F1-F24
        **{0x6F + i: f"F{i + 1}" for i in range(24)},
        # 符号键(OEM)
        0xBA: ";",
        0xBB: "=",
        0xBC: ",",
        0xBD: "-",
        0xBE: ".",
        0xBF: "/",
        0xC0: "`",
        0xDB: "[",
        0xDC: "\\",
        0xDD: "]",
        0xDE: "'",
    }
    return base


VK_MAP: dict[int, str] = _build_vk_map()


def vk_name(vk: int) -> str:
    """返回虚拟键码的可读名,未知键码回退为 `VK0xXX`。"""
    return VK_MAP.get(vk, f"VK0x{vk:02X}")


# ---------------------------------------------------------------------------
# 系统保留热键(Windows 默认占用,RegisterHotKey 会失败)
# 用于在 UI 中标注"系统保留",与"第三方应用占用"区分。
# 格式:(modifiers, vk) 的集合。
# ---------------------------------------------------------------------------
SYSTEM_RESERVED: set[tuple[int, int]] = {
    # Win 组合(大量由 Windows Shell/系统占用,RegisterHotKey 会失败/返回 1409)
    (MOD_WIN, 0x44),   # Win+D  桌面
    (MOD_WIN, 0x45),   # Win+E  资源管理器
    (MOD_WIN, 0x52),   # Win+R  运行
    (MOD_WIN, 0x4C),   # Win+L  锁屏
    (MOD_WIN, 0x4D),   # Win+M  最小化全部
    (MOD_WIN, 0x09),   # Win+Tab 任务视图
    (MOD_WIN, 0x20),   # Win+Space 输入法切换
    (MOD_WIN, 0x49),   # Win+I  设置
    (MOD_WIN, 0x50),   # Win+P  投影
    (MOD_WIN, 0x41),   # Win+A  操作中心
    (MOD_WIN, 0x53),   # Win+S  搜索
    (MOD_WIN, 0x56),   # Win+V  剪贴板历史
    (MOD_WIN, 0x58),   # Win+X  快速链接菜单
    (MOD_WIN, 0x54),   # Win+T  任务栏循环
    (MOD_WIN, 0x4E),   # Win+N  通知中心
    # 其他系统级切换/菜单键(实测 RegisterHotKey 返回失败/1409)
    (MOD_ALT, 0x09),              # Alt+Tab      任务切换
    (MOD_ALT, 0x20),              # Alt+Space    窗口系统菜单
    (MOD_CONTROL, 0x1B),          # Ctrl+Esc     开始菜单
    (MOD_CONTROL | MOD_ALT, 0x2E),  # Ctrl+Alt+Del 安全注意序列
    (MOD_CONTROL | MOD_ALT, 0x09),  # Ctrl+Alt+Tab 任务切换(持久)
}
# Win+0..9:任务栏快捷键(切换/启动任务栏对应位应用),系统保留
SYSTEM_RESERVED.update((MOD_WIN, 0x30 + i) for i in range(10))


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HotkeyCombo:
    """一个待检测的热键组合。"""

    modifiers: int  # 修饰键位掩码(MOD_* 的或)
    vk: int  # 虚拟键码

    @property
    def name(self) -> str:
        return format_combo(self.modifiers, self.vk)

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# 组合生成
# ---------------------------------------------------------------------------
def _modifier_subsets(
    include_win: bool = True,
    min_modifiers: int = 1,
) -> Iterator[int]:
    """生成所有合法的修饰键位掩码(非空子集)。

    - include_win: 是否包含 Win 键组合(系统占用多,可关闭以加速)。
    - min_modifiers: 至少需要几个修饰键(1=含单修饰键组合)。
    """
    mods = _ALL_MODS if include_win else tuple(m for m in _ALL_MODS if m != MOD_WIN)
    n = len(mods)
    # 枚举所有非空子集(位掩码)
    for mask in range(1, 1 << n):
        combined = 0
        bits = 0
        for i in range(n):
            if mask & (1 << i):
                combined |= mods[i]
                bits += 1
        if bits >= min_modifiers:
            yield combined


def generate_combos(
    include_win: bool = True,
    min_modifiers: int = 1,
    letters: bool = True,
    digits: bool = True,
    function_keys: bool = True,
    navigation: bool = True,
    symbols: bool = True,
    space: bool = True,
) -> list[HotkeyCombo]:
    """根据筛选条件生成待检测的热键组合列表。"""
    vks: list[int] = []
    if letters:
        vks.extend(range(0x41, 0x5B))  # A-Z
    if digits:
        vks.extend(range(0x30, 0x3A))  # 0-9
    if function_keys:
        vks.extend(range(0x70, 0x88))  # F1-F24
    if navigation:
        vks.extend(
            [
                0x08, 0x09, 0x0D, 0x13, 0x14, 0x1B, 0x20,
                0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
            ]
        )
    if symbols:
        vks.extend([0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xDB, 0xDC, 0xDD, 0xDE])
    if space and 0x20 not in vks:
        vks.append(0x20)

    # 去重保序
    seen: set[int] = set()
    unique_vks: list[int] = []
    for v in vks:
        if v not in seen:
            seen.add(v)
            unique_vks.append(v)

    combos: list[HotkeyCombo] = []
    for mod_mask in _modifier_subsets(include_win, min_modifiers):
        for vk in unique_vks:
            combos.append(HotkeyCombo(modifiers=mod_mask, vk=vk))
    return combos


def format_combo(modifiers: int, vk: int) -> str:
    """把(修饰键, 键码)格式化为 `Ctrl+Alt+Del` 风格字符串。"""
    parts: list[str] = []
    for m in MOD_ORDER:
        if modifiers & m:
            parts.append(MOD_NAMES[m])
    parts.append(vk_name(vk))
    return "+".join(parts)


def modifier_name(modifiers: int) -> str:
    """仅修饰键部分的名字,如 `Ctrl+Alt`。"""
    parts = [MOD_NAMES[m] for m in MOD_ORDER if modifiers & m]
    return "+".join(parts) if parts else "(none)"


__all__ = [
    "MOD_ALT",
    "MOD_CONTROL",
    "MOD_SHIFT",
    "MOD_WIN",
    "MOD_ORDER",
    "MOD_NAMES",
    "VK_MAP",
    "SYSTEM_RESERVED",
    "HotkeyCombo",
    "vk_name",
    "format_combo",
    "modifier_name",
    "generate_combos",
]
