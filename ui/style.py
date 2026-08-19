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
ACCENT_DISABLED = "#9db8ef"   # primary 按钮禁用态

DANGER_HOVER = "#b91c1c"      # danger 按钮悬停
DANGER_DISABLED = "#f0a3a3"   # danger 按钮禁用态

# 选中/表头/滚动条
SELECT_BG = "#dbe7ff"         # 表格/列表选中背景
HEADER_BG = "#f7f8fa"         # 表头背景
SCROLL_HANDLE = "#c8ced6"
SCROLL_HANDLE_HOVER = "#aeb6c0"

# 信息/建议框(浅蓝底)
ADVICE_BG = "#f0f5ff"
ADVICE_BORDER = "#c7d8ff"
ADVICE_TEXT = "#1e3a8a"

STATUS_FREE = "#16a34a"     # 空闲-绿
STATUS_OCCUPIED = "#dc2626"  # 已占用-红(冲突)
STATUS_SYSTEM = "#64748b"    # 系统保留-灰
STATUS_ERROR = "#d97706"     # 异常-橙

# 证据/检查行符号色(✓ 确认 / △ 部分 / ✗ 不支持 / ? 未知)
SYM_OK = STATUS_FREE
SYM_WARN = STATUS_ERROR
SYM_ERR = STATUS_OCCUPIED
SYM_NEUTRAL = STATUS_SYSTEM
SYM_COLORS = {"✓": SYM_OK, "△": SYM_WARN, "✗": SYM_ERR, "?": SYM_NEUTRAL}

TEXT_FAINT = "#888888"      # 注脚/次要说明(比 TEXT_MUTED 更弱)

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
QPushButton#primary:disabled {{ background-color: {ACCENT_DISABLED}; border-color: {ACCENT_DISABLED}; color: {TEXT_INVERT}; }}

QPushButton#danger {{
    background-color: {STATUS_OCCUPIED};
    color: {TEXT_INVERT};
    border: 1px solid {STATUS_OCCUPIED};
    font-weight: 600;
}}
QPushButton#danger:hover {{ background-color: {DANGER_HOVER}; border-color: {DANGER_HOVER}; }}
QPushButton#danger:disabled {{ background-color: {DANGER_DISABLED}; border-color: {DANGER_DISABLED}; }}

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
    selection-background-color: {SELECT_BG};
    selection-color: {TEXT_PRIMARY};
}}
QTableView::item {{ padding: 5px 8px; border: none; }}
QTableView::item:focus {{ outline: none; }}
QHeaderView::section {{
    background-color: {HEADER_BG};
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
    background: {SCROLL_HANDLE};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {SCROLL_HANDLE_HOVER}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {SCROLL_HANDLE};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {SCROLL_HANDLE_HOVER}; }}
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
    background-color: {TEXT_PRIMARY};
    color: {TEXT_INVERT};
    border: none;
    padding: 6px 10px;
    border-radius: 4px;
}}
"""


def status_color(status_value: str) -> tuple[str, str]:
    """返回状态对应的(前景色, 背景色)。"""
    return STATUS_COLORS.get(status_value, (TEXT_MUTED, BG_ALT))


__all__ = [
    "QSS",
    "status_color",
    "STATUS_COLORS",
    "ACCENT_DISABLED",
    "DANGER_HOVER",
    "DANGER_DISABLED",
    "SELECT_BG",
    "HEADER_BG",
    "SCROLL_HANDLE",
    "SCROLL_HANDLE_HOVER",
    "ADVICE_BG",
    "ADVICE_BORDER",
    "ADVICE_TEXT",
    "STATUS_FREE",
    "STATUS_OCCUPIED",
    "STATUS_SYSTEM",
    "STATUS_ERROR",
    "SYM_OK",
    "SYM_WARN",
    "SYM_ERR",
    "SYM_NEUTRAL",
    "SYM_COLORS",
    "TEXT_FAINT",
]
