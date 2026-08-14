"""core/watch 单测:记录序列 + 转变检测 + 冲突转变 + summary。

运行: python tests/test_watch.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.watch import WatchState  # noqa: E402


def test_record_and_current() -> None:
    s = WatchState()
    assert s.current_status is None
    assert s.transitions == []
    s.record("free", ["微信"])
    s.record("free", ["微信"])
    assert s.current_status == "free"
    assert len(s.events) == 2
    assert s.events[0].running_apps == ["微信"]
    print("[OK] record 序列 + current_status + 空 events 安全")


def test_transitions_detected() -> None:
    s = WatchState()
    s.record("free", ["A"])
    s.record("free", ["A"])
    s.record("occupied", ["A", "B"])   # free→occupied
    s.record("occupied", ["A", "B"])
    s.record("free", [])                # occupied→free
    trans = s.transitions
    assert len(trans) == 2
    assert trans[0]["from"] == "free" and trans[0]["to"] == "occupied"
    assert trans[0]["running_apps"] == ["A", "B"]
    assert trans[1]["from"] == "occupied" and trans[1]["to"] == "free"
    print(f"[OK] transitions: {len(trans)} 次转变(free↔occupied)")


def test_conflict_transitions_filter() -> None:
    s = WatchState()
    s.record("occupied", [])
    s.record("system", [])   # occupied→system(都属冲突,不算 conflict_transition)
    s.record("free", [])     # system→free(冲突→非冲突,算)
    s.record("occupied", []) # free→occupied(非冲突→冲突,算)
    assert len(s.transitions) == 3           # 全部 status 变化
    assert len(s.conflict_transitions) == 2  # 仅冲突↔非冲突
    print("[OK] conflict_transitions 过滤掉 occupied↔system 同属冲突的变化")


def test_no_change_no_transition() -> None:
    s = WatchState()
    for _ in range(5):
        s.record("free", ["A"])
    assert s.transitions == []
    print("[OK] 状态未变化 → transitions 为空")


def test_summary_text() -> None:
    s = WatchState()
    assert "尚未开始" in s.summary
    s.record("free", [])
    s.record("occupied", ["微信"])
    txt = s.summary
    assert "1 次占用状态转变" in txt
    assert "微信" in txt
    print("[OK] summary 文案正确(空/含转变/含运行软件)")


def main() -> int:
    test_record_and_current()
    test_transitions_detected()
    test_conflict_transitions_filter()
    test_no_change_no_transition()
    test_summary_text()
    print("[OK] test_watch 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
