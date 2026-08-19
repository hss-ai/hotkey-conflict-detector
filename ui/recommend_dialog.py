"""空闲热键推荐对话框:展示当前可安全使用的空闲组合,支持复制。

基于 core.recommend.recommend_free 的友好度排序(Ctrl+Alt+字母 优先)。
正向输出——不仅告诉用户哪些被占,还推荐可用的组合。
"""
from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from core.recommend import recommend_free

from .style import BORDER, SELECT_BG, TEXT_MUTED, TEXT_PRIMARY


class RecommendDialog(QtWidgets.QDialog):
    """展示推荐的空闲热键组合。"""

    def __init__(self, results: list[Any], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._rec = recommend_free(results, top_n=12)
        self.setWindowTitle("💡 推荐可用热键")
        self.resize(420, 480)
        self._build()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        intro = QtWidgets.QLabel(
            "以下组合当前空闲,可安全用作全局热键(按友好度排序):\n"
            "优先 Ctrl+Alt+字母 → Ctrl+Shift+字母 → …,避开 Win/小键盘。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{TEXT_MUTED};")
        root.addWidget(intro)

        if not self._rec:
            tip = QtWidgets.QLabel("ⓘ 当前没有空闲组合可供推荐。\n请先扫描,或缩小占用范围后再试。")
            tip.setStyleSheet(f"padding:24px;color:{TEXT_MUTED};")
            tip.setAlignment(QtCore.Qt.AlignCenter)
            root.addWidget(tip, 1)
        else:
            self._listw = QtWidgets.QListWidget()
            for r in self._rec:
                item = QtWidgets.QListWidgetItem(f"{r.name}")
                item.setToolTip(f"可用 · {r.name}(空闲,可注册)")
                self._listw.addItem(item)
            self._listw.setStyleSheet(
                f"QListWidget::item{{padding:8px 10px;border-bottom:1px solid {BORDER};}}"
                f"QListWidget::item:selected{{background:{SELECT_BG};color:{TEXT_PRIMARY};}}"
                "font-family:Consolas,monospace;font-size:14px;"
            )
            root.addWidget(self._listw, 1)

        # 按钮
        btns = QtWidgets.QHBoxLayout()
        btn_copy = QtWidgets.QPushButton("📋 复制推荐列表")
        btn_copy.setEnabled(bool(self._rec))
        btn_copy.clicked.connect(self._copy)
        btns.addWidget(btn_copy)
        btns.addStretch(1)
        btn_close = QtWidgets.QPushButton("关闭")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_close)
        root.addLayout(btns)

    def _copy(self) -> None:
        if not self._rec:
            return
        lines = ["# 推荐可用热键(全局热键冲突检测器)", ""]
        lines.extend(r.name for r in self._rec)
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))
        self._sb_feedback("✓ 已复制")

    def _sb_feedback(self, text: str) -> None:
        # 简单反馈:改关闭按钮文案 0.8s
        btn = self.findChild(QtWidgets.QPushButton, "primary")
        if btn is not None:
            orig = btn.text()
            btn.setText(text)
            QtCore.QTimer.singleShot(800, lambda: btn.setText(orig))


__all__ = ["RecommendDialog"]
