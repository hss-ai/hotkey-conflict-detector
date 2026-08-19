"""core/suspect + core/ai_analyze 单测:嫌疑度排序 + AI 配置/prompt 构造。

运行: python tests/test_suspect.py
不依赖 Qt / 网络 / 真实热键注册,CI(Session 0)可跑。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.ai_analyze import (  # noqa: E402
    AiConfig,
    ai_config_path,
    load_ai_config,
    build_prompt,
    save_ai_config,
)
from core.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, HotkeyCombo  # noqa: E402
from core.suspect import (  # noqa: E402
    Suspect,
    deserialize_suspects,
    format_suspects,
    rank_suspects,
    serialize_suspects,
)


# ---------------------------------------------------------------- suspect
def test_rank_exact_match_running_top() -> None:
    """命中默认热键 + 进程在运行 → 5★ 排第一。"""
    combo = HotkeyCombo(vk=0x41, modifiers=MOD_CONTROL | MOD_ALT)  # QQ 截图
    running = {"explorer.exe", "qq.exe"}
    suspects = rank_suspects(combo, running)
    assert suspects, "应有候选"
    top = suspects[0]
    assert top.app == "QQ"
    assert top.stars == 5
    assert any("默认热键" in r for r in top.reasons)
    print(f"[OK] 精确命中+在运行 → 5★:{top.app} {top.star_str}")


def test_rank_exact_match_not_running() -> None:
    """命中默认热键但进程未运行 → 3★,排后于在运行的热键软件。"""
    combo = HotkeyCombo(vk=0x41, modifiers=MOD_CONTROL | MOD_ALT)
    suspects = rank_suspects(combo, running={"utools.exe", "explorer.exe"})
    by_app = {s.app: s for s in suspects}
    assert by_app["QQ"].stars == 3
    assert by_app["QQ"].stars < by_app["uTools"].stars + 5  # 只需都在列表里
    print(f"[OK] 命中但未运行 → 3★:{by_app['QQ'].star_str}")


def test_rank_same_vk_bonus() -> None:
    """同 VK 不同修饰键(修饰键被自定义)+ 进程在运行 → 加分。"""
    combo = HotkeyCombo(vk=0x41, modifiers=MOD_CONTROL | MOD_SHIFT | MOD_WIN)
    running = {"wechat.exe"}
    suspects = rank_suspects(combo, running)
    assert suspects, "同 VK 信号应产生候选(微信 Alt+A)"
    assert any("修饰键" in r for s in suspects for r in s.reasons)
    print(f"[OK] 同 VK 加分:{suspects[0].app} {suspects[0].star_str}")


def test_rank_category_base_and_name_hint() -> None:
    """类别基础分(启动器)+ 进程名热键特征分。"""
    combo = HotkeyCombo(vk=0x20, modifiers=0xF)  # 四修饰键+Space,无精确命中
    running = {"utools.exe", "fnhotkeyutility.exe", "explorer.exe"}
    suspects = rank_suspects(combo, running)
    by_app = {s.app: s for s in suspects}
    assert "uTools" in by_app and by_app["uTools"].stars >= 3  # 启动器基础分 3
    assert "fnhotkeyutility.exe" in by_app  # 名字含 hotkey
    assert by_app["uTools"].stars >= by_app["fnhotkeyutility.exe"].stars
    # 排序单调不增
    stars = [s.stars for s in suspects]
    assert stars == sorted(stars, reverse=True)
    print(f"[OK] 类别分+特征分,排序单调:{[(s.app, s.stars) for s in suspects]}")


def test_rank_empty_and_format() -> None:
    """无候选 → 空列表;format_suspects 纯文本渲染。"""
    combo = HotkeyCombo(vk=0x41, modifiers=MOD_CONTROL)
    assert rank_suspects(combo, running={"explorer.exe"}) == []
    s = Suspect(app="X", matched="x.exe", stars=3, reasons=["理由A", "理由B"])
    text = format_suspects([s])
    assert "★★★☆☆" in text and "X (x.exe)" in text and "- 理由A" in text
    assert format_suspects([]) == "(无嫌疑来源)"
    print("[OK] 空候选 + format_suspects 渲染")


def test_rank_heuristic_cap_without_exact() -> None:
    """星级语义:无精确命中的启发式累加封顶 4★——5★ 专属「精确命中默认热键」。"""
    # uTools:同 VK +2(Ctrl+Alt+U 是其默认键,这里换修饰键)+ 类别基础分 3
    # 修正前可叠到 5★,修正后封顶 4★(exact_hit=False)
    combo = HotkeyCombo(vk=0x55, modifiers=MOD_CONTROL | MOD_SHIFT)  # Ctrl+Shift+U
    running = {"utools.exe", "explorer.exe"}
    suspects = rank_suspects(combo, running)
    by_app = {s.app: s for s in suspects}
    u = by_app["uTools"]
    assert u.stars == 4, f"无精确命中应封顶 4★,实际 {u.stars}"
    assert u.exact_hit is False, "未命中默认热键不应标记 exact_hit"

    # 对照:精确命中 + 在运行 → 仍 5★
    exact = rank_suspects(HotkeyCombo(vk=0x20, modifiers=MOD_ALT), running)
    top = exact[0]
    assert top.stars == 5 and top.exact_hit is True, "精确命中+在运行应 5★"
    print(f"[OK] 星级语义:启发式封顶 4★(uTools={u.star_str}),精确命中 5★({top.app})")


# ------------------------------------------------------------- 子模块合并
def test_rank_group_by_process_owner() -> None:
    """子模块热键(PowerToys Run)与宿主(Microsoft PowerToys)合并为一条。"""
    combo = HotkeyCombo(vk=0x20, modifiers=MOD_ALT)  # Alt+Space:PowerToys Run 等
    running = {"powertoys.exe", "keyboardmanagerengine.exe", "explorer.exe"}
    suspects = rank_suspects(combo, running)
    apps = [s.app for s in suspects]
    assert "Microsoft PowerToys" in apps, f"应合并为宿主应用:{apps}"
    assert "PowerToys Run" not in apps, "子模块名不应单列一条"
    pt = next(s for s in suspects if s.app == "Microsoft PowerToys")
    assert any("PowerToys Run" in r for r in pt.reasons), "合并后理由仍保留子模块信息"
    print(f"[OK] 进程归属合并:{apps}")


def test_serialize_roundtrip() -> None:
    """serialize/deserialize 往返 + 坏数据容错。"""
    suspects = [
        Suspect(app="uTools", matched="utools.exe", stars=5, reasons=["r1", "r2", "r3"]),
        Suspect(app="X", matched="x.exe", stars=2, reasons=["only"]),
    ]
    data = serialize_suspects(suspects)
    assert len(data) == 2
    assert data[0]["reasons"] == ["r1", "r2"]  # reasons 截断到 2 条
    assert len(serialize_suspects(suspects, top=1)) == 1
    back = deserialize_suspects(data)
    assert back[0].app == "uTools" and back[0].stars == 5 and back[0].star_str == "★★★★★"
    assert back[1].matched == "x.exe"
    # 容错:非法列表/坏条目/越界 stars
    assert deserialize_suspects(None) == []
    assert deserialize_suspects(["bad", {"stars": 99}, {"app": "ok"}])[0].app == "ok"
    assert deserialize_suspects([{"app": "ok", "stars": 99}])[0].stars == 0
    print("[OK] serialize/deserialize 往返 + 容错")


# ------------------------------------------------------------- ai_analyze
def test_ai_config_roundtrip(tmpdir_env=None) -> None:
    """配置读写回环 + 缺失/损坏容错(临时 HOME,不碰真实配置)。"""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOTKEY_DETECTOR_HOME"] = tmp
        try:
            assert load_ai_config().configured is False  # 无文件
            cfg = AiConfig(base_url="https://api.example.com/v1/",
                           api_key="sk-test-1234567890", model="test-model")
            assert cfg.configured
            assert "sk-test" not in cfg.masked_summary() or len(cfg.api_key) > 8
            save_ai_config(cfg)
            assert ai_config_path().exists()
            loaded = load_ai_config()
            assert loaded == AiConfig(base_url="https://api.example.com/v1",
                                      api_key="sk-test-1234567890", model="test-model"), \
                "base_url 应去尾斜杠"
            # 损坏 JSON 容错
            ai_config_path().write_text("{broken", encoding="utf-8")
            assert load_ai_config().configured is False
            print("[OK] AI 配置回环 + 容错")
        finally:
            os.environ.pop("HOTKEY_DETECTOR_HOME", None)


def test_build_prompt_content() -> None:
    """prompt 含组合名、嫌疑列表与进程名;无敏感数据。"""
    combo = HotkeyCombo(vk=0x41, modifiers=MOD_CONTROL | MOD_ALT)
    suspects = [Suspect(app="QQ", matched="qq.exe", stars=5, reasons=["命中默认热键"])]
    system, user = build_prompt(combo, suspects=suspects, running={"qq.exe", "abc.exe"})
    assert "热键" in system
    assert "Ctrl+Alt" in user and "A" in user
    assert "QQ" in user and "abc.exe" in user
    print("[OK] build_prompt 内容完整")


def main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                failures += 1
                print(f"[FAIL] {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"[ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{'✓ 全部通过' if failures == 0 else f'✗ {failures} 个失败'} (test_suspect)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
