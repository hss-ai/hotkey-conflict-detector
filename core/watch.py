"""实时守望核心逻辑:对一个热键组合轮询探测,记录状态时间线与转变点。

解决"间歇性占用"——某热键时好时坏(软件周期性注册/注销)。
本模块只含纯逻辑(WatchState 状态机 + 时间线),不含 Qt 定时器;
UI 层(us/watch_dialog)用 QTimer 轮询 quick_probe 后调 record()。

WatchState.record(status, running_apps) 追加一条事件;
.transitions 自动识别 FREE→OCCUPIED 等状态转变并记录当时运行进程。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WatchEvent:
    """单次探测的事件快照。"""

    timestamp: str            # ISO 格式时间
    status: str               # free/occupied/system/error
    running_apps: list[str]   # 当时的运行软件(展示名列表,可能为空)


@dataclass
class WatchState:
    """一个组合的守望状态机。"""

    events: list[WatchEvent] = field(default_factory=list)

    def record(self, status: str, running_apps: list[str] | None = None) -> WatchEvent:
        """记录一次探测。status 取 HotkeyStatus.value 字符串(如 'free')。"""
        ev = WatchEvent(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            status=status,
            running_apps=list(running_apps or []),
        )
        self.events.append(ev)
        return ev

    @property
    def current_status(self) -> str | None:
        return self.events[-1].status if self.events else None

    @property
    def transitions(self) -> list[dict]:
        """状态转变点列表(每次 status 与前一条不同时记录)。

        每项:{at, from, to, running_apps},含转变时刻与当时运行进程。
        FREE→OCCUPIED 与反向都会被识别。
        """
        result: list[dict] = []
        for i in range(1, len(self.events)):
            prev = self.events[i - 1].status
            cur = self.events[i].status
            if prev != cur:
                result.append({
                    "at": self.events[i].timestamp,
                    "from": prev,
                    "to": cur,
                    "running_apps": list(self.events[i].running_apps),
                })
        return result

    @property
    def conflict_transitions(self) -> list[dict]:
        """仅保留涉及冲突(occupied/system)↔非冲突 的转变——最有诊断价值。"""
        conflict = {"occupied", "system"}
        return [
            t for t in self.transitions
            if (t["from"] in conflict) != (t["to"] in conflict)
        ]

    @property
    def summary(self) -> str:
        """人类可读的时间线摘要(供对话框/复制)。"""
        if not self.events:
            return "尚未开始守望。"
        cur = self.current_status
        lines = [f"已记录 {len(self.events)} 次探测,当前状态:{cur}。"]
        cts = self.conflict_transitions
        if cts:
            lines.append(f"检测到 {len(cts)} 次占用状态转变(最近 5 次):")
            for t in cts[-5:]:
                apps = "、".join(t["running_apps"]) or "(无已知软件)"
                lines.append(f"  {t['at']}  {t['from']} → {t['to']}  运行:{apps}")
        else:
            lines.append("期间占用状态未发生变化。")
        return "\n".join(lines)

    def clear(self) -> None:
        self.events.clear()


__all__ = ["WatchEvent", "WatchState"]
