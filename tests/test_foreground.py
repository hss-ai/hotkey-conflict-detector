"""core/foreground 单测:hint 文案逻辑(mock,不依赖真实窗口)。

运行: python tests/test_foreground.py
注:get_foreground_process 依赖真实 Win32 前台窗口,Session 0 下返回空;
    本测试 monkeypatch 它,只验 hint 逻辑(UI 真正关心的部分)。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import core.foreground as fg  # noqa: E402


def _patch(return_value):
    """把 get_foreground_process 替换为返回固定值(还原在 finally)。"""
    original = fg.get_foreground_process
    fg.get_foreground_process = lambda: return_value
    return lambda: setattr(fg, "get_foreground_process", original)


def test_hint_known_app() -> None:
    restore = _patch((1234, "wechat.exe"))
    try:
        name, known = fg.get_foreground_hotkey_hint()
        assert known is True, "wechat.exe 应识别为已知热键软件"
        assert "微信" in name
    finally:
        restore()
    print(f"[OK] 已知热键软件(wechat.exe)→ ({name}, {known})")


def test_hint_unknown_app() -> None:
    restore = _patch((5678, "notepad.exe"))
    try:
        name, known = fg.get_foreground_hotkey_hint()
        assert known is False
        assert name == "notepad.exe"
    finally:
        restore()
    print(f"[OK] 普通应用(notepad.exe)→ ({name}, {known})")


def test_hint_no_window() -> None:
    restore = _patch((0, ""))
    try:
        name, known = fg.get_foreground_hotkey_hint()
        assert name == "" and known is False
    finally:
        restore()
    print("[OK] 无前台窗口/Session0 → ('', False) 优雅返回")


def test_process_name_by_pid_lowercase() -> None:
    """真实功能:查自身进程名,验证小写化与 PID 直查(OpenProcess 路径)可用。"""
    name = fg.process_name_by_pid(os.getpid())
    assert name and name.islower(), f"应返回小写进程名,实际 {name!r}"
    assert "python" in name, f"自身进程应含 python,实际 {name!r}"
    print(f"[OK] process_name_by_pid(自身 PID)→ {name!r}(已小写)")


def test_process_name_by_pid_invalid() -> None:
    """无效/不存在的 PID:直查安全返回空串(OpenProcess 失败路径不崩)。"""
    assert fg.process_name_by_pid(0) == ""
    assert fg.process_name_by_pid(-1) == ""
    # 0x7FFFFFFF 远超 Windows PID 取值范围,OpenProcess 必失败 → 空串
    assert fg.process_name_by_pid(0x7FFFFFFF) == ""
    print("[OK] process_name_by_pid: 无效/超范围 PID → 空串")


def main() -> int:
    test_hint_known_app()
    test_hint_unknown_app()
    test_hint_no_window()
    test_process_name_by_pid_lowercase()
    test_process_name_by_pid_invalid()
    print("[OK] test_foreground 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
