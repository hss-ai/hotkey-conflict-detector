"""离屏冒烟测试:验证 UI 构建 + 扫描线程 + 信号流转 + 模型统计的完整链路。

运行(项目根):
    QT_QPA_PLATFORM=offscreen python tests/test_smoke_offscreen.py

CI 说明:GitHub-hosted 的 Windows runner 运行在 Session 0(无交互式桌面),
RegisterHotKey 在此环境下不可靠。检测到 CI 环境时,本测试改用构造数据验证
UI / 模型 / 筛选 / 作用域链路;真实热键探测留给本机 / 手动测试。
"""
from __future__ import annotations

import os
import sys

# offscreen:不弹实际窗口,CI 友好
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6 import QtCore, QtWidgets  # noqa: E402

from ui import MainWindow  # noqa: E402
from ui.style import QSS  # noqa: E402


# GitHub Actions 默认置 CI=true、GITHUB_ACTIONS=true
CI = os.environ.get("CI", "").lower() == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


def _apply_minimal_range(win: MainWindow) -> None:
    """缩到最小扫描范围:仅数字键 + 至少 2 个修饰键 → ~110 组合,秒级完成。"""
    win._cb_letters.setChecked(False)
    win._cb_fkeys.setChecked(False)
    win._cb_nav.setChecked(False)
    win._cb_symbols.setChecked(False)
    win._cb_space.setChecked(False)
    win._cb_digits.setChecked(True)
    win._spin_min_mods.setValue(2)


def _verify_counts_and_filter(win: MainWindow) -> None:
    """公共断言:行数 == 生成组合数;「仅冲突」筛选 == 占用 + 系统数。"""
    counts = win._model.count_by_status()
    total = sum(counts.values())
    combos = win._build_combos()
    print(f"[OK] 模型总行数 = {total}")
    print("     状态分布:", {k.value: v for k, v in counts.items()})
    assert total == len(combos), f"行数 {total} != 组合数 {len(combos)}"
    print(f"[OK] 行数匹配生成组合数 ({len(combos)})")

    win._proxy.set_conflict_only(True)
    shown = win._proxy.rowCount()
    conflict = sum(
        v for k, v in counts.items()
        if k.value in ("occupied", "system")
    )
    assert shown == conflict, f"仅冲突筛选 {shown} != 冲突数 {conflict}"
    print(f"[OK] 「仅冲突」筛选显示 {shown} 行(冲突 {conflict})")
    win._proxy.set_conflict_only(False)


def _verify_scope_mapping() -> None:
    """验证「作用域」列映射(不依赖真实扫描结果,直接构造各状态)。"""
    from core import HotkeyCombo, HotkeyResult, HotkeyStatus  # noqa: E402
    from ui.models import COL_SCOPE, HotkeyTableModel  # noqa: E402

    scope_model = HotkeyTableModel()
    scope_model.reset_results([
        HotkeyResult(HotkeyCombo(1, 0x41), HotkeyStatus.OCCUPIED, "x"),
        HotkeyResult(HotkeyCombo(8, 0x44), HotkeyStatus.SYSTEM, ""),
        HotkeyResult(HotkeyCombo(2, 0x42), HotkeyStatus.FREE, ""),
        HotkeyResult(HotkeyCombo(4, 0x43), HotkeyStatus.ERROR, ""),
    ])
    scope_expect = {0: "全局占用", 1: "系统级", 2: "—", 3: "—"}
    for row, want in scope_expect.items():
        got = scope_model.index(row, COL_SCOPE).data()
        assert got == want, f"作用域行{row}: 期望 {want!r}, 实际 {got!r}"
    print("[OK] 作用域映射: OCCUPIED→全局占用 / SYSTEM→系统级 / FREE,ERROR→—")


def _verify_vk_regression() -> None:
    """回归测试:F1-F24 的 VK 码(曾错位一位:0x6F→F1 的 bug)。"""
    from core.hotkeys import vk_name  # noqa: E402

    assert vk_name(0x70) == "F1", f"VK_F1 映射错误: {vk_name(0x70)}"
    assert vk_name(0x87) == "F24", f"VK_F24 映射错误: {vk_name(0x87)}"
    assert vk_name(0x6F) == "Num/", "0x6F 应为小键盘除号,而非 F1"
    print("[OK] F1-F24 VK 码映射正确(0x70=F1 … 0x87=F24)")


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = MainWindow()
    _apply_minimal_range(win)

    if CI:
        # Session 0 无交互式桌面,RegisterHotKey 不可靠 —— 用构造数据验证模型链路
        from core import HotkeyCombo, HotkeyResult, HotkeyStatus  # noqa: E402

        combos = win._build_combos()
        fake = [
            HotkeyResult(c, HotkeyStatus.OCCUPIED if i % 3 == 0 else HotkeyStatus.FREE)
            for i, c in enumerate(combos)
        ]
        win._model.reset_results(fake)
        print(f"[CI] 跳过真实 RegisterHotKey 扫描(Session 0 无桌面),"
              f"用 {len(fake)} 条构造数据验证模型链路")
    else:
        # 真实扫描:验证扫描线程 + 信号流转
        state = {"done": False}

        def on_done(_stats: dict) -> None:
            state["done"] = True
            app.quit()

        def go() -> None:
            win.start_scan()
            assert win._thread is not None, "扫描线程未启动"
            win._thread.finished_scan.connect(on_done)

        QtCore.QTimer.singleShot(0, go)
        # 超时保护:15 秒未完成视为失败
        QtCore.QTimer.singleShot(15000, lambda: (print("[TIMEOUT] 扫描超时"), app.quit()))
        app.exec()
        assert state["done"], "扫描未完成(超时或异常)"
        print("[OK] 扫描完成")

    # 公共验证(两种模式都跑)
    _verify_counts_and_filter(win)
    _verify_scope_mapping()
    _verify_vk_regression()

    print("[OK] 冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        import traceback
        tb = traceback.format_exc()
        # GitHub Actions 工作流命令:::error:: 会创建公开可见的 annotation,便于无 token 诊断
        last = tb.strip().splitlines()[-1] if tb.strip() else "(无 traceback)"
        print(f"::error::冒烟测试失败:{last}")
        print(tb)
        raise SystemExit(1)
