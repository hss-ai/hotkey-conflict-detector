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
    quick_probe,
    scan_running_hotkey_apps,
)
from core.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    format_combo,
    modifier_name,
    vk_name,
)
from core import snapshot as snap
from core.report import write_html

from .detail_dialog import DetailDialog
from .recommend_dialog import RecommendDialog
from .snapshot_dialog import SnapshotCompareDialog
from .models import COL_STATUS, SCOPE_LABEL, HotkeyFilterProxy, HotkeyTableModel
from .style import QSS, STATUS_COLORS, status_color

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


class HotkeyCaptureEdit(QtWidgets.QLineEdit):
    """聚焦后按下组合键自动捕获,显示并存储 (modifiers, vk)。

    用 QKeyEvent.nativeVirtualKey() 取原生 Win32 虚拟键码,避开 Qt::Key 与 VK 的差异。
    """

    combo_captured = QtCore.Signal(int, int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)  # 只捕获按键,不允许手输文字
        self.setPlaceholderText("点此聚焦,然后按下要检测的热键(如 Ctrl+Alt+J)…")
        self._mods = 0
        self._vk = 0

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (
            QtCore.Qt.Key_Control, QtCore.Qt.Key_Alt, QtCore.Qt.Key_Shift,
            QtCore.Qt.Key_Meta, QtCore.Qt.Key_AltGr,
        ):
            return  # 单独按修饰键不触发捕获
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
        self._mods, self._vk = mods, vk
        self.setText(format_combo(mods, vk))
        self.combo_captured.emit(mods, vk)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("全局热键冲突检测器")
        self.resize(1080, 720)
        self.setMinimumSize(820, 540)

        self._thread: Optional[ScanThread] = None
        self._pending: list[HotkeyResult] = []
        self._running_apps: list = []
        self._scanned_keys: set[tuple[int, int]] = set()  # 已扫过的 combo(续扫用)
        self._has_partial: bool = False                    # 上次扫描是否未完成

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
        root.addWidget(self._build_quick_bar())
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
        self._btn_snapshot_save = self._mkbtn("📁 存快照")
        self._btn_snapshot_diff = self._mkbtn("📊 对比快照")
        self._btn_export_html = self._mkbtn("📄 导出 HTML")
        self._btn_recommend = self._mkbtn("💡 推荐可用")
        self._btn_about = self._mkbtn("关于")

        for b in (
            self._btn_scan, self._btn_stop, self._btn_clear,
            self._btn_export, self._btn_copy,
            self._btn_snapshot_save, self._btn_snapshot_diff,
            self._btn_export_html, self._btn_recommend,
            self._btn_about,
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

    def _build_quick_bar(self) -> QtWidgets.QFrame:
        """单点检测条:按下热键自动探测这一个组合,无需全量扫描。"""
        frame = QtWidgets.QFrame()
        frame.setStyleSheet("QFrame{background:#ffffff;border:1px solid #e3e7ec;border-radius:8px;}")
        h = QtWidgets.QHBoxLayout(frame)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(8)
        h.addWidget(QtWidgets.QLabel("🔍 单点检测"))
        self._capture = HotkeyCaptureEdit()
        self._capture.setFixedHeight(30)
        self._capture.combo_captured.connect(self._quick_check)
        h.addWidget(self._capture, 1)
        self._btn_quick_detail = QtWidgets.QPushButton("查看详情")
        self._btn_quick_detail.setEnabled(False)
        self._btn_quick_detail.clicked.connect(self._show_quick_detail)
        h.addWidget(self._btn_quick_detail)
        self._quick_result = QtWidgets.QLabel("按下热键后自动检测…")
        self._quick_result.setMinimumWidth(220)
        self._quick_result.setWordWrap(True)
        self._quick_result.setStyleSheet("color:#6b7480;")
        h.addWidget(self._quick_result, 1)
        return frame

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
        self._cb_numpad = QtWidgets.QCheckBox("小键盘")
        self._cb_multimedia = QtWidgets.QCheckBox("媒体/浏览器键")
        for cb in (
            self._cb_win, self._cb_letters, self._cb_digits, self._cb_fkeys,
            self._cb_nav, self._cb_symbols, self._cb_space, self._cb_numpad,
            self._cb_multimedia,
        ):
            h.addWidget(cb)
        # 主流键默认勾选;扩展键(小键盘/多媒体)默认不勾,避免组合数过多
        for cb in (
            self._cb_win, self._cb_letters, self._cb_digits, self._cb_fkeys,
            self._cb_nav, self._cb_symbols, self._cb_space,
        ):
            cb.setChecked(True)

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
        # 固定列宽(Interactive)而非 ResizeToContents——后者在千行数据上每次窗口缩放
        # 都要重新测量全部单元格,是缩放卡顿的主因;最后一列 Stretch 自适应剩余空间。
        header = view.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)  # 组合
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)  # 修饰键
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)  # 按键
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)  # 状态
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Interactive)  # 作用域
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)      # 可能来源
        view.setColumnWidth(0, 150)  # 组合
        view.setColumnWidth(1, 140)  # 修饰键(容纳 Ctrl+Alt+Shift)
        view.setColumnWidth(2, 100)  # 按键(容纳 Backspace 等长键名)
        view.setColumnWidth(3, 100)  # 状态
        view.setColumnWidth(4, 100)  # 作用域
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
        self._btn_snapshot_save.clicked.connect(self.save_snapshot)
        self._btn_snapshot_diff.clicked.connect(self.show_snapshot_compare)
        self._btn_export_html.clicked.connect(self.export_html)
        self._btn_recommend.clicked.connect(self.show_recommend)
        self._btn_about.clicked.connect(self.about)
        self._table.doubleClicked.connect(self._show_detail)

        self._combo_status.currentIndexChanged.connect(self._apply_filters)
        self._cb_conflict_only.toggled.connect(self._apply_filters)
        self._search.textChanged.connect(self._apply_filters)

        # 扫描范围变化时刷新提示
        for cb in (
            self._cb_win, self._cb_letters, self._cb_digits, self._cb_fkeys,
            self._cb_nav, self._cb_symbols, self._cb_space, self._cb_numpad,
            self._cb_multimedia,
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
            numpad=self._cb_numpad.isChecked(),
            multimedia=self._cb_multimedia.isChecked(),
            min_modifiers=self._spin_min_mods.value(),
        )

    def start_scan(self) -> None:
        if self._thread is not None:
            return
        combos = self._build_combos()
        if not combos:
            QtWidgets.QMessageBox.information(self, "提示", "请至少选择一类按键。")
            return

        exclude: set[tuple[int, int]] = set()
        # 续扫:上次未扫完且有部分结果 → 询问继续扫描剩余 / 重新开始
        if self._has_partial and self._model.rowCount() > 0 and self._scanned_keys:
            remaining = sum(1 for c in combos if (c.modifiers, c.vk) not in self._scanned_keys)
            if remaining > 0:
                choice = QtWidgets.QMessageBox.question(
                    self, "继续扫描?",
                    f"上次扫描未完成(已扫 {len(self._scanned_keys)} 个,剩余约 {remaining} 个)。\n"
                    "「Yes」继续扫描剩余 ·「No」重新开始 ·「Cancel」取消。",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
                )
                if choice == QtWidgets.QMessageBox.Cancel:
                    return
                if choice == QtWidgets.QMessageBox.Yes:
                    exclude = set(self._scanned_keys)  # 续扫:跳过已扫,不清空已有结果
                else:  # No: 重新开始
                    self._scanned_keys.clear()
                    self.clear_results(silent=True)
            else:
                self._scanned_keys.clear()
                self.clear_results(silent=True)
        else:
            self._scanned_keys.clear()
            self.clear_results(silent=True)

        self._has_partial = False
        self._refresh_running_apps()

        self._thread = ScanThread(combos, exclude=exclude, parent=self)
        self._thread.result_ready.connect(self._on_result)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_scan.connect(self._on_finished)
        self._thread.finished.connect(self._on_thread_destroyed)

        self._set_scanning(True)
        self._flush_timer.start()
        self._thread.start()

        hint = "(续扫剩余)" if exclude else ""
        self._sb_status.setText(f"扫描中{hint}…(探测期间会短暂占用目标组合,请勿同时按下热键)")

    def stop_scan(self) -> None:
        if self._thread is not None:
            self._thread.request_stop()
            self._sb_status.setText("正在停止…")

    def _on_result(self, result: HotkeyResult) -> None:
        self._pending.append(result)
        self._scanned_keys.add((result.modifiers, result.vk))

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
        # 标记是否未完整扫完(中途停止),供下次 start_scan 判断是否提示续扫
        self._has_partial = not stats.get("completed", True)
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
            self._cb_nav, self._cb_symbols, self._cb_space, self._cb_numpad,
            self._cb_multimedia, self._spin_min_mods,
        ):
            w.setEnabled(not scanning)

    # ------------------------------------------------------------------
    # 结果管理
    # ------------------------------------------------------------------
    def clear_results(self, silent: bool = False) -> None:
        self._pending.clear()
        self._scanned_keys.clear()
        self._has_partial = False
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
    # 单点检测 / 详情面板
    # ------------------------------------------------------------------
    def _quick_check(self, modifiers: int, vk: int) -> None:
        """单点检测:探测一个组合并显示结果(捕获框按下热键后触发)。"""
        try:
            result = quick_probe(modifiers, vk)
        except Exception as e:  # noqa: BLE001
            self._quick_result.setText(f"<span style='color:#dc2626'>检测失败:{e}</span>")
            self._btn_quick_detail.setEnabled(False)
            return
        self._last_quick = result
        fg, _ = status_color(result.status.value)
        scope = SCOPE_LABEL.get(result.status, "")
        scope_txt = f"　·　{scope}" if scope else ""
        src = f"　·　{result.source}" if result.source else ""
        self._quick_result.setText(
            f"<span style='color:{fg};font-weight:600'>{result.status.label}</span>{scope_txt}{src}"
        )
        self._btn_quick_detail.setEnabled(True)

    def _show_quick_detail(self) -> None:
        r = getattr(self, "_last_quick", None)
        if r is not None:
            DetailDialog(r, self).exec()

    def _show_detail(self, proxy_index: QtCore.QModelIndex) -> None:
        """双击表格行 → 弹出详情诊断面板。"""
        source_index = self._proxy.mapToSource(proxy_index)
        if not source_index.isValid():
            return
        result = self._model.result_at(source_index.row())
        DetailDialog(result, self).exec()

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
    # 快照(基线对比)
    # ------------------------------------------------------------------
    def save_snapshot(self) -> None:
        results = self._model.all_results()
        if not results:
            QtWidgets.QMessageBox.information(self, "存快照", "当前没有扫描结果,请先扫描。")
            return
        label, ok = QtWidgets.QInputDialog.getText(
            self, "存快照", "为这份快照加个备注(可选,如「装软件前」):"
        )
        if not ok:
            return
        try:
            path = snap.save(results, meta={"label": label.strip()})
        except OSError as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "存快照失败", str(e))
            return
        conflict = sum(1 for r in results if r.status.is_conflict)
        QtWidgets.QMessageBox.information(
            self, "已保存快照",
            f"快照已保存:\n{path}\n\n共 {len(results)} 个组合,{conflict} 个冲突。\n"
            "之后可用「📊 对比快照」与历史快照对比。",
        )
        self._sb_status.setText(f"快照已保存:{path.name}")

    def show_snapshot_compare(self) -> None:
        SnapshotCompareDialog(self).exec()

    # ------------------------------------------------------------------
    # HTML 报告 / 空闲推荐
    # ------------------------------------------------------------------
    def export_html(self) -> None:
        results = self._model.all_results()
        if not results:
            QtWidgets.QMessageBox.information(self, "导出 HTML", "当前没有扫描结果,请先扫描。")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出为 HTML", "hotkey_report.html", "HTML 文件 (*.html)"
        )
        if not path:
            return
        try:
            write_html(path, results, meta={"label": "扫描报告"})
        except OSError as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "导出失败", str(e))
            return
        QtWidgets.QMessageBox.information(self, "导出成功", f"已导出 HTML 报告:\n{path}")
        self._sb_status.setText(f"HTML 报告已导出")

    def show_recommend(self) -> None:
        RecommendDialog(self._model.all_results(), self).exec()

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
            "<p><b>「作用域」列说明</b>:"
            "<br>• <b>系统级</b> = Windows 系统/Shell 保留(如 Win+D、Alt+Tab、Ctrl+Alt+Del),全局生效;"
            "<br>• <b>全局占用</b> = 被程序注册或全局键盘钩子占用,在<b>任何</b>应用按下都会触发"
            "——这才是会和其他快捷键冲突的来源。"
            "<br>应用内快捷键(如 Word 的 Ctrl+B)只在那个软件激活时生效,不占用全局槽位、不会冲突,"
            "因此不在检测范围。</p>"
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
