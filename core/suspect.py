"""嫌疑度排序:证据链(build_evidence)未命中时的"谁最可能占用"启发式推断。

与 Evidence 的区别:
- Evidence:已知热键库**精确命中** (modifiers, vk) 时给出单条证据链,置信度高。
- Suspect:不依赖精确命中——按"该软件在运行 + 软件类别爱占全局热键 + 按键同名(修饰键
  可能被用户改过)+ 进程名含热键特征"等信号综合打分,给出**排序列表**。

打分(0-5★,启发式,仅供排障参考,不保证准确):
- 命中已知默认热键且进程在运行 .......... +5(封顶)
- 命中已知默认热键但进程未检测到 ........ +3
- 已知热键库中同 VK(修饰键可能被用户改过)+ 进程在运行 +2(用户可能改过修饰键)
- 软件类别基础分(启动器/剪贴板/AHK 等爱注册全局热键)+1~3
- 进程名含 hotkey/hook/key 等特征(不在已知库)+2

星级语义(重要,防止"启发式叠满"伪装成精确命中):
- 5★ 专属「精确命中默认热键」的证据组合;
- 无精确命中的纯启发式累加封顶 **4★**——同 VK 猜测 + 类别分等弱证据
  无论怎么叠都不会到 5,与"命中默认热键"严格区分。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ._known_data import merged_known_apps, merged_known_hotkeys
from .apps import list_process_names
from .hotkeys import HotkeyCombo, vk_name


@dataclass
class Suspect:
    """一个嫌疑来源的打分卡。"""

    app: str                     # 应用展示名
    matched: str                 # 匹配到的进程名
    stars: int                   # 0-5
    reasons: list[str] = field(default_factory=list)
    exact_hit: bool = False      # 是否含「精确命中默认热键」证据(5★ 的唯一通道)

    @property
    def star_str(self) -> str:
        return "★" * self.stars + "☆" * (5 - self.stars)


# ---------------------------------------------------------------------------
# 类别基础分:哪些类别的软件"爱注册全局热键"(含自定义组合)
# ---------------------------------------------------------------------------
_CATEGORY_BASE: dict[str, int] = {
    # 启动器:主快捷键几乎必配且常自定义成复杂组合
    "uTools": 3, "Flow Launcher": 3, "Listary": 3, "Wox": 3,
    "Microsoft PowerToys": 2, "Fluent Search": 3, "Quicker": 3,
    # 脚本/自动化:热键完全由用户脚本决定,任何组合都可能
    "AutoHotkey": 3,
    # 剪贴板/截图/录屏:默认就是全局热键
    "Ditto(剪贴板)": 2, "Snipaste": 2, "ShareX": 2, "Bandicam": 2, "OBS Studio": 1,
    "Windows 截图工具": 1,
    # 输入法/词典/翻译:常驻且注册开关热键
    "搜狗输入法": 2, "网易有道词典": 2,
    # 通讯:截图/全局唤起热键
    "微信 WeChat": 1, "QQ": 1, "企业微信": 1, "钉钉 DingTalk": 1, "TIM": 1,
    "腾讯会议": 1, "Zoom": 1,
    # 媒体:全局媒体键/歌词热键
    "网易云音乐": 1, "QQ音乐": 1, "PotPlayer": 1, "VLC": 1,
    # 桌面搜索/文件
    "Everything": 1,
    # 安全软件:常驻,偶有热键
    "火绒安全": 1, "360 系列": 1,
}

# 进程名含这些关键词(且不在已知库)时给"特征分"
_NAME_HINTS = ("hotkey", "hook", "keymap", "shortcut")


def rank_suspects(combo: HotkeyCombo, running: set[str] | None = None) -> list[Suspect]:
    """对某个被占用的组合,给嫌疑来源打分排序(降序)。

    running:进程名集合(小写);None 时现场枚举。
    """
    if running is None:
        running = list_process_names()

    by_app: dict[str, Suspect] = {}

    # 进程 → 已知应用名 的归属表(把子模块热键合并到宿主应用展示,
    # 如 "PowerToys Run" → "Microsoft PowerToys")
    proc_owner: dict[str, str] = {
        p: app.name for app in merged_known_apps() for p in app.processes
    }

    def _group(app: str, procs) -> str:
        owners = {proc_owner.get(p) for p in procs if p} - {None}
        return owners.pop() if len(owners) == 1 and app not in owners else app

    def add(app: str, proc: str, stars: int, reason: str, exact: bool = False) -> None:
        s = by_app.setdefault(app, Suspect(app=app, matched=proc, stars=0))
        s.exact_hit = s.exact_hit or exact
        if stars > 0:
            # 5★ 仅对精确命中开放;纯启发式累加封顶 4★(见模块 docstring)
            cap = 5 if s.exact_hit else 4
            s.stars = min(cap, s.stars + stars)
        s.reasons.append(reason)

    # ① 已知热键库精确命中(同 build_evidence 的信号,但展开全部候选)
    for kh in merged_known_hotkeys().get((combo.modifiers, combo.vk), ()):
        kh_running = any(p in running for p in kh.processes)
        add(_group(kh.app, kh.processes),
            next((p for p in kh.processes if p in running), kh.processes[0] if kh.processes else "?"),
            5 if kh_running else 3,
            f"命中 {kh.app} 默认热键{kh.action}(进程{'在运行' if kh_running else '未检测到'})",
            exact=True)

    # ② 同 VK 不同修饰键:用户可能改过修饰键
    for (mods, vk), khs in merged_known_hotkeys().items():
        if vk == combo.vk and mods != combo.modifiers:
            for kh in khs:
                if any(p in running for p in kh.processes):
                    add(_group(kh.app, kh.processes), kh.processes[0] if kh.processes else "?", 2,
                        f"{vk_name(combo.vk)} 是 {kh.app} 默认热键{kh.action}的按键,修饰键可能被自定义")

    # ③ 已知"热键软件"在运行:给类别基础分
    for app in merged_known_apps():
        matched_proc = next((p for p in app.processes if p in running), None)
        if matched_proc is None:
            continue
        base = _CATEGORY_BASE.get(app.name)
        if base:
            add(app.name, matched_proc, base, "正在运行,且该类软件常注册全局热键")
        else:
            add(app.name, matched_proc, 1, "正在运行的已知热键软件")

    # ④ 不在已知库、但进程名含热键特征的进程
    known_procs = {p for app in merged_known_apps() for p in app.processes}
    for proc in sorted(running):
        if proc in known_procs:
            continue
        stem = proc.rsplit(".", 1)[0]
        if any(h in stem for h in _NAME_HINTS):
            add(proc, proc, 2, f"进程名含热键特征({stem})")

    suspects = sorted(by_app.values(), key=lambda s: (-s.stars, s.app))
    return suspects[:8]  # 最多展示 8 条,避免刷屏


def format_suspects(suspects: list[Suspect]) -> str:
    """纯文本渲染(复制诊断信息 / AI prompt 复用)。"""
    if not suspects:
        return "(无嫌疑来源)"
    lines = []
    for i, s in enumerate(suspects, 1):
        lines.append(f"{i}. {s.star_str} {s.app} ({s.matched})")
        for r in s.reasons:
            lines.append(f"    - {r}")
    return "\n".join(lines)


def serialize_suspects(suspects: list[Suspect], top: int = 3) -> list[dict]:
    """把嫌疑列表序列化为轻量 dict(快照/报告复用,取前 top 条)。"""
    return [
        {"app": s.app, "matched": s.matched, "stars": s.stars,
         "reasons": s.reasons[:2]}
        for s in suspects[:top]
    ]


def deserialize_suspects(raw) -> list[Suspect]:
    """从快照 dict 恢复 Suspect 列表(容错:坏字段跳过)。"""
    out: list[Suspect] = []
    if not isinstance(raw, (list, tuple)):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        app = str(item.get("app", "")).strip()
        if not app:
            continue
        stars = item.get("stars", 0)
        out.append(Suspect(
            app=app,
            matched=str(item.get("matched", "")).strip() or "?",
            stars=stars if isinstance(stars, int) and 0 <= stars <= 5 else 0,
            reasons=[str(r) for r in item.get("reasons", []) or []],
        ))
    return out


__all__ = ["Suspect", "rank_suspects", "format_suspects",
           "serialize_suspects", "deserialize_suspects"]
