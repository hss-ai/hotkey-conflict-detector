"""AI 设置对话框:配置可选的 LLM 辅助来源分析(OpenAI 兼容端点)。

配置存 ~/.hotkey_detector/ai_config.json;api_key 只落本地,不进报告/快照。
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from core.ai_analyze import AiConfig, load_ai_config, save_ai_config, test_config


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
            "<span style='color:#888'>仅在点击「AI 分析」时联网;API Key 只保存在本机 "
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
        form.addRow("Base URL", self._base_url)

        self._api_key = QtWidgets.QLineEdit(cfg.api_key)
        self._api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("API Key", self._api_key)

        self._model = QtWidgets.QLineEdit(cfg.model)
        self._model.setPlaceholderText("gpt-4o-mini / glm-4-flash / ...")
        form.addRow("模型名", self._model)
        root.addLayout(form)

        row = QtWidgets.QHBoxLayout()
        self._test_lbl = QtWidgets.QLabel("")
        self._test_lbl.setStyleSheet("color:#6b7480;")
        btn_test = QtWidgets.QPushButton("🔗 测试连通")
        btn_test.clicked.connect(self._on_test)
        row.addWidget(btn_test)
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

    # ------------------------------------------------------------------
    def _config_from_form(self) -> AiConfig:
        return AiConfig(
            base_url=self._base_url.text().strip().rstrip("/"),
            api_key=self._api_key.text().strip(),
            model=self._model.text().strip(),
        )

    def _on_test(self) -> None:
        cfg = self._config_from_form()
        if not cfg.configured:
            self._test_lbl.setText("请先填全三项再测试")
            self._test_lbl.setStyleSheet("color:#d97706;")
            return
        self._test_lbl.setText("测试中…")
        QtWidgets.QApplication.processEvents()
        try:
            reply = test_config(cfg)
            self._test_lbl.setText(f"✓ 连通正常(模型回复:{reply[:30]})")
            self._test_lbl.setStyleSheet("color:#16a34a;")
        except Exception as e:  # AiError 或意外错误,统一展示
            self._test_lbl.setText(f"✗ {e}")
            self._test_lbl.setStyleSheet("color:#dc2626;")

    def _on_save(self) -> None:
        save_ai_config(self._config_from_form())
        self.accept()


__all__ = ["AiSettingsDialog"]
