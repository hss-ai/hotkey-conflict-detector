"""可选的 AI 辅助来源分析(用户自配 LLM,OpenAI 兼容端点)。

- 配置存 ``~/.hotkey_detector/ai_config.json``(与用户热键库同目录):
  {"base_url": "https://api.example.com/v1", "api_key": "sk-...",
   "model": "gpt-4o-mini"}
- 零依赖:urllib + json,不引入第三方库(项目零依赖底线)。
- 只在用户点击「AI 分析」时发起请求;不配置不联网。
- api_key 只存本地文件,不写入报告/快照。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from ._known_data import user_data_dir
from .apps import list_process_names
from .hotkeys import HotkeyCombo, modifier_name, vk_name
from .suspect import Suspect, format_suspects, rank_suspects


class AiError(RuntimeError):
    """AI 调用失败(未配置/网络/HTTP 错误),message 可直接展示给用户。"""


@dataclass(frozen=True)
class AiConfig:
    base_url: str = ""      # 如 https://api.openai.com/v1(不含 /chat/completions)
    api_key: str = ""
    model: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def masked_summary(self) -> str:
        """脱敏摘要(设置界面展示用,key 只露首尾)。"""
        if not self.api_key:
            return "未设置 API Key"
        k = self.api_key
        return f"{k[:4]}...{k[-4:]}" if len(k) > 8 else "***"


def ai_config_path():
    return user_data_dir() / "ai_config.json"


def load_ai_config() -> AiConfig:
    """读取配置;文件缺失/损坏返回空配置(不抛异常)。"""
    path = ai_config_path()
    if not path.exists():
        return AiConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AiConfig()
    if not isinstance(raw, dict):
        return AiConfig()
    return AiConfig(
        base_url=str(raw.get("base_url", "")).strip().rstrip("/"),
        api_key=str(raw.get("api_key", "")).strip(),
        model=str(raw.get("model", "")).strip(),
    )


def save_ai_config(cfg: AiConfig) -> None:
    """保存配置(建目录 + 落盘,UTF-8 无 BOM)。"""
    path = ai_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"base_url": cfg.base_url, "api_key": cfg.api_key, "model": cfg.model},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 调用(OpenAI 兼容 /chat/completions)
# ---------------------------------------------------------------------------
def _post_chat(cfg: AiConfig, system: str, user: str, timeout: float = 60.0) -> str:
    url = f"{cfg.base_url}/chat/completions"
    payload = json.dumps({
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AiError(f"AI 服务返回 HTTP {e.code}:{e.reason}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AiError(f"无法连接 AI 服务:{e}") from e
    except ValueError as e:
        raise AiError(f"AI 服务返回非法 JSON:{e}") from e
    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise AiError(f"AI 服务返回结构异常:{body}") from e


def build_prompt(combo: HotkeyCombo,
                 suspects: list[Suspect] | None = None,
                 running: set[str] | None = None) -> tuple[str, str]:
    """构造 (system, user) prompt。输入均为本机热键/进程名,不含敏感数据。"""
    if running is None:
        running = list_process_names()
    if suspects is None:
        suspects = rank_suspects(combo, running)
    proc_list = ", ".join(sorted(running)[:200])  # 截断,防 prompt 过长
    system = (
        "你是 Windows 全局热键排障专家。RegisterHotKey 失败(错误 1409)时 Windows 不告知占用者,"
        "你根据已知信息推断哪些软件最可能占用该热键,给出嫌疑度排序和每条的理由,"
        "并给出具体的下一步排查建议(如改哪个软件的哪个设置)。"
        "回答用中文,简明扼要,先给排序结论再给建议,不超过 300 字。"
    )
    user = (
        f"被占用的全局热键:{modifier_name(combo.modifiers)}+{vk_name(combo.vk)}"
        f"(modifiers=0x{combo.modifiers:X}, vk=0x{combo.vk:02X})\n\n"
        f"本地启发式嫌疑排序(仅供参考,可能不准):\n{format_suspects(suspects)}\n\n"
        f"当前运行进程(截取):{proc_list}\n\n"
        "请给出:1) 嫌疑度排序(含理由);2) 排查建议。"
    )
    return system, user


def analyze_combo(combo: HotkeyCombo, cfg: AiConfig | None = None) -> str:
    """调用 AI 分析占用来源;未配置/失败抛 AiError。"""
    if cfg is None:
        cfg = load_ai_config()
    if not cfg.configured:
        raise AiError("未配置 AI 模型。请先在「AI 设置」里填写 base_url / api_key / model。")
    system, user = build_prompt(combo)
    return _post_chat(cfg, system, user)


def test_config(cfg: AiConfig) -> str:
    """测试连通性:发一句最小请求,成功返回模型回复文本,失败抛 AiError。"""
    return _post_chat(cfg, "You are a test endpoint.", "回复:ok", timeout=20.0)


__all__ = [
    "AiConfig",
    "AiError",
    "ai_config_path",
    "load_ai_config",
    "save_ai_config",
    "build_prompt",
    "analyze_combo",
    "test_config",
]
