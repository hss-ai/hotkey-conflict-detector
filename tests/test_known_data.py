"""core/_known_data 单测:内置库 + 用户 JSON 扩展 + 合并。

运行: python tests/test_known_data.py
不依赖 Qt / 真实热键注册,CI(Session 0)可跑。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core._known_data import (  # noqa: E402
    KNOWN_APPS,
    KNOWN_HOTKEYS,
    invalidate_merged_cache,
    load_user_data,
    merged_known_apps,
    merged_known_hotkeys,
    parse_modifiers,
    user_hotkeys_path,
)
from core.apps import build_evidence  # noqa: E402
from core.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, HotkeyCombo  # noqa: E402


def test_builtin_nonempty() -> None:
    assert len(KNOWN_APPS) >= 25, f"内置 apps 过少: {len(KNOWN_APPS)}"
    assert len(KNOWN_HOTKEYS) >= 8, f"内置 hotkeys 过少: {len(KNOWN_HOTKEYS)}"
    # 内置 QQ 截图 Ctrl+Alt+A 存在
    assert (MOD_CONTROL | MOD_ALT, 0x41) in KNOWN_HOTKEYS
    print(f"[OK] 内置库非空: {len(KNOWN_APPS)} apps, {len(KNOWN_HOTKEYS)} 热键")


def test_parse_modifiers() -> None:
    assert parse_modifiers(6) == 6
    assert parse_modifiers(["Ctrl", "Alt"]) == MOD_CONTROL | MOD_ALT
    assert parse_modifiers("Ctrl+Alt+Shift") == MOD_CONTROL | MOD_ALT | MOD_SHIFT
    assert parse_modifiers(["win", "super"]) == 0x8  # win == super == MOD_WIN
    assert parse_modifiers("未知键") == 0
    assert parse_modifiers(True) == 0  # bool 排除
    print("[OK] parse_modifiers: int / list / string / 未知 / bool 全覆盖")


def _setup_user_dir(tmpdir: str, payload: dict | str) -> None:
    """把 payload 写入临时用户目录的 user_hotkeys.json。"""
    os.makedirs(tmpdir, exist_ok=True)
    path = os.path.join(tmpdir, "user_hotkeys.json")
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(payload, str):
            f.write(payload)
        else:
            json.dump(payload, f, ensure_ascii=False)
    invalidate_merged_cache()


def test_user_load_and_merge() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOTKEY_DETECTOR_HOME"] = tmp
        _setup_user_dir(tmp, {
            "apps": [
                {"name": "我的软件", "processes": ["myapp.exe", "MyApp2.EXE"]},
            ],
            "hotkeys": [
                {"modifiers": ["Ctrl", "Alt"], "vk": 74, "app": "我的软件",
                 "action": "截图", "processes": ["myapp.exe"]},
            ],
        })

        apps, hotkeys = load_user_data()
        assert len(apps) == 1 and apps[0].name == "我的软件"
        assert apps[0].processes == ("myapp.exe", "myapp2.exe")  # 小写化
        assert (MOD_CONTROL | MOD_ALT, 74) in hotkeys
        assert hotkeys[(MOD_CONTROL | MOD_ALT, 74)][0].app == "我的软件"

        # 合并:用户 app 出现在 merged_known_apps 末尾
        merged_apps = merged_known_apps()
        assert any(a.name == "我的软件" for a in merged_apps)
        # 合并:用户热键叠加到内置(Ctrl+Alt+A 仍含 QQ,用户 J 新增)
        merged_hk = merged_known_hotkeys()
        assert (MOD_CONTROL | MOD_ALT, 74) in merged_hk
        assert (MOD_CONTROL | MOD_ALT, 0x41) in merged_hk  # 内置未丢
        print("[OK] 用户 JSON 加载 + 与内置合并正确")

    del os.environ["HOTKEY_DETECTOR_HOME"]
    invalidate_merged_cache()


def test_corrupt_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOTKEY_DETECTOR_HOME"] = tmp
        # 损坏 JSON
        _setup_user_dir(tmp, "{这不是合法 json")
        apps, hotkeys = load_user_data()
        assert apps == [] and hotkeys == {}
        # 合并回退到纯内置
        assert len(merged_known_hotkeys()) == len(KNOWN_HOTKEYS)
        print("[OK] 损坏 JSON 不崩溃,优雅回退到内置")

        # 文件不存在
        os.remove(user_hotkeys_path())
        invalidate_merged_cache()
        apps2, hotkeys2 = load_user_data()
        assert apps2 == [] and hotkeys2 == {}
        print("[OK] 文件不存在返回空")

    del os.environ["HOTKEY_DETECTOR_HOME"]
    invalidate_merged_cache()


def test_build_evidence_hits_user_entry() -> None:
    """用户自填条目也能被证据链命中(US-002 核心价值)。"""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOTKEY_DETECTOR_HOME"] = tmp
        _setup_user_dir(tmp, {
            "hotkeys": [
                {"modifiers": "Ctrl+Alt", "vk": 75, "app": "自定义工具",
                 "action": "贴图", "processes": ["customtool.exe"]},
            ],
        })
        combo = HotkeyCombo(MOD_CONTROL | MOD_ALT, 75)  # Ctrl+Alt+K
        ev = build_evidence(combo)
        assert ev is not None, "用户条目未被证据链命中"
        assert ev.app == "自定义工具"
        assert ev.confidence in ("中", "低", "高")
        print(f"[OK] build_evidence 命中用户条目: {ev.app}{ev.action}")

    del os.environ["HOTKEY_DETECTOR_HOME"]
    invalidate_merged_cache()


def main() -> int:
    test_builtin_nonempty()
    test_parse_modifiers()
    test_user_load_and_merge()
    test_corrupt_json()
    test_build_evidence_hits_user_entry()
    print("[OK] test_known_data 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
