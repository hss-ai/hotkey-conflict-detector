"""core/ai_analyze 单测:配置读写 / 脱敏 / prompt 构造 / HTTP 错误分类(全 mock)。

运行: python tests/test_ai_analyze.py
注:不发真实网络请求——urlopen 全部 monkeypatch;配置读写用临时目录
    (HOTKEY_DETECTOR_HOME),不碰用户真实 ~/.hotkey_detector。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import core.ai_analyze as aa  # noqa: E402
from core.ai_analyze import AiConfig, AiError  # noqa: E402
from core.hotkeys import HotkeyCombo  # noqa: E402
from core.suspect import Suspect  # noqa: E402


# ---------------------------------------------------------------------------
# 工具:临时配置目录 / urlopen mock
# ---------------------------------------------------------------------------
def _with_tmp_home(fn) -> None:
    """把 HOTKEY_DETECTOR_HOME 指到临时目录跑 fn(结束后还原 + 清理)。"""
    old = os.environ.get("HOTKEY_DETECTOR_HOME")
    tmp = tempfile.mkdtemp(prefix="hk_ai_test_")
    os.environ["HOTKEY_DETECTOR_HOME"] = tmp
    try:
        fn()
    finally:
        if old is None:
            os.environ.pop("HOTKEY_DETECTOR_HOME", None)
        else:
            os.environ["HOTKEY_DETECTOR_HOME"] = old


class _FakeResp:
    """urlopen 返回的 context manager 替身。"""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _with_urlopen(fake, fn):
    """把 urllib.request.urlopen 换成 fake 跑 fn(结束后还原)。"""
    orig = urllib.request.urlopen
    urllib.request.urlopen = fake
    try:
        return fn()
    finally:
        urllib.request.urlopen = orig


_CFG = AiConfig(base_url="https://api.example.com/v1", api_key="sk-test-1234567890", model="m1")


# ---------------------------------------------------------------------------
# AiConfig
# ---------------------------------------------------------------------------
def test_configured() -> None:
    assert AiConfig().configured is False, "空配置不应算已配置"
    assert AiConfig(base_url="https://x", api_key="k", model="").configured is False, "缺 model 不应算已配置"
    assert _CFG.configured is True
    print("[OK] AiConfig.configured: 空/缺项/全填")


def test_masked_summary() -> None:
    assert AiConfig().masked_summary() == "未设置 API Key"
    short = AiConfig(base_url="https://x", api_key="sk-12345", model="m")
    assert short.masked_summary() == "***", "短 key(≤8)必须整体打码"
    s = _CFG.masked_summary()
    assert s == "sk***90", f"长 key 只应露首尾各 2 字符,实际 {s!r}"
    assert "12345678" not in s, "脱敏摘要泄露 key 中段"
    print("[OK] masked_summary: 空/短 key 打码/长 key 首尾各 2")


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------
def test_load_missing_returns_empty() -> None:
    def run() -> None:
        cfg = aa.load_ai_config()
        assert cfg == AiConfig(), f"配置文件缺失应返回空配置,实际 {cfg!r}"
    _with_tmp_home(run)
    print("[OK] load_ai_config: 文件缺失 → 空配置")


def test_load_corrupt_returns_empty() -> None:
    def run() -> None:
        aa.ai_config_path().write_text("{not json", encoding="utf-8")
        assert aa.load_ai_config() == AiConfig(), "损坏 JSON 应返回空配置"
        aa.ai_config_path().write_text("[1, 2]", encoding="utf-8")  # 非 dict
        assert aa.load_ai_config() == AiConfig(), "非 dict 顶层应返回空配置"
    _with_tmp_home(run)
    print("[OK] load_ai_config: 损坏/非 dict → 空配置")


def test_save_load_roundtrip() -> None:
    def run() -> None:
        aa.save_ai_config(_CFG)
        loaded = aa.load_ai_config()
        assert loaded == _CFG, f"roundtrip 不一致: {loaded!r}"

        # base_url 尾部斜杠应被去掉
        aa.save_ai_config(AiConfig(base_url="https://x/v1/", api_key="k", model="m"))
        assert aa.load_ai_config().base_url == "https://x/v1", "base_url 尾部 / 应去除"
    _with_tmp_home(run)
    print("[OK] save/load_ai_config: roundtrip + base_url 去尾斜杠")


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------
def test_build_prompt() -> None:
    combo = HotkeyCombo(modifiers=3, vk=0x41)  # Ctrl+Alt+A
    suspects = [Suspect(app="X", matched="x.exe", stars=5, reasons=["命中默认热键"])]
    running = {f"proc{i:03d}.exe" for i in range(300)}
    system, user = aa.build_prompt(combo, suspects=suspects, running=running)

    assert "Ctrl+Alt" in user and "+A" in user, f"user prompt 应含热键名,实际:\n{user}"
    assert "X" in user and "命中默认热键" in user, "user prompt 应含嫌疑列表"
    assert "proc199.exe" in user and "proc200.exe" not in user, "进程列表应截断到 200 个"
    assert "1409" in system, "system prompt 应说明错误码背景"
    print("[OK] build_prompt: 热键名/嫌疑/进程截断(≤200)/system 背景说明")


# ---------------------------------------------------------------------------
# _post_chat 错误分类(全 mock,不发真实请求)
# ---------------------------------------------------------------------------
def test_post_chat_ok() -> None:
    body = json.dumps({"choices": [{"message": {"content": "  hello  "}}]}).encode("utf-8")
    text = _with_urlopen(lambda *a, **k: _FakeResp(body), lambda: aa._post_chat(_CFG, "s", "u"))
    assert text == "hello", f"应返回 strip 后的 content,实际 {text!r}"
    print("[OK] _post_chat: 成功路径返回 content")


def test_post_chat_http_error() -> None:
    err = urllib.error.HTTPError("url", 401, "Unauthorized", None, None)

    def fake(*a, **k):
        raise err

    try:
        _with_urlopen(fake, lambda: aa._post_chat(_CFG, "s", "u"))
        raise AssertionError("HTTPError 应转为 AiError")
    except AiError as e:
        assert "HTTP 401" in str(e), f"应含状态码,实际 {e}"
    print("[OK] _post_chat: HTTPError → AiError(含状态码)")


def test_post_chat_url_error() -> None:
    def fake(*a, **k):
        raise urllib.error.URLError("timed out")

    try:
        _with_urlopen(fake, lambda: aa._post_chat(_CFG, "s", "u"))
        raise AssertionError("URLError 应转为 AiError")
    except AiError as e:
        assert "无法连接" in str(e), f"连接失败应给中文提示,实际 {e}"
    print("[OK] _post_chat: URLError → AiError(无法连接)")


def test_post_chat_bad_payload() -> None:
    # 非法 JSON
    def run_bad_json() -> None:
        try:
            _with_urlopen(lambda *a, **k: _FakeResp(b"not-json"),
                          lambda: aa._post_chat(_CFG, "s", "u"))
            raise AssertionError("非法 JSON 应转为 AiError")
        except AiError as e:
            assert "非法 JSON" in str(e)

    # 结构缺 choices
    def run_bad_shape() -> None:
        body = json.dumps({"unexpected": True}).encode("utf-8")
        try:
            _with_urlopen(lambda *a, **k: _FakeResp(body),
                          lambda: aa._post_chat(_CFG, "s", "u"))
            raise AssertionError("缺 choices 应转为 AiError")
        except AiError as e:
            assert "结构异常" in str(e)

    run_bad_json()
    run_bad_shape()
    print("[OK] _post_chat: 非法 JSON / 结构异常 → AiError")


def test_analyze_combo_unconfigured() -> None:
    def run() -> None:
        try:
            aa.analyze_combo(HotkeyCombo(3, 0x41), cfg=AiConfig())
            raise AssertionError("未配置应抛 AiError")
        except AiError as e:
            assert "未配置" in str(e)
    _with_tmp_home(run)
    print("[OK] analyze_combo: 未配置 → AiError(未配置提示)")


def test_is_plain_http() -> None:
    assert AiConfig(base_url="http://192.168.1.5:8000/v1").is_plain_http is True
    assert AiConfig(base_url="HTTP://x/v1").is_plain_http is True, "应大小写不敏感"
    assert AiConfig(base_url="https://api.x.com/v1").is_plain_http is False
    assert AiConfig().is_plain_http is False, "空 base_url 不算明文 http"
    print("[OK] is_plain_http: http/HTTP/https/空")


def main() -> int:
    test_configured()
    test_masked_summary()
    test_is_plain_http()
    test_load_missing_returns_empty()
    test_load_corrupt_returns_empty()
    test_save_load_roundtrip()
    test_build_prompt()
    test_post_chat_ok()
    test_post_chat_http_error()
    test_post_chat_url_error()
    test_post_chat_bad_payload()
    test_analyze_combo_unconfigured()
    print("[OK] test_ai_analyze 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
