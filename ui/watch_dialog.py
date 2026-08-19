"""守望模式对话框:对一个热键组合后台定时探测,记录状态时间线与转变点。

解决「时好时坏」的间歇性占用——某软件周期性注册/注销热键,
单次扫描抓不到;守望持续探测,捕捉它从空闲变占用的瞬间及当时运行的软件。

组合捕获框内联于此(与 main_window.HotkeyCaptureEdit 同源),避免与主窗口循环导入。
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from core import HotkeyCombo, quick_probe, scan_running_hotkey_apps
from core.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, format_combo
from core.watch import WatchState

from .style import STATUS_OCCUPIED, TEXT_MUTED, status_color


_STATUS_LABEL = {
    "free": "空闲", "occupied": "已占用", "system": "系统保留",
    "error": "异常", "skipped": "已跳过",
}
_CONFLICT = {"occupied", "system"}


class _ComboCapture(QtWidgets.QLineEdit):
    """聚焦后按下组合键自动捕获(与 HotkeyCaptureEdit 同源,内联以避免循环导入)。"""

    captured = QtCore.Signal(int, int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点此聚焦,按下要守望的热键(如 Ctrl+Alt+J)…")

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (
            QtCore.Qt.Key_Control, QtCore.Qt.Key_Alt, QtCore.Qt.Key_Shift,
            QtCore.Qt.Key_Meta, QtCore.Qt.Key_AltGr,
        ):
            return
        vk = event.nativeVirtualKey()
        if not vk:
            return
        mods = 0
        m = event.modifiers()
        if m & QtCore.Qt.ControlModifier:
            mods |= MOD_CONTROL
        if m & QtCore.Qt.AltModifier:
            mods |= MOD_ALT
        if m & QtCore.Qt.ShiftModifier:
            mods |= MOD_SHIFT
        if m & QtCore.Qt.MetaModifier:
            mods |= MOD_WIN
        if mods == 0:
            return
        self.setText(format_combo(mods, vk))
        self.captured.emit(mods, vk)


class WatchDialog(QtWidgets.QDialog):
    """对一个组合定时守望,记录状态时间线。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("⏱ 守望模式")
        self.resize(680, 520)
        self._combo: HotkeyCombo | None = None
        self._state = WatchState()
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        intro = QtWidgets.QLabel(
            "守望一个热键组合:后台定时探测,记录状态时间线。\n"
            "解决「时好时坏」——捕捉它从空闲变占用的瞬间及当时运行的软件。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{TEXT_MUTED};")
        root.addWidget(intro)

        # 控制栏
        ctrl = QtWidgets.QHBoxLayout()
        ctrl.addWidget(QtWidgets.QLabel("守望组合:"))
        self._capture = _ComboCapture()
        self._capture.setFixedHeight(30)
        self._capture.captured.connect(self._on_captured)
        ctrl.addWidget(self._capture, 1)
        ctrl.addWidget(QtWidgets.QLabel("间隔(秒):"))
        self._spin_interval = QtWidgets.QSpinBox()
        self._spin_interval.setRange(1, 30)
        self._spin_interval.setValue(2)
        self._spin_interval.setFixedWidth(64)
        ctrl.addWidget(self._spin_interval)
        self._btn_toggle = QtWidgets.QPushButton("▶ 开始守望")
        self._btn_toggle.setObjectName("primary")
        self._btn_toggle.setEnabled(False)
        self._btn_toggle.clicked.connect(self._toggle)
        ctrl.addWidget(self._btn_toggle)
        root.addLayout(ctrl)

        # 当前状态徽章(初始未开始,用 system 灰)
        fg0, bg0 = status_color("system")
        self._badge = QtWidgets.QLabel("未开始")
        self._badge.setAlignment(QtCore.Qt.AlignCenter)
        self._badge.setStyleSheet(
            f"background:{bg0};color:{fg0};font-weight:600;"
            f"padding:8px;border-radius:6px;"
        )
        root.addWidget(self._badge)

        # 时间线表
        self._table = QtWidgets.QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["时刻", "状态", "运行软件"])
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        root.addWidget(self._table, 1)

        # 摘要
        self._summary = QtWidgets.QLabel("尚未开始。")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f"color:{TEXT_MUTED};")
        root.addWidget(self._summary)

        btns = QtWidgets.QHBoxLayout()
        btn_copy = QtWidgets.QPushButton("📋 复制时间线")
        btn_copy.clicked.connect(self._copy)
        btns.addWidget(btn_copy)
        btns.addStretch(1)
        btn_clear = QtWidgets.QPushButton("清空")
        btn_clear.clicked.connect(self._clear)
        btns.addWidget(btn_clear)
        btn_close = QtWidgets.QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        btns.addWidget(btn_close)
        root.addLayout(btns)

    # ------------------------------------------------------------------
    def _on_captured(self, mods: int, vk: int) -> None:
        self._combo = HotkeyCombo(mods, vk)
        self._btn_toggle.setEnabled(True)

    def _toggle(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._btn_toggle.setText("▶ 开始守望")
            self._capture.setEnabled(True)
            self._spin_interval.setEnabled(True)
        else:
            if self._combo is None:
                return
            self._timer.setInterval(self._spin_interval.value() * 1000)
            self._timer.start()
            self._btn_toggle.setText("■ 停止守望")
            self._capture.setEnabled(False)
            self._spin_interval.setEnabled(False)
            self._tick()  # 立即探一次

    def _tick(self) -> None:
        if self._combo is None:
            return
        try:
            r = quick_probe(self._combo.modifiers, self._combo.vk)
        except Exception:  # noqa: BLE001
            return
        apps = [a.name for a in scan_running_hotkey_apps()]
        prev_status = self._state.current_status
        self._state.record(r.status.value, apps)
        self._add_row(r.status.value, apps)
        self._update_badge(r.status.value)
        # 状态转变:冲突↔非冲突 才提示音+高亮
        if prev_status and prev_status != r.status.value:
            if (prev_status in _CONFLICT) != (r.status.value in _CONFLICT):
                QtWidgets.QApplication.beep()
                self._summary.setText(
                    f"⚡ 状态转变!{_STATUS_LABEL.get(prev_status, prev_status)} → "
                    f"{_STATUS_LABEL.get(r.status.value, r.status.value)}"
                )
                self._summary.setStyleSheet(f"color:{STATUS_OCCUPIED};font-weight:600;")
                return
        self._refresh_summary()

    def _add_row(self, status: str, apps: list[str]) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        ts = self._state.events[-1].timestamp
        self._table.setItem(row, 0, QtWidgets.QTableWidgetItem(ts))
        fg, _ = status_color(status)
        cell_status = QtWidgets.QTableWidgetItem(_STATUS_LABEL.get(status, status))
        cell_status.setForeground(QtGui.QColor(fg))
        self._table.setItem(row, 1, cell_status)
        self._table.setItem(row, 2, QtWidgets.QTableWidgetItem("、".join(apps) or "—"))
        self._table.scrollToBottom()

    def _update_badge(self, status: str) -> None:
        fg, bg = status_color(status)
        self._badge.setText(f"当前:{_STATUS_LABEL.get(status, status)}")
        self._badge.setStyleSheet(
            f"background:{bg};color:{fg};font-weight:600;padding:8px;border-radius:6px;"
        )

    def _refresh_summary(self) -> None:
        self._summary.setText(self._state.summary)
        self._summary.setStyleSheet(f"color:{TEXT_MUTED};")

    def _copy(self) -> None:
        if not self._state.events:
            return
        name = self._combo.name if self._combo else "?"
        text = f"# 守望时间线 · {name}\n\n" + self._state.summary
        QtWidgets.QApplication.clipboard().setText(text)

    def _clear(self) -> None:
        self._state.clear()
        self._table.setRowCount(0)
        self._summary.setText("已清空。")
        self._summary.setStyleSheet(f"color:{TEXT_MUTED};")

    def reject(self) -> None:  # noqa: D401
        self._timer.stop()
        super().reject()


__all__ = ["WatchDialog"]
