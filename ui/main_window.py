"""主窗口:工具栏 / 扫描范围设置 / 统计 / 进度 / 筛选 / 表格 / 状态栏。

扫描在后台 QThread 进行,结果通过信号攒入 buffer,由 50ms 定时器批量刷入表格,
避免逐行重绘造成卡顿。
"""
from __future__ import annotations

import csv
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core import (
    HotkeyResult,
    HotkeyStatus,
    ScanThread,
    generate_combos,
    scan_running_hotkey_apps,
)
from core.hotkeys import modifier_name, vk_name

from .models import COL_STATUS, HotkeyFilterProxy, HotkeyTableModel
from .style import QSS, STATUS_COLORS

# 统计项定义:(key, 标题, 颜色)
_STAT_ITEMS = (
    ("total", "组合总数", "#2563eb"),
    ("conflict", "冲突", "#dc2626"),
    ("occupied", "已占用", "#dc2626"),
    ("system", "系统保留", "#64748b"),
    ("free", "空闲", "#16a34a"),
    ("error", "异常", "#d97706"),
)

_STATUS_LABELS = (
    ("(全部)", None),
    ("空闲", HotkeyStatus.FREE),
    ("已占用", HotkeyStatus.OCCUPIED),
    ("系统保留", HotkeyStatus.SYSTEM),
    ("异常", HotkeyStatus.ERROR),
)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("全局热键冲突检测器")
        self.resize(1080, 720)
        self.setMinimumSize(820, 540)

        self._thread: Optional[ScanThread] = None
        self._pending: list[HotkeyResult] = []
        self._running_apps: list = []

        # 刷新节流定时器
        self._flush_timer = QtCore.QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush_results)

        self._model = HotkeyTableModel(self)
        self._proxy = HotkeyFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._build_ui()
        self._connect_signals()
        self._update_stats()
        self._refresh_running_apps()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        root.addLayout(self._build_toolbar())
        root.addWidget(self._build_settings_panel())
        root.addWidget(self._build_stats_bar())
        root.addWidget(self._build_progress())
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_table(), 1)

        self._build_statusbar()

    def _build_toolbar(self) -> QtWidgets.QHBoxLayout:
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(8)

        title = QtWidgets.QLabel("🔧 全局热键冲突检测器")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        bar.addWidget(title)
        bar.addStretch(1)

        self._btn_scan = self._mkbtn("▶  开始扫描", primary=True)
        self._btn_stop = self._mkbtn("■  停止", danger=True)
        self._btn_stop.setEnabled(False)
        self._btn_clear = self._mkbtn("清空")
        self._btn_export = self._mkbtn("💾 导出 CSV")
        self._btn_copy = self._mkbtn("📋 复制冲突")
        self._btn_about = self._mkbtn("关于")

        for b in (
            self._btn_scan, self._btn_stop, self._btn_clear,
            self._btn_export, self._btn_copy, self._btn_about,
        ):
            bar.addWidget(b)
        return bar

    def _mkbtn(self, text: str, primary: bool = False, danger: bool = False) -> QtWidgets.QPushButton:
        b = QtWidgets.QPushButton(text)
        if primary:
            b.setObjectName("primary")
        elif danger:
            b.setObjectName("danger")
        return b

    def _build_settings_panel(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("扫描范围")
        h = QtWidgets.QHBoxLayout(box)
        h.setSpacing(14)

        self._cb_win = QtWidgets.QCheckBox("含 Win 组合")
        self._cb_letters = QtWidgets.QCheckBox("字母 A-Z")
        self._cb_digits = QtWidgets.QCheckBox("数字 0-9")
        self._cb_fkeys = QtWidgets.QCheckBox("功能键 F1-F24")
        self._cb_nav = QtWidgets.QCheckBox("导航/编辑键")
        self._cb_symbols = QtWidgets.QCheckBox("符号键")
        self._cb_space = QtWidgets.QCheckBox("Space")
        for cb in (
            self._cb_win, self._cb_letters, self._cb_digits, self._cb_fkeys,
            self._cb_nav, self._cb_symbols, self._cb_space,
        ):
            cb.setChecked(True)
            h.addWidget(cb)

        h.addSpacing(12)
        h.addWidget(QtWidgets.QLabel("最少修饰键:"))
        self._spin_min_mods = QtWidgets.QSpinBox()
        self._spin_min_mods.setRange(1, 4)
        self._spin_min_mods.setValue(1)
        self._spin_min_mods.setFixedWidth(56)
        h.addWidget(self._spin_min_mods)

        h.addStretch(1)
        self._lbl_scope_hint = QtWidgets.QLabel()
        self._lbl_scope_hint.setStyleSheet("color:#6b7480;")
        h.addWidget(self._lbl_scope_hint)
        return box

    def _build_stats_bar(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setStyleSheet(
            f"QFrame{{background:{QtWidgets.QWidget().palette().color(QtGui.QPalette.Window).name()};}}"
        )
        h = QtWidgets.QHBoxLayout(frame)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        self._stat_labels: dict[str, QtWidgets.QLabel] = {}
        for key, title, color in _STAT_ITEMS:
            card = self._make_stat_card(title, color)
            self._stat_labels[key] = card
            h.addWidget(card)
        h.addStretch(1)
        return frame

    def _make_stat_card(self, title: str, color: str) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setStyleSheet(
            f"QFrame{{background:#ffffff;border:1px solid #e3e7ec;border-radius:10px;}}"
        )
        card.setFixedHeight(64)
        card.setMinimumWidth(96)
        v = QtWidgets.QVBoxLayout(card)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(2)
        val = QtWidgets.QLabel("0")
        val.setObjectName("value")
        val.setStyleSheet(f"font-size:22px;font-weight:700;color:{color};")
        val.setAlignment(QtCore.Qt.AlignCenter)
        lab = QtWidgets.QLabel(title)
        lab.setStyleSheet("font-size:11px;color:#6b7480;")
        lab.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(val)
        v.addWidget(lab)
        # 把 value label 挂到 frame 上便于外部更新
        setattr(card, "value_label", val)
        return card

    def _build_progress(self) -> QtWidgets.QProgressBar:
        self._progress = QtWidgets.QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFormat("就绪")
        self._progress.setFixedHeight(18)
        return self._progress

    def _build_filter_bar(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        h = QtWidgets.QHBoxLayout(frame)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        h.addWidget(QtWidgets.QLabel("状态:"))
        self._combo_status = QtWidgets.QComboBox()
        for label, _ in _STATUS_LABELS:
            self._combo_status.addItem(label)
        self._combo_status.setFixedHeight(30)
        h.addWidget(self._combo_status)

        self._cb_conflict_only = QtWidgets.QCheckBox("仅看冲突")
        h.addWidget(self._cb_conflict_only)

        h.addSpacing(12)
        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText("搜索组合(如 Ctrl+A)或来源…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(30)
        h.addWidget(self._search, 1)

        self._lbl_filter_info = QtWidgets.QLabel()
        self._lbl_filter_info.setStyleSheet("color:#6b7480;")
        h.addWidget(self._lbl_filter_info)
        return frame

    def _build_table(self) -> QtWidgets.QTableView:
        view = QtWidgets.QTableView()
        view.setModel(self._proxy)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        view.verticalHeader().setVisible(False)
        view.verticalHeader().setDefaultSectionSize(30)
        view.horizontalHeader().setStretchLastSection(True)
        view.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        view.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        view.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        view.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        view.setSortingEnabled(True)
        view.sortByColumn(COL_STATUS, QtCore.Qt.AscendingOrder)
        self._table = view
        return view

    def _build_statusbar(self) -> None:
        sb = QtWidgets.QStatusBar()
        self.setStatusBar(sb)
        self._sb_status = QtWidgets.QLabel("就绪")
        self._sb_apps = QtWidgets.QLabel()
        sb.addWidget(self._sb_status, 2)
        sb.addPermanentWidget(self._sb_apps)

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self._btn_scan.clicked.connect(self.start_scan)
        self._btn_stop.clicked.connect(self.stop_scan)
        self._btn_clear.clicked.connect(self.clear_results)
        self._btn_export.clicked.connect(self.export_csv)
        self._btn_copy.clicked.connect(self.copy_conflicts)
        self._btn_about.clicked.connect(self.about)

        self._combo_status.currentIndexChanged.connect(self._apply_filters)
        self._cb_conflict_only.toggled.connect(self._apply_filters)
        self._search.textChanged.connect(self._apply_filters)

        # 扫描范围变化时刷新提示
        for cb in (
            self._cb_win, self._cb_letters, self._cb_digits, self._cb_fkeys,
            self._cb_nav, self._cb_symbols, self._cb_space,
        ):
            cb.toggled.connect(self._update_scope_hint)
        self._spin_min_mods.valueChanged.connect(self._update_scope_hint)
        self._update_scope_hint()

    # ------------------------------------------------------------------
    # 扫描流程
    # ------------------------------------------------------------------
    def _update_scope_hint(self) -> None:
        try:
            combos = self._build_combos()
        except Exception:
            combos = []
        self._lbl_scope_hint.setText(f"将扫描约 {len(combos)} 个组合")

    def _build_combos(self):
        return generate_combos(
            include_win=self._cb_win.isChecked(),
            letters=self._cb_letters.isChecked(),
            digits=self._cb_digits.isChecked(),
            function_keys=self._cb_fkeys.isChecked(),
            navigation=self._cb_nav.isChecked(),
            symbols=self._cb_symbols.isChecked(),
            space=self._cb_space.isChecked(),
            min_modifiers=self._spin_min_mods.value(),
        )

    def start_scan(self) -> None:
        if self._thread is not None:
            return
        combos = self._build_combos()
        if not combos:
            QtWidgets.QMessageBox.information(self, "提示", "请至少选择一类按键。")
            return

        self.clear_results(silent=True)
        self._refresh_running_apps()

        self._thread = ScanThread(combos, self)
        self._thread.result_ready.connect(self._on_result)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_scan.connect(self._on_finished)
        self._thread.finished.connect(self._on_thread_destroyed)

        self._set_scanning(True)
        self._flush_timer.start()
        self._thread.start()

        self._sb_status.setText("扫描中…(探测期间会短暂占用目标组合,请勿同时按下热键)")

    def stop_scan(self) -> None:
        if self._thread is not None:
            self._thread.request_stop()
            self._sb_status.setText("正在停止…")

    def _on_result(self, result: HotkeyResult) -> None:
        self._pending.append(result)

    def _flush_results(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        self._model.flush_results(batch)
        self._update_stats()

    def _on_progress(self, done: int, total: int) -> None:
        pct = int(done * 100 / total) if total else 0
        self._progress.setValue(pct)
        self._progress.setFormat(f"扫描中 {done}/{total}  ({pct}%)")

    def _on_finished(self, stats: dict) -> None:
        self._flush_results()
        self._flush_timer.stop()
        self._progress.setValue(100)
        scanned = stats.get("scanned", 0)
        total = stats.get("total", 0)
        occupied = stats.get("occupied", 0)
        system = stats.get("system", 0)
        conflict = occupied + system
        self._progress.setFormat(f"完成 · 已扫描 {scanned}/{total}")
        self._update_stats()
        self._set_scanning(False)
        msg = f"扫描完成:{scanned}/{total} 个组合。"
        if conflict:
            msg += f"\n发现 {conflict} 个冲突(占用 {occupied} + 系统 {system})。"
        else:
            msg += "\n未发现冲突。"
        self._sb_status.setText(msg)

    def _on_thread_destroyed(self) -> None:
        self._thread = None

    def _set_scanning(self, scanning: bool) -> None:
        self._btn_scan.setEnabled(not scanning)
        self._btn_stop.setEnabled(scanning)
        for w in (
            self._cb_win, self._cb_letters, self._cb_digits, self._cb_fkeys,
            self._cb_nav, self._cb_symbols, self._cb_space, self._spin_min_mods,
        ):
            w.setEnabled(not scanning)

    # ------------------------------------------------------------------
    # 结果管理
    # ------------------------------------------------------------------
    def clear_results(self, silent: bool = False) -> None:
        self._pending.clear()
        self._model.clear()
        self._progress.setValue(0)
        self._progress.setFormat("就绪")
        self._update_stats()
        if not silent:
            self._sb_status.setText("已清空结果。")

    def _update_stats(self) -> None:
        counts = self._model.count_by_status()
        total = sum(counts.values())
        occupied = counts.get(HotkeyStatus.OCCUPIED, 0)
        system = counts.get(HotkeyStatus.SYSTEM, 0)
        free = counts.get(HotkeyStatus.FREE, 0)
        error = counts.get(HotkeyStatus.ERROR, 0)
        conflict = occupied + system
        values = {
            "total": total, "conflict": conflict, "occupied": occupied,
            "system": system, "free": free, "error": error,
        }
        for key, val in values.items():
            card = self._stat_labels.get(key)
            if card is not None:
                card.value_label.setText(str(val))

        # 筛选后行数提示
        shown = self._proxy.rowCount()
        if total and shown != total:
            self._lbl_filter_info.setText(f"显示 {shown}/{total}")
        else:
            self._lbl_filter_info.setText("")

    def _apply_filters(self) -> None:
        idx = self._combo_status.currentIndex()
        status = _STATUS_LABELS[idx][1]
        self._proxy.set_status_filter(status)
        self._proxy.set_conflict_only(self._cb_conflict_only.isChecked())
        self._proxy.set_search(self._search.text())
        self._update_stats()

    def _refresh_running_apps(self) -> None:
        try:
            self._running_apps = scan_running_hotkey_apps()
        except Exception as e:  # noqa: BLE001
            self._running_apps = []
            self._sb_apps.setText(f"(进程扫描失败:{e})")
            return
        if self._running_apps:
            names = "、".join(a.name for a in self._running_apps)
            self._sb_apps.setText(f"🖥 运行中的热键软件:{names}")
            detail = "\n".join(f"{a.name}  ({a.matched})" for a in self._running_apps)
            self._sb_apps.setToolTip(
                "检测到以下可能注册全局热键的软件(悬停查看进程名):\n" + detail
            )
        else:
            self._sb_apps.setText("🖥 未检测到已知热键软件")
            self._sb_apps.setToolTip("")

    # ------------------------------------------------------------------
    # 导出 / 复制
    # ------------------------------------------------------------------
    def export_csv(self) -> None:
        results = self._model.all_results()
        if not results:
            QtWidgets.QMessageBox.information(self, "导出", "当前没有可导出的结果,请先扫描。")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出为 CSV", "hotkey_scan.csv", "CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["组合", "修饰键", "按键", "状态", "可能来源"])
                for r in results:
                    w.writerow([
                        r.name, modifier_name(r.modifiers), vk_name(r.vk),
                        r.status.label, r.source,
                    ])
            QtWidgets.QMessageBox.information(self, "导出成功", f"已导出 {len(results)} 行到:\n{path}")
        except OSError as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "导出失败", str(e))

    def copy_conflicts(self) -> None:
        conflicts = [
            r for r in self._model.all_results() if r.status.is_conflict
        ]
        if not conflicts:
            QtWidgets.QMessageBox.information(self, "复制", "当前没有冲突组合可复制。")
            return
        lines = ["# 热键冲突列表(全局热键冲突检测器导出)", ""]
        for r in conflicts:
            lines.append(f"{r.name}\t{r.status.label}\t{r.source}".rstrip())
        text = "\n".join(lines)
        QtWidgets.QApplication.clipboard().setText(text)
        self._sb_status.setText(f"已复制 {len(conflicts)} 个冲突组合到剪贴板。")

    # ------------------------------------------------------------------
    # 其他
    # ------------------------------------------------------------------
    def about(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "关于",
            "<h3>全局热键冲突检测器</h3>"
            "<p>检测 Windows 上已被占用的全局热键组合,帮助排查快捷键冲突。</p>"
            "<p><b>原理</b>:逐个尝试注册候选热键组合,若失败说明已被占用"
            "(RegisterHotKey 探测法)。Windows 不提供「哪个进程占用哪个热键」的接口,"
            "来源识别为尽力推断。</p>"
            "<p><b>提示</b>:探测时会短暂占用目标组合(毫秒级),扫描很快,影响极小。</p>"
            "<p style='color:#888'>基于 Python + PySide6 · MIT License</p>",
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._thread is not None:
            self._thread.request_stop()
            self._thread.wait(3000)
        self._flush_timer.stop()
        super().closeEvent(event)


__all__ = ["MainWindow"]
