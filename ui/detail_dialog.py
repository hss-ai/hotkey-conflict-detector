"""详情诊断对话框:双击表格行弹出,展示单个热键的完整诊断信息。

包括:状态、作用域、VK码、修饰键、来源证据链(✓/△/✗)、排障建议。
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from core import HotkeyResult, HotkeyStatus
from core.hotkeys import modifier_name, vk_name

from .locate_dialog import LocateSourceDialog
from .models import SCOPE_LABEL
from .style import status_color


class DetailDialog(QtWidgets.QDialog):
    """单条热键结果的详情面板。"""

    def __init__(self, result: HotkeyResult, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._result = result
        self.setWindowTitle(f"热键详情 · {result.name}")
        self.setMinimumWidth(460)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        r = self._result
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # 标题 + 状态徽章
        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(r.name)
        title.setStyleSheet("font-size:24px;font-weight:700;")
        head.addWidget(title)
        head.addStretch(1)
        fg, bg = status_color(r.status.value)
        badge = QtWidgets.QLabel(f"  {r.status.label}  ")
        badge.setStyleSheet(
            f"background:{bg};color:{fg};font-weight:600;"
            f"padding:5px 14px;border-radius:5px;font-size:13px;"
        )
        head.addWidget(badge)
        root.addLayout(head)

        # 信息表
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        scope = SCOPE_LABEL.get(r.status, "—")
        form.addRow(self._dim("作用域"), QtWidgets.QLabel(scope))
        form.addRow(self._dim("虚拟键码"), QtWidgets.QLabel(f"0x{r.vk:02X}"))
        form.addRow(self._dim("按键名"), QtWidgets.QLabel(vk_name(r.vk)))
        form.addRow(self._dim("修饰键"), QtWidgets.QLabel(f"{modifier_name(r.modifiers)}  (0x{r.modifiers:X})"))
        root.addLayout(form)

        # 来源 + 证据链
        ev_box = QtWidgets.QGroupBox("来源诊断")
        evl = QtWidgets.QVBoxLayout(ev_box)
        evl.setSpacing(6)
        if r.evidence:
            star = "★" * r.evidence.stars + "☆" * (5 - r.evidence.stars)
            evl.addWidget(QtWidgets.QLabel(
                f"<b>{r.evidence.app}</b>{r.evidence.action}　"
                f"置信度:<b>{r.evidence.confidence}</b> <span style='color:#d97706'>{star}</span>"
            ))
            evl.addWidget(self._hline())
            for desc, sym in r.evidence.checks:
                evl.addWidget(self._check_row(sym, desc))
            evl.addWidget(QtWidgets.QLabel(
                "<span style='color:#888;font-size:11px'>"
                "注:Windows 不提供「哪个进程占用哪个热键」的 API,以上为基于已知热键库的推断。</span>"
            ))
        else:
            evl.addWidget(QtWidgets.QLabel(r.source or "—"))
        root.addWidget(ev_box)

        # 建议
        advice = self._advice()
        if advice:
            adv = QtWidgets.QLabel(advice)
            adv.setWordWrap(True)
            adv.setStyleSheet(
                "background:#f0f5ff;border:1px solid #c7d8ff;border-radius:6px;"
                "padding:10px;color:#1e3a8a;"
            )
            root.addWidget(adv)

        root.addStretch(1)

        # 按钮
        btns = QtWidgets.QHBoxLayout()
        if r.status == HotkeyStatus.OCCUPIED:
            btn_locate = QtWidgets.QPushButton("🔎 定位占用来源")
            btn_locate.setToolTip("Windows 不告知占用者,用二分定位法逐个排查")
            btn_locate.clicked.connect(self._locate)
            btns.addWidget(btn_locate)
        btns.addStretch(1)
        btn_copy = QtWidgets.QPushButton("📋 复制诊断信息")
        btn_copy.clicked.connect(self._copy)
        btn_close = QtWidgets.QPushButton("关闭")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_copy)
        btns.addWidget(btn_close)
        root.addLayout(btns)

    # ------------------------------------------------------------------
    def _dim(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet("color:#6b7480;")
        return lbl

    def _hline(self) -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color:#e3e7ec;")
        return line

    def _check_row(self, sym: str, desc: str) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        color = {"✓": "#16a34a", "△": "#d97706", "✗": "#dc2626", "?": "#64748b"}.get(sym, "#64748b")
        s = QtWidgets.QLabel(sym)
        s.setStyleSheet(f"color:{color};font-weight:700;font-size:15px;")
        s.setFixedWidth(20)
        s.setAlignment(QtCore.Qt.AlignCenter)
        d = QtWidgets.QLabel(desc)
        h.addWidget(s)
        h.addWidget(d, 1)
        return w

    # ------------------------------------------------------------------
    def _advice(self) -> str:
        r = self._result
        if r.status == HotkeyStatus.FREE:
            return "✓ 当前空闲,可放心使用该组合作为全局热键。"
        if r.status == HotkeyStatus.SYSTEM:
            return "🔒 Windows 系统保留,应用通常无法注册使用。"
        if r.status == HotkeyStatus.OCCUPIED:
            if r.evidence:
                return f"💡 若要释放此热键,可在「{r.evidence.app}」的设置里关闭或修改该快捷键,然后点工具栏「清空」重新扫描确认。"
            return "💡 已被占用。可逐个关闭后台软件后重新扫描,用「差异」定位到底是哪个程序占用。"
        if r.status == HotkeyStatus.ERROR:
            return "⚠ 探测异常,可能是无效组合或权限问题(尝试以管理员身份运行)。"
        return ""

    def _locate(self) -> None:
        """打开来源定位助手(二分定位:逐个关软件重测)。"""
        LocateSourceDialog(self._result.combo, self).exec()

    def _copy(self) -> None:
        r = self._result
        lines = [
            f"# 热键诊断 · {r.name}",
            f"状态: {r.status.label}",
            f"作用域: {SCOPE_LABEL.get(r.status, '—')}",
            f"虚拟键码: 0x{r.vk:02X}",
            f"修饰键: {modifier_name(r.modifiers)} (0x{r.modifiers:X})",
        ]
        if r.evidence:
            lines.append("")
            lines.append(f"来源: {r.evidence.app}{r.evidence.action} (置信度{r.evidence.confidence})")
            for desc, sym in r.evidence.checks:
                lines.append(f"  {sym} {desc}")
        elif r.source:
            lines.append(f"来源: {r.source}")
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))
        self.findChild(QtWidgets.QPushButton).setText("✓ 已复制")  # 简单反馈


__all__ = ["DetailDialog"]
