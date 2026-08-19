"""后台扫描线程(QThread)。

从 core/detector.py 迁出:core 保持"不依赖 Qt"的分层底线(AGENTS 约定),
Qt 并发封装归 ui 层。探测/归类/来源解析全部复用 core.detector 公开接口。
"""
from __future__ import annotations

from typing import Optional

from PySide6 import QtCore

from core.apps import refresh_running_processes
from core.detector import filter_combos, probe_result
from core.hotkeys import HotkeyCombo


class ScanThread(QtCore.QThread):
    """在后台逐个探测组合,通过信号实时回报进度与结果。"""

    # 每探测完一个组合发出:(result)
    result_ready = QtCore.Signal(object)
    # 进度:(已完成数, 总数)
    progress = QtCore.Signal(int, int)
    # 全部结束:(统计字典)
    finished_scan = QtCore.Signal(dict)

    def __init__(
        self,
        combos: list[HotkeyCombo],
        exclude: set[tuple[int, int]] | None = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._combos = list(combos)
        # 续扫:已扫过的 (modifiers,vk) 集合,run 时跳过
        self._exclude: set[tuple[int, int]] = set(exclude) if exclude else set()
        self._stop_flag = False

    def request_stop(self) -> None:
        """请求停止(在下一个组合前生效)。"""
        self._stop_flag = True

    def run(self) -> None:  # noqa: D401 - QThread 入口
        # 续扫:剔除已扫过的 combo,只扫剩余
        to_scan = filter_combos(self._combos, self._exclude)
        total = len(to_scan)
        stats = {"free": 0, "occupied": 0, "system": 0, "error": 0, "skipped": 0}
        refresh_running_processes()  # 刷新进程缓存,供证据链判断"app 是否运行"

        for i, combo in enumerate(to_scan):
            if self._stop_flag:
                break  # 用户已请求停止,剩余项不再探测

            result = probe_result(combo.modifiers, combo.vk)
            self.result_ready.emit(result)

            key = result.status.value
            stats[key] = stats.get(key, 0) + 1
            self.progress.emit(i + 1, total)

        scanned = sum(v for k, v in stats.items() if k != "skipped")
        stats["scanned"] = scanned
        stats["total"] = total
        stats["completed"] = scanned == total  # 是否完整扫完(未中途停止)
        self.finished_scan.emit(stats)


__all__ = ["ScanThread"]
