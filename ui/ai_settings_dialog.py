"""AI 设置对话框:配置可选的 LLM 辅助来源分析(OpenAI 兼容端点)。

配置存 ~/.hotkey_detector/ai_config.json;api_key 只落本地,不进报告/快照。
连通性测试在 FnWorker 后台线程执行(test_config 最长阻塞 20s,不能冻结 UI)。
"""
from __future__ import annotations

from PySide6 import QtWidgets

from core.ai_analyze import AiConfig, load_ai_config, save_ai_config, test_config

from .style import STATUS_ERROR, STATUS_FREE, STATUS_OCCUPIED, TEXT_FAINT, TEXT_MUTED
from .workers import FnWorker


class AiSettingsDialog(QtWidgets.QDialog):
    """AI 模型配置(base_url / api_key / model + 连通性测试)。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 设置 · 来源辅助分析")
        self.setMinimumWidth(480)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        intro = QtWidgets.QLabel(
            "配置一个 OpenAI 兼容的 LLM 端点,用于在热键被占用且本地推断无果时"
            "给出「嫌疑度排序 + 排查建议」。<br>"
            f"<span style='color:{TEXT_FAINT}'>仅在点击「AI 分析」时联网;API Key 只保存在本机 "
            "~/.hotkey_detector/ai_config.json。</span>"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        cfg = load_ai_config()
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._base_url = QtWidgets.QLineEdit(cfg.base_url)
        self._base_url.setPlaceholderText("https://api.openai.com/v1")
        self._base_url.textChanged.connect(self._update_http_warn)
        form.addRow("Base URL", self._base_url)

        # http 明文警告(不拦保存——尊重内网自建端点,只提示风险)
        self._warn_lbl = QtWidgets.QLabel(
            f"<span style='color:{STATUS_ERROR}'>⚠ 当前是 http:// 端点:"
            "API Key 会以明文经网络发送。内网自建服务可忽略,公网端点请改用 https://。</span>"
        )
        self._warn_lbl.setWordWrap(True)
        self._warn_lbl.hide()
        form.addRow("", self._warn_lbl)

        self._api_key = QtWidgets.QLineEdit(cfg.api_key)
        self._api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("API Key", self._api_key)

        self._model = QtWidgets.QLineEdit(cfg.model)
        self._model.setPlaceholderText("gpt-4o-mini / glm-4-flash / ...")
        form.addRow("模型名", self._model)
        root.addLayout(form)

        row = QtWidgets.QHBoxLayout()
        self._btn_test = QtWidgets.QPushButton("🔗 测试连通")
        self._btn_test.clicked.connect(self._on_test)
        row.addWidget(self._btn_test)
        self._test_lbl = QtWidgets.QLabel("")
        self._test_lbl.setStyleSheet(f"color:{TEXT_MUTED};")
        row.addWidget(self._test_lbl, 1)
        root.addLayout(row)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btn_cancel = QtWidgets.QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QtWidgets.QPushButton("保存")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self._on_save)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)
        root.addLayout(btns)

        # 打开时若已存 http 端点,直接显示警告(构造函数填文本不触发 textChanged)
        self._update_http_warn(self._base_url.text())

    # ------------------------------------------------------------------
    def _config_from_form(self) -> AiConfig:
        return AiConfig(
            base_url=self._base_url.text().strip().rstrip("/"),
            api_key=self._api_key.text().strip(),
            model=self._model.text().strip(),
        )

    def _update_http_warn(self, text: str) -> None:
        cfg = AiConfig(base_url=text.strip())
        self._warn_lbl.setVisible(cfg.is_plain_http)

    def _on_test(self) -> None:
        cfg = self._config_from_form()
        if not cfg.configured:
            self._test_lbl.setText("请先填全三项再测试")
            self._test_lbl.setStyleSheet(f"color:{STATUS_ERROR};")
            return
        # 后台线程执行(同步 urllib 最长阻塞 20s,会冻结整个事件循环)
        self._btn_test.setEnabled(False)
        self._test_lbl.setText("测试中…")
        self._test_lbl.setStyleSheet(f"color:{TEXT_MUTED};")
        FnWorker.spawn(lambda: test_config(cfg), self._on_test_ok, self._on_test_fail)

    def _on_test_ok(self, reply: str) -> None:
        self._btn_test.setEnabled(True)
        self._test_lbl.setText(f"✓ 连通正常(模型回复:{reply[:30]})")
        self._test_lbl.setStyleSheet(f"color:{STATUS_FREE};")

    def _on_test_fail(self, msg: str) -> None:
        self._btn_test.setEnabled(True)
        self._test_lbl.setText(f"✗ {msg}")
        self._test_lbl.setStyleSheet(f"color:{STATUS_OCCUPIED};")

    def _on_save(self) -> None:
        save_ai_config(self._config_from_form())
        self.accept()


__all__ = ["AiSettingsDialog"]
