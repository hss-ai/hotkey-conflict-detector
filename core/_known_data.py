"""已知热键软件与默认热键的数据源(内置常量 + 用户可扩展 JSON)。

设计要点:
- 内置数据仍是 Python 常量(随包打包,无需 PyInstaller --add-data,零打包风险)。
- 用户扩展:读取 ``~/.hotkey_detector/user_hotkeys.json`` 与内置库合并。
  这样社区可分享 JSON、用户可自填条目,而证据链(core.apps.build_evidence)
  会一并考虑用户条目。

用户 JSON 格式(字段均可选,modifiers 支持 int 位掩码或 ["Ctrl","Alt"] 列表
或 "Ctrl+Alt" 字符串)::

    {
      "apps": [
        {"name": "我的软件", "processes": ["myapp.exe"]}
      ],
      "hotkeys": [
        {"modifiers": ["Ctrl","Alt"], "vk": 74, "app": "我的软件",
         "action": "截图", "processes": ["myapp.exe"]}
      ]
    }
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KnownApp:
    name: str                         # 展示名
    processes: tuple[str, ...]        # 可能的进程名(小写)


@dataclass(frozen=True)
class KnownHotkey:
    app: str                          # 展示名
    action: str                       # 功能描述
    processes: tuple[str, ...]        # 判断"是否在运行"用的进程名(小写)


# ---------------------------------------------------------------------------
# 内置数据(从 apps.py 迁移,保持单点维护)
# ---------------------------------------------------------------------------
KNOWN_APPS: tuple[KnownApp, ...] = (
    KnownApp("Microsoft PowerToys", ("powertoys.exe", "fancyzones.exe", "keyboardmanagerengine.exe", "powerlauncher.exe")),
    KnownApp("AutoHotkey", ("autohotkey.exe", "autohotkey64.exe", "autohotkey32.exe", "autohotkey64_unicode.exe")),
    KnownApp("微信 WeChat", ("wechat.exe",)),
    KnownApp("QQ", ("qq.exe",)),
    KnownApp("TIM", ("tim.exe",)),
    KnownApp("钉钉 DingTalk", ("dingtalk.exe", "dingtalklauncher.exe")),
    KnownApp("企业微信", ("wxwork.exe",)),
    KnownApp("Snipaste", ("snipaste.exe",)),
    KnownApp("ShareX", ("sharex.exe",)),
    KnownApp("Windows 截图工具", ("snippingtool.exe", "screenclippinghost.exe")),
    KnownApp("Everything", ("everything.exe",)),
    KnownApp("Listary", ("listary.exe",)),
    KnownApp("Flow Launcher", ("flow.launcher.exe",)),
    KnownApp("Wox", ("wox.exe",)),
    KnownApp("uTools", ("utools.exe",)),
    KnownApp("Quicker", ("quicker.exe",)),
    KnownApp("网易云音乐", ("cloudmusic.exe",)),
    KnownApp("QQ音乐", ("qqmusic.exe",)),
    KnownApp("PotPlayer", ("potplayermini64.exe", "potplayermini.exe", "potplayer.exe")),
    KnownApp("VLC", ("vlc.exe",)),
    KnownApp("OBS Studio", ("obs64.exe", "obs32.exe")),
    KnownApp("Bandicam", ("bdcam.exe",)),
    KnownApp("Ditto(剪贴板)", ("ditto.exe",)),
    KnownApp("腾讯会议", ("wemeetapp.exe",)),
    KnownApp("Zoom", ("zoom.exe",)),
    KnownApp("网易有道词典", ("youdaodict.exe",)),
    KnownApp("火绒安全", ("hipstray.exe", "hipsdaemon.exe", "usysdiag.exe")),
    KnownApp("360 系列", ("360tray.exe", "360safe.exe", "zhudongfangyu.exe")),
    KnownApp("搜狗输入法", ("sogoucloud.exe", "sgtool.exe", "soGouSvc.exe")),
    KnownApp("Fluent Search", ("fluentsearch.exe",)),
    KnownApp("Raycast(若跨平台)", ("raycast.exe",)),
)


# 已知软件的默认全局热键 → 应用记录(用于来源证据链推断)
# 注意:这是"默认值",用户可能改过;仅作排障参考。
KNOWN_HOTKEYS: dict[tuple[int, int], tuple[KnownHotkey, ...]] = {
    (MOD_CONTROL | MOD_ALT, 0x41): (KnownHotkey("QQ", "截图", ("qq.exe",)),),
    (MOD_ALT, 0x41): (
        KnownHotkey("微信", "截图", ("wechat.exe",)),
        KnownHotkey("企业微信", "截图", ("wxwork.exe",)),
    ),
    (MOD_CONTROL | MOD_SHIFT, 0x41): (KnownHotkey("钉钉", "截图", ("dingtalk.exe", "dingtalklauncher.exe")),),
    (MOD_WIN | MOD_SHIFT, 0x53): (KnownHotkey("Windows 截图工具", "截图", ("snippingtool.exe", "screenclippinghost.exe")),),
    (MOD_ALT, 0x20): (
        KnownHotkey("PowerToys Run", "启动器", ("powerlauncher.exe", "powertoys.exe")),
        KnownHotkey("Flow Launcher", "启动器", ("flow.launcher.exe",)),
        KnownHotkey("uTools", "启动器", ("utools.exe",)),
    ),
    (MOD_CONTROL | MOD_ALT, 0x55): (KnownHotkey("uTools", "超级面板", ("utools.exe",)),),
    (MOD_CONTROL, 0xC0): (KnownHotkey("Ditto", "剪贴板", ("ditto.exe",)),),
    (MOD_CONTROL | MOD_ALT, 0x44): (KnownHotkey("网易有道词典", "划词", ("youdaodict.exe",)),),
    (MOD_WIN | MOD_SHIFT, 0x46): (KnownHotkey("Snipaste", "截图", ("snipaste.exe",)),),
    (MOD_CONTROL | MOD_SHIFT | MOD_ALT, 0x53): (KnownHotkey("ShareX", "截图", ("sharex.exe",)),),
}


# ---------------------------------------------------------------------------
# 修饰键解析(支持 int 位掩码 / 名称列表 / "+" 分隔字符串)
# ---------------------------------------------------------------------------
_MOD_NAME_TO_FLAG: dict[str, int] = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT, "option": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN, "windows": MOD_WIN,
}


def parse_modifiers(value) -> int:
    """把用户输入的修饰键描述转为位掩码。

    支持:int(直接返回)、["Ctrl","Alt"] 列表、"Ctrl+Alt+Shift" 字符串。
    未知名称忽略(返回 0 贡献),不抛异常。
    """
    if isinstance(value, bool):  # bool 是 int 子类,排除
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        mods = 0
        for item in value:
            mods |= _MOD_NAME_TO_FLAG.get(str(item).strip().lower(), 0)
        return mods
    if isinstance(value, str):
        mods = 0
        for part in value.replace("，", ",").replace("＋", "+").split("+"):
            mods |= _MOD_NAME_TO_FLAG.get(part.strip().lower(), 0)
        return mods
    return 0


# ---------------------------------------------------------------------------
# 用户扩展加载
# ---------------------------------------------------------------------------
def user_data_dir() -> Path:
    """用户配置目录:~/.hotkey_detector(跨平台用 Path.home)。"""
    env = os.environ.get("HOTKEY_DETECTOR_HOME")
    if env:
        return Path(env)
    return Path.home() / ".hotkey_detector"


def user_hotkeys_path() -> Path:
    return user_data_dir() / "user_hotkeys.json"


def _coerce_process_list(value) -> tuple[str, ...]:
    """把 JSON 里的 processes 字段统一为小写元组。"""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(p).strip().lower() for p in value if str(p).strip())


def load_user_data() -> tuple[list[KnownApp], dict[tuple[int, int], list[KnownHotkey]]]:
    """读取用户 JSON,返回 (apps 列表, hotkeys 字典)。

    文件不存在 / 损坏 / 格式错误时返回 ([], {}) 不抛异常——用户扩展是"尽力而为"。
    """
    path = user_hotkeys_path()
    if not path.exists():
        return [], {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], {}
    if not isinstance(raw, dict):
        return [], {}

    apps: list[KnownApp] = []
    for item in raw.get("apps", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        procs = _coerce_process_list(item.get("processes"))
        if name and procs:
            apps.append(KnownApp(name=name, processes=procs))

    hotkeys: dict[tuple[int, int], list[KnownHotkey]] = {}
    for item in raw.get("hotkeys", []) or []:
        if not isinstance(item, dict):
            continue
        mods = parse_modifiers(item.get("modifiers", 0))
        vk = item.get("vk")
        if not isinstance(vk, int) or vk <= 0:
            continue
        name = str(item.get("app", "")).strip()
        action = str(item.get("action", "")).strip()
        procs = _coerce_process_list(item.get("processes"))
        if not name:
            continue
        kh = KnownHotkey(app=name, action=action, processes=procs)
        hotkeys.setdefault((mods, vk), []).append(kh)

    return apps, hotkeys


# ---------------------------------------------------------------------------
# 合并(带缓存;UI 编辑用户库后调 invalidate_merged_cache() 刷新)
# ---------------------------------------------------------------------------
_merged_apps_cache: tuple[KnownApp, ...] | None = None
_merged_hotkeys_cache: dict[tuple[int, int], tuple[KnownHotkey, ...]] | None = None


def invalidate_merged_cache() -> None:
    """清空合并缓存(用户修改 user_hotkeys.json 后调用以重新加载)。"""
    global _merged_apps_cache, _merged_hotkeys_cache
    _merged_apps_cache = None
    _merged_hotkeys_cache = None


def merged_known_apps() -> tuple[KnownApp, ...]:
    """内置 + 用户 apps(去重:以 (name) 为键,内置优先,用户补充)。"""
    global _merged_apps_cache
    if _merged_apps_cache is not None:
        return _merged_apps_cache
    seen_names = {a.name for a in KNOWN_APPS}
    user_apps, _ = load_user_data()
    extra = [a for a in user_apps if a.name not in seen_names]
    _merged_apps_cache = KNOWN_APPS + tuple(extra)
    return _merged_apps_cache


def merged_known_hotkeys() -> dict[tuple[int, int], tuple[KnownHotkey, ...]]:
    """内置 + 用户 hotkeys 合并:同一 (modifiers,vk) 的候选叠加(用户在后)。"""
    global _merged_hotkeys_cache
    if _merged_hotkeys_cache is not None:
        return _merged_hotkeys_cache
    _, user_hotkeys = load_user_data()
    merged: dict[tuple[int, int], tuple[KnownHotkey, ...]] = {}
    for key, builtins in KNOWN_HOTKEYS.items():
        merged[key] = builtins
    for key, user_list in user_hotkeys.items():
        existing = merged.get(key, ())
        merged[key] = existing + tuple(user_list)
    _merged_hotkeys_cache = merged
    return _merged_hotkeys_cache


__all__ = [
    "KnownApp",
    "KnownHotkey",
    "KNOWN_APPS",
    "KNOWN_HOTKEYS",
    "parse_modifiers",
    "user_data_dir",
    "user_hotkeys_path",
    "load_user_data",
    "invalidate_merged_cache",
    "merged_known_apps",
    "merged_known_hotkeys",
]
