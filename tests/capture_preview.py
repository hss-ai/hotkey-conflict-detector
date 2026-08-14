"""启动真实窗口并截图保存(开发期验证 UI 渲染用,不纳入正式测试)。

扫描完成后截图并退出:
    python tests/capture_preview.py
"""
from __future__ import annotations

import os
import sys
import time

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
    win.resize(1100, 760)
    win.show()

    # 选一个能产生丰富样本(空闲/占用/系统保留)的范围
    win._cb_letters.setChecked(True)
    win._cb_digits.setChecked(True)
    win._cb_fkeys.setChecked(True)
    win._cb_nav.setChecked(True)
    win._cb_win.setChecked(True)
    win._cb_symbols.setChecked(False)
    win._cb_space.setChecked(False)

    def capture() -> None:
        # 按组合名排序,让截图展示不同状态/作用域的混合行(而非默认"冲突在前")
        win._table.sortByColumn(0, QtCore.Qt.AscendingOrder)
        # 模拟单点检测:填入捕获框 + 触发检测
        from core import MOD_ALT  # noqa: E402
        win._capture.setText("Alt+A")
        win._quick_check(MOD_ALT, 0x41)
        app.processEvents()
        # 主界面截图
        main_path = os.path.join(ROOT, "assets", "preview.png")
        os.makedirs(os.path.dirname(main_path), exist_ok=True)
        win.grab().save(main_path)
        print(f"[OK] 主界面截图: {main_path}")
        # 详情面板截图(Alt+A,带证据链)
        r = getattr(win, "_last_quick", None)
        if r is not None:
            from ui.detail_dialog import DetailDialog  # noqa: E402
            dlg = DetailDialog(r, win)
            dlg.show()
            app.processEvents()
            detail_path = os.path.join(ROOT, "assets", "detail.png")
            dlg.grab().save(detail_path)
            print(f"[OK] 详情面板截图: {detail_path}")
            dlg.accept()
        counts = win._model.count_by_status()
        print("     状态分布:", {k.value: v for k, v in counts.items()})
        app.quit()

    def on_finished(_stats: dict) -> None:
        QtCore.QTimer.singleShot(600, capture)

    def go() -> None:
        t0 = time.time()
        win.start_scan()

        def finished(stats):
            on_finished(stats)
            print(f"     扫描耗时 {time.time() - t0:.2f}s")

        win._thread.finished_scan.connect(finished)

    QtCore.QTimer.singleShot(400, go)
    QtCore.QTimer.singleShot(40000, lambda: (print("[TIMEOUT]"), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
