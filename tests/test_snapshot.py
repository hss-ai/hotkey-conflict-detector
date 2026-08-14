"""core/snapshot 单测:序列化往返 + save/load + diff 三类 + 容错。

运行: python tests/test_snapshot.py
不依赖 Qt / 真实热键注册,CI(Session 0)可跑。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import HotkeyCombo, HotkeyResult, HotkeyStatus  # noqa: E402
from core import snapshot as snap  # noqa: E402


def _mk(mods: int, vk: int, status: HotkeyStatus, source: str = "") -> HotkeyResult:
    return HotkeyResult(HotkeyCombo(mods, vk), status, source)


def test_to_dict_fields() -> None:
    results = [
        _mk(6, 0x41, HotkeyStatus.OCCUPIED, "QQ"),
        _mk(2, 0x42, HotkeyStatus.FREE),
        _mk(8, 0x44, HotkeyStatus.SYSTEM),
    ]
    d = snap.to_dict(results, meta={"label": "装软件前"})
    assert d["schema_version"] == snap.SCHEMA_VERSION
    assert "created_at" in d and d["created_at"]
    assert d["app_version"]
    assert d["meta"]["label"] == "装软件前"
    assert d["stats"]["occupied"] == 1 and d["stats"]["free"] == 1 and d["stats"]["system"] == 1
    assert len(d["results"]) == 3
    r0 = d["results"][0]
    assert r0["modifiers"] == 6 and r0["vk"] == 0x41 and r0["status"] == "occupied"
    print("[OK] to_dict: schema/时间戳/版本/stats/results 字段齐全")


def test_save_load_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOTKEY_DETECTOR_HOME"] = tmp
        results = [_mk(6, 0x41, HotkeyStatus.OCCUPIED, "QQ"), _mk(2, 0x42, HotkeyStatus.FREE)]
        p = snap.save(results, meta={"label": "t"})
        assert p.exists()
        loaded = snap.load(p)
        assert loaded is not None
        assert len(loaded["results"]) == 2
        assert loaded["meta"]["label"] == "t"
        # list_snapshots 能列出
        snaps = snap.list_snapshots()
        assert len(snaps) == 1 and snaps[0] == p
        print(f"[OK] save→load 往返一致,快照存于 {p.name}")
    del os.environ["HOTKEY_DETECTOR_HOME"]


def test_load_missing_and_corrupt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "nope.json"
        assert snap.load(missing) is None
        corrupt = Path(tmp) / "bad.json"
        corrupt.write_text("{坏 json", encoding="utf-8")
        assert snap.load(corrupt) is None
        print("[OK] load: 缺失/损坏文件均返回 None 不崩溃")


def test_diff_three_categories() -> None:
    old = {"results": [
        {"modifiers": 6, "vk": 65, "name": "Ctrl+Alt+A", "status": "free"},
        {"modifiers": 2, "vk": 66, "name": "Ctrl+B", "status": "occupied"},
        {"modifiers": 4, "vk": 67, "name": "Shift+C", "status": "system"},
    ]}
    new = {"results": [
        {"modifiers": 6, "vk": 65, "name": "Ctrl+Alt+A", "status": "occupied"},  # free→occupied
        {"modifiers": 2, "vk": 66, "name": "Ctrl+B", "status": "free"},          # occupied→free
        {"modifiers": 4, "vk": 67, "name": "Shift+C", "status": "system"},        # 不变
        {"modifiers": 1, "vk": 68, "name": "Alt+D", "status": "occupied"},        # 新增占用
    ]}
    d = snap.diff(old, new)
    added_keys = {(e["modifiers"], e["vk"]) for e in d["added"]}
    removed_keys = {(e["modifiers"], e["vk"]) for e in d["removed"]}
    assert added_keys == {(6, 65), (1, 68)}, f"added 应为 Ctrl+Alt+A + Alt+D,实际 {added_keys}"
    assert removed_keys == {(2, 66)}, f"removed 应为 Ctrl+B,实际 {removed_keys}"
    assert d["changed"] == [], "无 same-category 细节变化"
    print(f"[OK] diff: added={added_keys} removed={removed_keys} changed=[]")


def test_diff_changed_category() -> None:
    # occupied↔system 同属冲突但 status 不同 → changed
    old = {"results": [{"modifiers": 6, "vk": 65, "status": "occupied"}]}
    new = {"results": [{"modifiers": 6, "vk": 65, "status": "system"}]}
    d = snap.diff(old, new)
    assert len(d["changed"]) == 1
    assert d["added"] == [] and d["removed"] == []
    print("[OK] diff: occupied↔system 归入 changed")


def test_snapshot_label() -> None:
    d = {"created_at": "2026-08-14T11:00:00", "stats": {"occupied": 3, "system": 1},
         "meta": {"label": "基线"}}
    label = snap.snapshot_label(d)
    assert "4 冲突" in label and "基线" in label
    print(f"[OK] snapshot_label: {label}")


def test_suspects_in_snapshot() -> None:
    """冲突项(无证据链)序列化时附嫌疑度 top3;旧快照(无 suspects)可容错读回。"""
    orig = snap.list_process_names
    snap.list_process_names = lambda: {"utools.exe", "explorer.exe"}
    try:
        results = [
            _mk(0xF, 0x20, HotkeyStatus.OCCUPIED, "无法注册(已被占用)"),
            _mk(2, 0x42, HotkeyStatus.FREE),
        ]
        d = snap.to_dict(results)
        e0 = d["results"][0]
        assert "suspects" in e0, "冲突项应有嫌疑列表"
        assert e0["suspects"][0]["app"] == "uTools"
        assert 1 <= len(e0["suspects"]) <= 3
        # free 项不附带
        assert "suspects" not in d["results"][1]
        # 读回:entries_from_dict 恢复 Suspect
        entries = snap.entries_from_dict(d)
        assert entries[0].suspects and entries[0].suspects[0].app == "uTools"
        assert entries[0].suspects[0].stars >= 3
        assert entries[1].suspects == []
        # 旧版快照(无 suspects 字段)容错
        legacy = {"results": [{"modifiers": 6, "vk": 0x41, "name": "x", "status": "occupied", "source": ""}]}
        assert snap.entries_from_dict(legacy)[0].suspects == []
        print(f"[OK] 快照含嫌疑列表:{[s['app'] for s in e0['suspects']]},旧快照容错")
    finally:
        snap.list_process_names = orig


def main() -> int:
    test_to_dict_fields()
    test_save_load_roundtrip()
    test_load_missing_and_corrupt()
    test_diff_three_categories()
    test_diff_changed_category()
    test_snapshot_label()
    print("[OK] test_snapshot 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
