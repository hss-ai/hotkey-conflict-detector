"""快照对比对话框:选两份历史快照,展示「新增占用 / 已释放 / 状态变化」diff。

典型场景:装某软件前后各存一份快照,对比即知该软件抢占了哪些热键。
无历史快照(<2 份)时给出友好提示。颜色与主界面语义一致。
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from core import snapshot as snap

from .style import STATUS_FREE, TEXT_MUTED, status_color


class SnapshotCompareDialog(QtWidgets.QDialog):
    """两份快照 diff 展示。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("📊 快照对比")
        self.resize(620, 560)
        self._paths = snap.list_snapshots()
        self._build()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        intro = QtWidgets.QLabel(
            "选「旧 / 新」两份快照对比,定位「装了某软件后新增的占用」。\n"
            "🆕 新增占用 = 旧空闲/无、新被占;✅ 已释放 = 旧被占、新空闲。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{TEXT_MUTED};")
        root.addWidget(intro)

        if len(self._paths) < 2:
            tip = QtWidgets.QLabel(
                "ⓘ 至少需要 2 份历史快照才能对比。\n请先扫描并点「💾 存快照」。"
            )
            tip.setStyleSheet(f"padding:24px;color:{TEXT_MUTED};")
            tip.setAlignment(QtCore.Qt.AlignCenter)
            root.addWidget(tip, 1)
            btn = QtWidgets.QPushButton("关闭")
            btn.clicked.connect(self.accept)
            root.addWidget(btn, alignment=QtCore.Qt.AlignRight)
            return

        # 选择栏
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("旧快照:"))
        self._cb_old = QtWidgets.QComboBox()
        row.addWidget(self._cb_old, 1)
        row.addWidget(QtWidgets.QLabel("新快照:"))
        self._cb_new = QtWidgets.QComboBox()
        row.addWidget(self._cb_new, 1)
        for p in self._paths:
            d = snap.load(p)
            label = snap.snapshot_label(d) if d else p.name
            self._cb_old.addItem(label, str(p))
            self._cb_new.addItem(label, str(p))
        # 默认 old=倒数第二, new=最新
        self._cb_old.setCurrentIndex(len(self._paths) - 2)
        self._cb_new.setCurrentIndex(len(self._paths) - 1)
        self._cb_old.currentIndexChanged.connect(self._do_compare)
        self._cb_new.currentIndexChanged.connect(self._do_compare)
        root.addLayout(row)

        # 结果滚动区
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        self._result_layout = QtWidgets.QVBoxLayout(inner)
        self._result_layout.setContentsMargins(0, 0, 0, 0)
        self._result_layout.setSpacing(8)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self._do_compare()

    def _clear_results(self) -> None:
        while self._result_layout.count():
            item = self._result_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _do_compare(self) -> None:
        self._clear_results()
        old = snap.load(self._cb_old.currentData())
        new = snap.load(self._cb_new.currentData())
        if not old or not new:
            self._result_layout.addWidget(QtWidgets.QLabel("快照读取失败(可能已损坏)。"))
            return
        d = snap.diff(old, new)

        # 三个 section 的颜色沿用状态语义色:新增=占用红 / 已释放=空闲绿 / 变化=系统灰
        for title, entries, status_key in (
            ("🆕 新增占用", d["added"], "occupied"),
            ("✅ 已释放", d["removed"], "free"),
            ("🔄 状态变化", d["changed"], "system"),
        ):
            fg, bg = status_color(status_key)
            if status_key == "system":
                items = [
                    f"{oe.get('name', '?')} : {oe.get('status', '?')} → {ne.get('status', '?')}"
                    for oe, ne in entries
                ]
            else:
                items = [e.get("name", "?") for e in entries]
            self._add_section(title, len(entries), fg, bg, items)

        # 热键软件环境变化:与「新增占用」并排,辅助定位"装了/开了某软件导致的新占用"
        apps_added = d.get("apps_added") or []
        apps_removed = d.get("apps_removed") or []
        if apps_added or apps_removed:
            lines = []
            if apps_added:
                lines.append("✚ 新启动运行:" + "、".join(apps_added))
            if apps_removed:
                lines.append("➖ 已退出:" + "、".join(apps_removed))
            if apps_added and d["added"]:
                lines.append(f"⚠ 期间新增 {len(d['added'])} 个占用,优先排查上面新启动的软件")
            self._add_section("🖥 热键软件变化",
                              len(apps_added) + len(apps_removed),
                              STATUS_SYSTEM, status_color("system")[1], lines)

        if not (d["added"] or d["removed"] or d["changed"]):
            same = QtWidgets.QLabel("✓ 两份快照的冲突情况完全一致,无变化。")
            same.setStyleSheet(f"padding:16px;color:{STATUS_FREE};font-weight:600;")
            same.setAlignment(QtCore.Qt.AlignCenter)
            self._result_layout.addWidget(same)

    def _add_section(
        self, title: str, count: int, color: str, bg: str, items: list[str]
    ) -> None:
        box = QtWidgets.QGroupBox(f"{title} ({count})")
        box.setStyleSheet(f"QGroupBox{{color:{color};}}")
        v = QtWidgets.QVBoxLayout(box)
        v.setContentsMargins(12, 8, 12, 8)
        if not items:
            lbl = QtWidgets.QLabel("无")
            lbl.setStyleSheet(f"color:{TEXT_MUTED};")
            v.addWidget(lbl)
        else:
            for text in items:
                row = QtWidgets.QLabel(text)
                row.setStyleSheet(
                    f"background:{bg};color:{color};padding:4px 10px;border-radius:4px;"
                    f"font-family:Consolas,monospace;"
                )
                v.addWidget(row)
        self._result_layout.addWidget(box)


__all__ = ["SnapshotCompareDialog"]
