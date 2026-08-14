"""来源定位助手:Windows 不告知热键被谁占用时的二分定位工具。

流程:列出正在运行的可疑软件 → 用户手动关闭一个 → 点「重新检测」→
状态从占用变空闲,则刚关的就是占用者。
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from core import (
    HotkeyCombo,
    HotkeyStatus,
    quick_probe,
    scan_running_hotkey_apps,
)

from .style import status_color


class LocateSourceDialog(QtWidgets.QDialog):
    """对一个被占用的热键,通过逐个关软件 + 重测来定位占用者。"""

    def __init__(self, combo: HotkeyCombo, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._combo = combo
        self._last_status: HotkeyStatus | None = None
        self.setWindowTitle(f"定位占用来源 · {combo.name}")
        self.setMinimumWidth(520)
        self._build()
        self._last_status = self._do_check().status

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        intro = QtWidgets.QLabel(
            f"<b style='font-size:15px'>{self._combo.name}</b><br><br>"
            "Windows 不直接告知热键被谁占用。用<b>二分定位法</b>:<br>"
            "① 从下面挑一个可疑软件并<b>手动关闭</b>它 → "
            "② 点「重新检测」→ ③ 状态一旦变<b>绿</b>,刚关的就是占用者。"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        # 当前状态徽章
        self._status_lbl = QtWidgets.QLabel()
        self._status_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._status_lbl.setStyleSheet("font-size:15px;font-weight:600;padding:8px;border-radius:6px;")
        root.addWidget(self._status_lbl)

        # "我刚关闭了" 下拉
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("我刚关闭了:"))
        self._suspect = QtWidgets.QComboBox()
        apps = scan_running_hotkey_apps()
        for a in apps:
            self._suspect.addItem(f"{a.name} ({a.matched})")
        if not apps:
            self._suspect.addItem("(未检测到已知热键软件)")
        self._suspect.addItem("(其他软件 — 直接关你怀疑的即可)")
        row.addWidget(self._suspect, 1)
        root.addLayout(row)

        # 重新检测按钮
        self._btn = QtWidgets.QPushButton("🔄  重新检测此热键")
        self._btn.setObjectName("primary")
        self._btn.clicked.connect(self._on_check)
        root.addWidget(self._btn)

        # 结果
        self._result = QtWidgets.QLabel("关闭一个软件后点上方按钮。状态变绿即定位成功。")
        self._result.setWordWrap(True)
        self._result.setStyleSheet("padding:10px;border-radius:6px;background:#f0f5ff;color:#1e3a8a;")
        root.addWidget(self._result)

        root.addStretch(1)
        hint = QtWidgets.QLabel(
            "<span style='color:#888'>提示:可疑优先级——截图工具、输入法、翻译/词典、"
            "启动器(PowerToys Run/uTools)、录屏、云盘、安全软件。</span>"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        btn_close = QtWidgets.QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        root.addWidget(btn_close, alignment=QtCore.Qt.AlignRight)

    # ------------------------------------------------------------------
    def _do_check(self):
        r = quick_probe(self._combo.modifiers, self._combo.vk)
        fg, bg = status_color(r.status.value)
        self._status_lbl.setText(f"当前状态:{r.status.label}")
        self._status_lbl.setStyleSheet(
            f"font-size:15px;font-weight:600;color:{fg};background:{bg};"
            f"padding:8px;border-radius:6px;"
        )
        return r

    def _on_check(self) -> None:
        was_conflict = (
            self._last_status in (HotkeyStatus.OCCUPIED, HotkeyStatus.SYSTEM)
            if self._last_status is not None
            else True
        )
        r = self._do_check()
        self._last_status = r.status
        suspect = self._suspect.currentText()
        if was_conflict and r.status == HotkeyStatus.FREE:
            self._result.setText(
                f"✓ 状态已变为空闲!\n\n占用者很可能是「{suspect}」(或你刚关闭的软件)。"
            )
            self._result.setStyleSheet(
                "padding:10px;border-radius:6px;background:#e8f6ee;color:#166534;font-weight:600;"
            )
            QtWidgets.QApplication.beep()
        elif r.status.is_conflict:
            self._result.setText("仍未释放。继续关闭其他可疑软件后再点「重新检测」。")
            self._result.setStyleSheet(
                "padding:10px;border-radius:6px;background:#fde8e8;color:#991b1b;"
            )
        else:
            self._result.setText(f"当前状态:{r.status.label}")


__all__ = ["LocateSourceDialog"]
