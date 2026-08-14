"""空闲热键推荐:从扫描结果筛 FREE 组合,按"友好度"排序后给出推荐。

正向输出——不仅告诉用户哪些被占,还推荐当前可安全使用的组合,
降低"我该设什么热键"的决策成本。排序启发式(借鉴常见软件默认热键习惯):

1. Ctrl+Alt+字母 最优(冲突少、好按、最常见的安全选择)
2. Ctrl+Shift+字母 次之
3. Alt+Shift / 三键 Ctrl+Alt+Shift
4. 单修饰键(Ctrl / Alt / Shift)
5. 含 Win 的最不优先(系统保留多、易撞)
键内:字母 A-Z 优先(字母序),其次数字、功能键。

纯逻辑,无 Qt 依赖,CI(Session 0)可单测。
"""
from __future__ import annotations

from typing import Any

from .hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN


# 修饰键组合 → 友好度分(越小越优);含 Win 一律最低
_MOD_SCORE: dict[int, int] = {
    MOD_CONTROL | MOD_ALT: 0,                # Ctrl+Alt
    MOD_CONTROL | MOD_SHIFT: 1,              # Ctrl+Shift
    MOD_ALT | MOD_SHIFT: 2,                  # Alt+Shift
    MOD_CONTROL | MOD_ALT | MOD_SHIFT: 3,    # Ctrl+Alt+Shift
    MOD_CONTROL: 4,
    MOD_ALT: 5,
    MOD_SHIFT: 6,
}


def _status_value(r: Any) -> str:
    return getattr(r.status, "value", str(r.status))


def _mod_score(mods: int) -> int:
    if mods & MOD_WIN:
        return 100  # 含 Win 最不优先(系统保留多)
    return _MOD_SCORE.get(mods, 50)  # 其他罕见组合居中


def _vk_tier(vk: int) -> tuple[int, int]:
    """返回(键类别分, 类别内序),越小越优。"""
    if 0x41 <= vk <= 0x5A:    # A-Z:字母序,A 最优
        return (0, vk - 0x41)
    if 0x30 <= vk <= 0x39:    # 0-9
        return (1, vk - 0x30)
    if 0x70 <= vk <= 0x87:    # F1-F24
        return (2, vk - 0x70)
    return (3, vk)            # 其他


def _sort_key(r: Any) -> tuple[int, int, int]:
    tier, inner = _vk_tier(r.vk)
    return (_mod_score(r.modifiers), tier, inner)


def recommend_free(results: list[Any], top_n: int = 12) -> list[Any]:
    """从结果里筛 FREE 组合,按友好度排序返回前 top_n 个。

    输入无 FREE 项时返回空列表。返回的是原始结果对象(含 name/source 等)。
    """
    free = [r for r in results if _status_value(r) == "free"]
    free.sort(key=_sort_key)
    if top_n <= 0:
        return []
    return free[:top_n]


__all__ = ["recommend_free"]
