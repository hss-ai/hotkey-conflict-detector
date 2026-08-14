"""core/report 单测:渲染关键标签 + 空结果 + XSS 转义。

运行: python tests/test_report.py
不依赖 Qt / 真实热键注册,CI(Session 0)可跑。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import HotkeyCombo, HotkeyResult, HotkeyStatus  # noqa: E402
from core.report import render_html, write_html  # noqa: E402


def _mk(mods: int, vk: int, status: HotkeyStatus, source: str = "") -> HotkeyResult:
    return HotkeyResult(HotkeyCombo(mods, vk), status, source)


def test_renders_key_tags() -> None:
    results = [
        _mk(3, 0x41, HotkeyStatus.OCCUPIED, "可能来自:微信截图(置信度高)"),
        _mk(2, 0x42, HotkeyStatus.SYSTEM, ""),
        _mk(4, 0x43, HotkeyStatus.FREE, ""),
    ]
    h = render_html(results, meta={"label": "基线"})
    assert "<table" in h and "</table>" in h
    assert "Ctrl+Alt+A" in h           # 组合名
    assert "微信截图" in h              # 来源提取进 Top
    assert "冲突" in h and "空闲" in h   # 卡片标签
    assert "基线" in h                  # meta label
    assert "<!DOCTYPE html>" in h
    print("[OK] 渲染含 table/组合名/来源Top/统计卡片/meta")


def test_empty_results_no_crash() -> None:
    h = render_html([], meta={})
    assert "<!DOCTYPE html>" in h
    assert "未检测到冲突组合" in h
    assert "无已知来源匹配" in h
    print("[OK] 空结果不崩溃,显示空态")


def test_xss_escaping() -> None:
    # source 含 HTML/脚本,必须被转义
    evil = "<script>alert(1)</script>&\"'"
    results = [_mk(3, 0x41, HotkeyStatus.OCCUPIED, evil)]
    h = render_html(results)
    assert "<script>alert(1)</script>" not in h, "原始 <script> 未转义!"
    assert "&lt;script&gt;" in h  # 转义后
    # meta 也转义
    h2 = render_html([], meta={"label": "<img src=x onerror=alert(1)>"})
    assert "<img src=x onerror" not in h2
    print("[OK] source/meta 的 < > & \" ' 均被 HTML 转义,无注入")


def test_write_html_file() -> None:
    import tempfile
    from pathlib import Path

    results = [_mk(3, 0x41, HotkeyStatus.OCCUPIED, "QQ")]
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "report.html"
        out = write_html(p, results)
        assert out == p and p.exists()
        content = p.read_text(encoding="utf-8")
        assert "Ctrl+Alt+A" in content
    print("[OK] write_html 落盘成功,内容可读")


def test_occupied_row_contains_suspects() -> None:
    """无证据链的冲突行,来源列附嫌疑度排序(top3,小字)。"""
    import core.report as rpt

    orig = rpt.list_process_names
    rpt.list_process_names = lambda: {"utools.exe", "explorer.exe"}
    try:
        results = [_mk(0xF, 0x20, HotkeyStatus.OCCUPIED,
                       "无法注册(已被程序/系统/钩子占用)")]
        h = render_html(results)
    finally:
        rpt.list_process_names = orig
    assert "嫌疑:" in h
    assert "uTools" in h and "★" in h
    assert 'class="suspect"' in h
    print("[OK] 冲突行附嫌疑度排序(uTools 命中)")


def main() -> int:
    test_renders_key_tags()
    test_empty_results_no_crash()
    test_xss_escaping()
    test_write_html_file()
    print("[OK] test_report 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
