"""离屏冒烟测试:验证 UI 构建 + 扫描线程 + 信号流转 + 模型统计的完整链路。

运行(项目根):
    QT_QPA_PLATFORM=offscreen python tests/test_smoke_offscreen.py

CI 说明:GitHub-hosted 的 Windows runner 运行在 Session 0(无交互式桌面),
RegisterHotKey 在此环境下不可靠。检测到 CI 环境时,本测试改用构造数据验证
UI / 模型 / 筛选 / 作用域链路;真实热键探测留给本机 / 手动测试。

诊断说明:PySide6 / ui 的 import 放进 main() 内,这样即使 import 阶段失败
也会被外层 try 捕获,把 traceback 写入 job output(GITHUB_OUTPUT),便于
无 token 通过 API 查询失败原因。
"""
from __future__ import annotations

import os
import sys

# offscreen:不弹实际窗口,CI 友好(必须在 import PySide6 之前设置)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# GitHub Actions 默认置 CI=true、GITHUB_ACTIONS=true
CI = os.environ.get("CI", "").lower() == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


def _apply_minimal_range(win) -> None:
    """缩到最小扫描范围:仅数字键 + 至少 2 个修饰键 → ~110 组合,秒级完成。"""
    win._cb_letters.setChecked(False)
    win._cb_fkeys.setChecked(False)
    win._cb_nav.setChecked(False)
    win._cb_symbols.setChecked(False)
    win._cb_space.setChecked(False)
    win._cb_digits.setChecked(True)
    win._spin_min_mods.setValue(2)


def _verify_counts_and_filter(win) -> None:
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


def _verify_error_codes() -> None:
    """回归测试:占用错误码必须是 1409(曾把 docstring 写成 1419)。"""
    from core.detector import (  # noqa: E402
        ERROR_HOTKEY_ALREADY_REGISTERED,
        ERROR_HOTKEY_NOT_REGISTERED,
    )

    assert ERROR_HOTKEY_ALREADY_REGISTERED == 1409, (
        f"占用错误码应为 1409,实际 {ERROR_HOTKEY_ALREADY_REGISTERED}"
    )
    assert ERROR_HOTKEY_NOT_REGISTERED == 1419, (
        f"注销错误码应为 1419,实际 {ERROR_HOTKEY_NOT_REGISTERED}"
    )
    print("[OK] 错误码一致: RegisterHotKey 占用=1409, UnregisterHotKey 注销=1419")


def _verify_resume() -> None:
    """续扫逻辑:filter_combos 剔除已扫 + ScanThread 接受 exclude(构造数据)。"""
    from core import HotkeyCombo, ScanThread  # noqa: E402
    from core.detector import filter_combos  # noqa: E402

    combos = [HotkeyCombo(m, v) for m in (1, 2, 3) for v in (0x41, 0x42)]  # 6 个
    scanned = {(1, 0x41), (2, 0x42)}  # 假设已扫 2 个
    pending = filter_combos(combos, scanned)
    assert len(pending) == 4, f"续扫应剩 4 个,实际 {len(pending)}"
    assert all((c.modifiers, c.vk) not in scanned for c in pending)
    th = ScanThread(combos, exclude=scanned)
    assert th._exclude == scanned, "ScanThread._exclude 未正确接收"
    assert len(th._combos) == 6, "原始 combos 不应被修改"
    print("[OK] 续扫: filter_combos 剔除已扫 + ScanThread exclude 生效")


def _verify_snapshot_ui() -> None:
    """快照 UI 链路:存两份快照 → 对比对话框构建 + diff 填充(构造数据)。"""
    import tempfile  # noqa: E402
    from core import snapshot as _snap  # noqa: E402
    from ui.snapshot_dialog import SnapshotCompareDialog  # noqa: E402
    from core import HotkeyCombo, HotkeyResult, HotkeyStatus  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOTKEY_DETECTOR_HOME"] = tmp
        old = [HotkeyResult(HotkeyCombo(2, 0x41), HotkeyStatus.FREE)]
        new = [HotkeyResult(HotkeyCombo(2, 0x41), HotkeyStatus.OCCUPIED, "X")]
        _snap.save(old, meta={"label": "旧"})
        _snap.save(new, meta={"label": "新"})
        dlg = SnapshotCompareDialog()
        assert dlg._cb_old.count() == 2, "应列出 2 份快照"
        assert dlg._result_layout.count() >= 3, "应填 3 个分类区"
        print("[OK] 快照 UI: 两份快照 → 对比对话框构建 + diff 填充正常")
    os.environ.pop("HOTKEY_DETECTOR_HOME", None)


def _verify_recommend_ui() -> None:
    """推荐 UI:RecommendDialog 构建并正确筛选空闲组合(构造数据)。"""
    from core import HotkeyCombo, HotkeyResult, HotkeyStatus  # noqa: E402
    from ui.recommend_dialog import RecommendDialog  # noqa: E402

    results = [
        HotkeyResult(HotkeyCombo(3, 0x41), HotkeyStatus.FREE),     # Ctrl+Alt+A 空闲
        HotkeyResult(HotkeyCombo(8, 0x44), HotkeyStatus.SYSTEM),   # Win+D 占用
    ]
    dlg = RecommendDialog(results)
    assert dlg._rec, "应筛出空闲组合"
    assert dlg._rec[0].name == "Ctrl+Alt+A", f"首推应为 Ctrl+Alt+A,实际 {dlg._rec[0].name}"
    print(f"[OK] 推荐 UI: RecommendDialog 构建,首推 {dlg._rec[0].name}")


def _verify_watch_ui() -> None:
    """守望 UI:WatchDialog 构建(时间线表 + 开始按钮初始禁用)。"""
    from ui.watch_dialog import WatchDialog  # noqa: E402

    dlg = WatchDialog()
    assert dlg._table.columnCount() == 3, "时间线表应有 3 列"
    assert dlg._btn_toggle.isEnabled() is False, "未捕获组合前开始按钮应禁用"
    print("[OK] 守望 UI: WatchDialog 构建(3 列时间线表,按钮初始禁用)")


def main() -> int:
    # import 放进函数内:即使 import 阶段失败,外层 try 也能捕获并输出诊断
    from PySide6 import QtCore, QtWidgets  # noqa: E402
    from ui import MainWindow  # noqa: E402
    from ui.style import QSS  # noqa: E402

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
    _verify_error_codes()
    _verify_resume()
    _verify_snapshot_ui()
    _verify_recommend_ui()
    _verify_watch_ui()

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
        last = tb.strip().splitlines()[-1] if tb.strip() else "(无 traceback)"
        print(f"::error::冒烟测试失败:{last}")
        # 写入 job output,可通过公开 API 查询(无需 token 看 annotation)
        gho = os.environ.get("GITHUB_OUTPUT")
        if gho:
            with open(gho, "a", encoding="utf-8") as f:
                f.write(f"smoke_error<<EOF\n{tb}\nEOF\n")
        print(tb)
        raise SystemExit(1)
