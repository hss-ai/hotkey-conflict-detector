"""core/recommend 单测:排序优先级 + top_n 截断 + 空输入。

运行: python tests/test_recommend.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import HotkeyCombo, HotkeyResult, HotkeyStatus  # noqa: E402
from core.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN  # noqa: E402
from core.recommend import recommend_free  # noqa: E402


def _mk(mods: int, vk: int, status: HotkeyStatus = HotkeyStatus.FREE) -> HotkeyResult:
    return HotkeyResult(HotkeyCombo(mods, vk), status)


def test_priority_ordering() -> None:
    results = [
        _mk(MOD_WIN, 0x58),                       # Win+X
        _mk(MOD_CONTROL, 0x42),                    # Ctrl+B(单修饰)
        _mk(MOD_CONTROL | MOD_SHIFT, 0x41),        # Ctrl+Shift+A
        _mk(MOD_CONTROL | MOD_ALT, 0x41),          # Ctrl+Alt+A ← 应排第一
        _mk(MOD_CONTROL | MOD_ALT, 0x42),          # Ctrl+Alt+B
    ]
    rec = recommend_free(results, top_n=10)
    names = [r.name for r in rec]
    assert names[0] == "Ctrl+Alt+A", f"首个应为 Ctrl+Alt+A,实际 {names[0]}"
    assert names[1] == "Ctrl+Alt+B", f"次个应为 Ctrl+Alt+B,实际 {names[1]}"
    assert names[2] == "Ctrl+Shift+A", f"第三应为 Ctrl+Shift+A,实际 {names[2]}"
    # Win+X 应排在最后(含 Win 最不优先)
    assert names[-1] == "Win+X", f"Win+X 应最后,实际 {names[-1]}"
    print(f"[OK] 排序优先级: {names}")


def test_letter_before_digit() -> None:
    # 同为 Ctrl+Alt:字母 A 优于数字 1
    results = [_mk(MOD_CONTROL | MOD_ALT, 0x31), _mk(MOD_CONTROL | MOD_ALT, 0x41)]
    rec = recommend_free(results, top_n=5)
    assert rec[0].name == "Ctrl+Alt+A"
    assert rec[1].name == "Ctrl+Alt+1"
    print("[OK] 同修饰下字母优先于数字")


def test_top_n_truncation() -> None:
    results = [_mk(MOD_CONTROL | MOD_ALT, 0x41 + i) for i in range(20)]  # 20 个 FREE
    assert len(recommend_free(results, top_n=5)) == 5
    assert len(recommend_free(results, top_n=12)) == 12
    assert len(recommend_free(results, top_n=0)) == 0
    assert len(recommend_free(results, top_n=100)) == 20
    print("[OK] top_n 截断正确(5/12/0/超量)")


def test_no_free_returns_empty() -> None:
    results = [
        _mk(MOD_CONTROL | MOD_ALT, 0x41, HotkeyStatus.OCCUPIED),
        _mk(MOD_CONTROL | MOD_ALT, 0x42, HotkeyStatus.SYSTEM),
    ]
    assert recommend_free(results, top_n=10) == []
    assert recommend_free([], top_n=10) == []
    print("[OK] 无 FREE 项 / 空输入均返回 []")


def main() -> int:
    test_priority_ordering()
    test_letter_before_digit()
    test_top_n_truncation()
    test_no_free_returns_empty()
    print("[OK] test_recommend 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
