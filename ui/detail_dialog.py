"""详情诊断对话框:双击表格行弹出,展示单个热键的完整诊断信息。

包括:状态、作用域、VK码、修饰键、来源证据链(✓/△/✗)、排障建议。
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from core import HotkeyResult, HotkeyStatus
from core.ai_analyze import AiError, analyze_combo, load_ai_config
from core.hotkeys import modifier_name, vk_name
from core.suspect import rank_suspects

from .ai_settings_dialog import AiSettingsDialog
from .locate_dialog import LocateSourceDialog
from .models import SCOPE_LABEL
from .style import (
    ADVICE_BG,
    ADVICE_BORDER,
    ADVICE_TEXT,
    BORDER,
    SYM_COLORS,
    SYM_WARN,
    TEXT_FAINT,
    TEXT_MUTED,
    status_color,
)
from .workers import FnWorker


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
                f"置信度:<b>{r.evidence.confidence}</b> <span style='color:{SYM_WARN}'>{star}</span>"
            ))
            evl.addWidget(self._hline())
            for desc, sym in r.evidence.checks:
                evl.addWidget(self._check_row(sym, desc))
            evl.addWidget(QtWidgets.QLabel(
                f"<span style='color:{TEXT_FAINT};font-size:11px'>"
                "注:Windows 不提供「哪个进程占用哪个热键」的 API,以上为基于已知热键库的推断。</span>"
            ))
        else:
            evl.addWidget(QtWidgets.QLabel(r.source or "—"))
        root.addWidget(ev_box)

        # 嫌疑度排序(占用时:本地启发式,多候选 + 无证据时的兜底)
        if r.status in (HotkeyStatus.OCCUPIED, HotkeyStatus.SYSTEM):
            root.addWidget(self._build_suspect_box())

        # 建议
        advice = self._advice()
        if advice:
            adv = QtWidgets.QLabel(advice)
            adv.setWordWrap(True)
            adv.setStyleSheet(
                f"background:{ADVICE_BG};border:1px solid {ADVICE_BORDER};border-radius:6px;"
                f"padding:10px;color:{ADVICE_TEXT};"
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
            btn_ai = QtWidgets.QPushButton("🤖 AI 分析来源")
            btn_ai.setObjectName("ai_analyze_btn")
            btn_ai.setToolTip("把热键 + 嫌疑排序 + 进程列表发给自配的 LLM,给出嫌疑度排序与排查建议")
            btn_ai.clicked.connect(self._ai_analyze)
            btns.addWidget(btn_ai)
            self._btn_ai = btn_ai
            btn_ai_cfg = QtWidgets.QPushButton("⚙ AI 设置")
            btn_ai_cfg.clicked.connect(self._ai_settings)
            btns.addWidget(btn_ai_cfg)
        btns.addStretch(1)
        self._btn_copy = QtWidgets.QPushButton("📋 复制诊断信息")
        self._btn_copy.clicked.connect(self._copy)
        btn_close = QtWidgets.QPushButton("关闭")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.accept)
        btns.addWidget(self._btn_copy)
        btns.addWidget(btn_close)
        root.addLayout(btns)

    # ------------------------------------------------------------------
    def _build_suspect_box(self) -> QtWidgets.QGroupBox:
        """嫌疑度排序区:本地启发式多候选打分(不依赖已知库精确命中)。"""
        self._suspects = rank_suspects(self._result.combo)
        box = QtWidgets.QGroupBox("嫌疑度排序(启发式推断)")
        v = QtWidgets.QVBoxLayout(box)
        v.setSpacing(4)
        if not self._suspects:
            v.addWidget(QtWidgets.QLabel("未发现正在运行的已知热键软件。可点「定位占用来源」二分排查,或用「AI 分析来源」。"))
            return box
        for s in self._suspects:
            v.addWidget(self._check_row(
                "△" if s.stars < 4 else "✓",
                f"<b>{s.star_str}</b> {s.app} <span style='color:{TEXT_FAINT};font-size:11px'>({s.matched})</span>"
                f"<br><span style='color:{TEXT_MUTED};font-size:11px'>{' ; '.join(s.reasons)}</span>",
            ))
        return box

    # ------------------------------------------------------------------
    def _ai_settings(self) -> None:
        AiSettingsDialog(self).exec()

    def _ai_analyze(self) -> None:
        """后台线程调用 LLM 分析,结果弹窗展示(不冻结 UI)。

        worker 生命周期由 FnWorker.spawn 管理:本对话框关闭后线程安全跑完,
        信号自动断开,结果被丢弃(见 ui/workers.py)。
        """
        if not load_ai_config().configured:
            QtWidgets.QMessageBox.information(
                self, "AI 分析",
                "尚未配置 AI 模型。请先在「AI 设置」里填写 Base URL / API Key / 模型名。")
            self._ai_settings()
            if not load_ai_config().configured:
                return
        combo = self._result.combo
        self._ai_btn_set_enabled(False)
        FnWorker.spawn(lambda: analyze_combo(combo), self._ai_done, self._ai_fail)

    def _ai_btn_set_enabled(self, enabled: bool) -> None:
        btn = getattr(self, "_btn_ai", None)
        if btn is not None:
            btn.setEnabled(enabled)
            btn.setText("🤖 AI 分析来源" if enabled else "🤖 AI 分析中…")

    def _ai_done(self, text: str) -> None:
        self._ai_btn_set_enabled(True)
        box = QtWidgets.QDialog(self)
        box.setWindowTitle(f"AI 来源分析 · {self._result.name}")
        box.setMinimumSize(520, 320)
        lay = QtWidgets.QVBoxLayout(box)
        view = QtWidgets.QTextEdit()
        view.setReadOnly(True)
        view.setMarkdown(text)
        lay.addWidget(view)
        btn_close = QtWidgets.QPushButton("关闭")
        btn_close.clicked.connect(box.accept)
        lay.addWidget(btn_close, alignment=QtCore.Qt.AlignRight)
        box.exec()

    def _ai_fail(self, msg: str) -> None:
        self._ai_btn_set_enabled(True)
        QtWidgets.QMessageBox.warning(self, "AI 分析失败", msg)

    # ------------------------------------------------------------------
    def _dim(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(f"color:{TEXT_MUTED};")
        return lbl

    def _hline(self) -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet(f"color:{BORDER};")
        return line

    def _check_row(self, sym: str, desc: str) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        color = SYM_COLORS.get(sym, SYM_COLORS["?"])
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
        # 反馈落在复制按钮自身(不能 findChild 找"第一个"——OCCUPIED 时第一个是「定位」按钮)
        self._btn_copy.setText("✓ 已复制")  # 简单反馈


__all__ = ["DetailDialog"]
