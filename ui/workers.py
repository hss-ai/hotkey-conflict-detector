"""轻量后台任务线程:UI 发起耗时调用(AI 网络请求等)避免冻结事件循环。

用法:
    FnWorker.spawn(fn, on_ok=self._on_ok, on_fail=self._on_fail)

生命周期保证(核心设计):
- spawn 把实例挂入类级 ``_alive`` 列表:调用方(对话框)销毁后线程仍能安全跑完,
  不会被 Python GC 提前回收——无 parent 的 QThread 由 Python 侧管理,
  引用随对话框消失会被回收,触发 "QThread: Destroyed while thread is still
  running" 崩溃;线程自然结束后自动移出列表并 ``deleteLater``。
- on_ok/on_fail 连接的是对话框的 bound method:对话框先销毁时 PySide6 自动断开
  连接,结果被安全丢弃,不会访问已销毁的 UI。
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6 import QtCore


class FnWorker(QtCore.QThread):
    """后台执行一个返回 str 的 callable,以 (finished_ok | failed) 信号回报。"""

    finished_ok = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    # 运行中的 worker 强引用存活至线程自然结束(见模块 docstring)
    _alive: list["FnWorker"] = []

    def __init__(self, fn: Callable[[], str], parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._fn = fn

    @classmethod
    def spawn(
        cls,
        fn: Callable[[], str],
        on_ok: Callable[[str], None],
        on_fail: Callable[[str], None],
    ) -> "FnWorker":
        """创建、连接回调并启动;返回实例(一般无需持有)。"""
        w = cls(fn)  # 故意不挂 parent:生命周期由 _alive 管理,不随对话框析构
        w.finished_ok.connect(on_ok)
        w.failed.connect(on_fail)
        w.finished.connect(w._retire)
        cls._alive.append(w)
        w.start()
        return w

    def _retire(self) -> None:
        try:
            FnWorker._alive.remove(self)
        except ValueError:
            pass
        self.deleteLater()

    def run(self) -> None:  # pragma: no cover - 线程路径,单测走 mock
        try:
            text = self._fn()
        except Exception as e:  # noqa: BLE001 - 统一转字符串给 UI 展示
            self.failed.emit(str(e) or e.__class__.__name__)
            return
        self.finished_ok.emit(str(text))


__all__ = ["FnWorker"]
