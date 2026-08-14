"""表格数据模型与筛选代理。

HotkeyTableModel 持有 HotkeyResult 列表,支持扫描时高效追加(单条/批量);
HotkeyFilterProxy 提供状态筛选、搜索、仅冲突、排序功能。
"""
from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui

from core import HotkeyResult, HotkeyStatus
from core.hotkeys import modifier_name, vk_name

from .style import status_color


# 列定义
COLUMNS = ("组合", "修饰键", "按键", "状态", "可能来源")
COL_COMBO, COL_MOD, COL_VK, COL_STATUS, COL_SOURCE = range(len(COLUMNS))

# 自定义角色:用于状态列按"冲突优先级"排序而非文字
ROLE_SORT = QtCore.Qt.UserRole + 1

# 状态 → 排序权重(冲突相关优先)
STATUS_ORDER = {
    HotkeyStatus.OCCUPIED: 0,
    HotkeyStatus.SYSTEM: 1,
    HotkeyStatus.ERROR: 2,
    HotkeyStatus.FREE: 3,
    HotkeyStatus.SKIPPED: 4,
}


class HotkeyTableModel(QtCore.QAbstractTableModel):
    """热键结果表格模型。"""

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._rows: list[HotkeyResult] = []

    # ---- 基础接口 ----
    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        col = index.column()

        if role == QtCore.Qt.DisplayRole:
            if col == COL_COMBO:
                return r.name
            if col == COL_MOD:
                return modifier_name(r.modifiers)
            if col == COL_VK:
                return vk_name(r.vk)
            if col == COL_STATUS:
                return r.status.label
            if col == COL_SOURCE:
                return r.source or "—"
            return None

        if role == ROLE_SORT:
            if col == COL_STATUS:
                return STATUS_ORDER[r.status]
            if col == COL_MOD:
                return r.modifiers  # 按位掩码排序
            if col == COL_VK:
                return r.vk
            return r.name  # 组合/来源按文本

        if role == QtCore.Qt.ToolTipRole:
            if col == COL_STATUS:
                tip = {
                    HotkeyStatus.FREE: "当前可成功注册,无人占用",
                    HotkeyStatus.OCCUPIED: "已被某个程序占用,再注册会失败",
                    HotkeyStatus.SYSTEM: "Windows 系统保留,通常无法注册",
                    HotkeyStatus.ERROR: "探测异常(可能是无效组合或权限问题)",
                    HotkeyStatus.SKIPPED: "扫描被停止,未检测",
                }.get(r.status, "")
                return tip
            if col == COL_SOURCE:
                return r.source or "无已知来源匹配"

        if col == COL_STATUS:
            if role == QtCore.Qt.ForegroundRole:
                fg, _ = status_color(r.status.value)
                return QtGui.QColor(fg)
            if role == QtCore.Qt.BackgroundRole:
                _, bg = status_color(r.status.value)
                return QtGui.QColor(bg)
            if role == QtCore.Qt.TextAlignmentRole:
                return int(QtCore.Qt.AlignCenter)

        if role == QtCore.Qt.TextAlignmentRole and col in (COL_COMBO, COL_STATUS):
            return int(QtCore.Qt.AlignCenter)

        return None

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.DisplayRole,
    ):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return COLUMNS[section]
        if role == QtCore.Qt.TextAlignmentRole and orientation == QtCore.Qt.Horizontal:
            return int(QtCore.Qt.AlignCenter)
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    # ---- 增删 ----
    def append_result(self, result: HotkeyResult) -> None:
        row = len(self._rows)
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._rows.append(result)
        self.endInsertRows()

    def flush_results(self, results: list[HotkeyResult]) -> None:
        """批量追加(用于节流后一次性提交,减少重绘)。"""
        if not results:
            return
        first = len(self._rows)
        last = first + len(results) - 1
        self.beginInsertRows(QtCore.QModelIndex(), first, last)
        self._rows.extend(results)
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()

    def reset_results(self, results: list[HotkeyResult]) -> None:
        self.beginResetModel()
        self._rows = list(results)
        self.endResetModel()

    # ---- 查询 ----
    def result_at(self, row: int) -> HotkeyResult:
        return self._rows[row]

    def all_results(self) -> list[HotkeyResult]:
        return list(self._rows)

    def count_by_status(self) -> dict[HotkeyStatus, int]:
        counts: dict[HotkeyStatus, int] = {}
        for r in self._rows:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


class HotkeyFilterProxy(QtCore.QSortFilterProxyModel):
    """状态/搜索/冲突筛选 + 状态列按冲突优先级排序。"""

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._status_filter: Optional[HotkeyStatus] = None
        self._conflict_only: bool = False
        self._search: str = ""

    # ---- 筛选配置 ----
    def set_status_filter(self, status: Optional[HotkeyStatus]) -> None:
        self._status_filter = status
        self.invalidateFilter()

    def set_conflict_only(self, on: bool) -> None:
        self._conflict_only = on
        self.invalidateFilter()

    def set_search(self, text: str) -> None:
        self._search = text.lower().strip()
        self.invalidateFilter()

    # ---- 过滤 ----
    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        r = model.result_at(source_row)

        if self._conflict_only and not r.status.is_conflict:
            return False
        if self._status_filter is not None and r.status != self._status_filter:
            return False
        if self._search:
            if (
                self._search not in r.name.lower()
                and self._search not in r.source.lower()
                and self._search not in modifier_name(r.modifiers).lower()
            ):
                return False
        return True

    # ---- 排序:状态列按冲突优先级,其余按文本/数值 ----
    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        lv = self.sourceModel().data(left, ROLE_SORT)
        rv = self.sourceModel().data(right, ROLE_SORT)
        try:
            return lv < rv
        except TypeError:
            return str(lv) < str(rv)


__all__ = [
    "COLUMNS",
    "COL_COMBO",
    "COL_MOD",
    "COL_VK",
    "COL_STATUS",
    "COL_SOURCE",
    "HotkeyTableModel",
    "HotkeyFilterProxy",
]
