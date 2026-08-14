"""离屏冒烟测试:验证 UI 构建 + 扫描线程 + 信号流转 + 模型统计的完整链路。

运行(项目根):
    QT_QPA_PLATFORM=offscreen python tests/test_smoke_offscreen.py
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


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = MainWindow()

    # 缩到最小扫描范围:仅数字键 + 至少 2 个修饰键 → ~110 组合,秒级完成
    win._cb_letters.setChecked(False)
    win._cb_fkeys.setChecked(False)
    win._cb_nav.setChecked(False)
    win._cb_symbols.setChecked(False)
    win._cb_space.setChecked(False)
    win._cb_digits.setChecked(True)
    win._spin_min_mods.setValue(2)

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

    code = app.exec()

    assert state["done"], "扫描未完成(超时或异常)"
    counts = win._model.count_by_status()
    total = sum(counts.values())
    print(f"[OK] 扫描完成,模型总行数 = {total}")
    print("     状态分布:", {k.value: v for k, v in counts.items()})

    # 验证:行数应等于生成组合数
    combos = win._build_combos()
    assert total == len(combos), f"行数 {total} != 组合数 {len(combos)}"
    print(f"[OK] 行数匹配生成组合数 ({len(combos)})")

    # 验证筛选代理
    win._proxy.set_conflict_only(True)
    shown = win._proxy.rowCount()
    conflict_in_model = sum(
        v for k, v in counts.items()
        if k.value in ("occupied", "system")
    )
    assert shown == conflict_in_model, f"仅冲突筛选 {shown} != 冲突数 {conflict_in_model}"
    print(f"[OK] 「仅冲突」筛选显示 {shown} 行(冲突 {conflict_in_model})")
    win._proxy.set_conflict_only(False)

    # 验证「作用域」列映射(不依赖真实扫描结果,直接构造各状态)
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

    print("[OK] 冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
