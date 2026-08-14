"""全局样式表与配色常量(浅色现代风)。

桌面 QSS 直接用色值是常规做法(无 web 的 token 系统),
但全站统一从本文件取色,避免散落硬编码。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 配色板
# ---------------------------------------------------------------------------
BG_APP = "#f4f5f8"        # 应用背景
BG_PANEL = "#ffffff"      # 面板/卡片
BG_ALT = "#fafbfc"        # 表格交替行
BORDER = "#e3e7ec"        # 边框
BORDER_FOCUS = "#2563eb"  # 聚焦边框

TEXT_PRIMARY = "#1f2933"
TEXT_MUTED = "#6b7480"
TEXT_INVERT = "#ffffff"

ACCENT = "#2563eb"        # 主强调(蓝)
ACCENT_HOVER = "#1d4ed8"
ACCENT_PRESSED = "#1e40af"

STATUS_FREE = "#16a34a"     # 空闲-绿
STATUS_OCCUPIED = "#dc2626"  # 已占用-红(冲突)
STATUS_SYSTEM = "#64748b"    # 系统保留-灰
STATUS_ERROR = "#d97706"     # 异常-橙

# 状态 → (前景色, 浅背景色) 用于表格单元格
STATUS_COLORS = {
    "free": (STATUS_FREE, "#e8f6ee"),
    "occupied": (STATUS_OCCUPIED, "#fde8e8"),
    "system": (STATUS_SYSTEM, "#eef1f4"),
    "error": (STATUS_ERROR, "#fdf2e3"),
    "skipped": (TEXT_MUTED, "#f0f1f3"),
}


QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}

QMainWindow, QWidget#central {{
    background-color: {BG_APP};
}}

/* ---------- 工具栏 ---------- */
QToolBar {{
    background-color: {BG_PANEL};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 10px;
    spacing: 6px;
}}
QToolBar QToolButton {{
    padding: 6px 12px;
    border-radius: 6px;
    background: transparent;
}}
QToolBar QToolButton:hover {{ background-color: {BG_ALT}; }}

/* ---------- 按钮 ---------- */
QPushButton {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 16px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background-color: {BG_ALT}; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; border-color: {BORDER}; }}

QPushButton#primary {{
    background-color: {ACCENT};
    color: {TEXT_INVERT};
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#primary:hover {{ background-color: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; color: {TEXT_INVERT}; }}
QPushButton#primary:pressed {{ background-color: {ACCENT_PRESSED}; }}
QPushButton#primary:disabled {{ background-color: #9db8ef; border-color: #9db8ef; color: {TEXT_INVERT}; }}

QPushButton#danger {{
    background-color: {STATUS_OCCUPIED};
    color: {TEXT_INVERT};
    border: 1px solid {STATUS_OCCUPIED};
    font-weight: 600;
}}
QPushButton#danger:hover {{ background-color: #b91c1c; border-color: #b91c1c; }}
QPushButton#danger:disabled {{ background-color: #f0a3a3; border-color: #f0a3a3; }}

/* ---------- 输入控件 ---------- */
QLineEdit, QComboBox, QSpinBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {ACCENT};
    selection-color: {TEXT_INVERT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {BORDER_FOCUS};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: {TEXT_INVERT};
    outline: none;
}}

QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {BG_PANEL};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}

/* ---------- 表格 ---------- */
QTableView {{
    background-color: {BG_PANEL};
    alternate-background-color: {BG_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    selection-background-color: #dbe7ff;
    selection-color: {TEXT_PRIMARY};
}}
QTableView::item {{ padding: 5px 8px; border: none; }}
QTableView::item:focus {{ outline: none; }}
QHeaderView::section {{
    background-color: #f7f8fa;
    color: {TEXT_MUTED};
    padding: 8px 10px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}
QHeaderView::section:hover {{ background-color: {BG_ALT}; }}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background-color: {BG_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    color: {TEXT_INVERT};
    height: 16px;
    font-weight: 600;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 5px;
}}

/* ---------- 状态栏 ---------- */
QStatusBar {{
    background-color: {BG_PANEL};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}
QStatusBar::item {{ border: none; }}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #c8ced6;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #aeb6c0; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #c8ced6;
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: #aeb6c0; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---------- 分组框 ---------- */
QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_MUTED};
}}

/* ---------- 提示 ---------- */
QToolTip {{
    background-color: #1f2933;
    color: {TEXT_INVERT};
    border: none;
    padding: 6px 10px;
    border-radius: 4px;
}}
"""


def status_color(status_value: str) -> tuple[str, str]:
    """返回状态对应的(前景色, 背景色)。"""
    return STATUS_COLORS.get(status_value, (TEXT_MUTED, BG_ALT))


__all__ = ["QSS", "status_color", "STATUS_COLORS"]
