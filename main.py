"""全局热键冲突检测器 - 入口。

运行:
    python main.py

依赖:PySide6(pip install PySide6)。仅支持 Windows(依赖 RegisterHotKey API)。
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    # 确保项目根在 sys.path 中(无论从哪个 cwd 启动都能 import core/ui)
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from PySide6 import QtWidgets

    from ui import MainWindow
    from ui.style import QSS

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("全局热键冲突检测器")
    app.setOrganizationName("HotkeyConflictDetector")
    app.setStyleSheet(QSS)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
