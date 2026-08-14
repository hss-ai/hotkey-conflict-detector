"""扫描快照:序列化 / 持久化 / 两份快照对比(基线 diff)。

杀手锏功能的数据层:每次扫描可存一份带元数据的 JSON 快照,
支持两份快照对比,高亮「新增占用 / 已释放 / 状态变化」——
解决"装了某软件后某个热键突然不能用了"的排查难题。

快照存放:`~/.hotkey_detector/snapshots/snapshot_YYYYMMDD_HHMMSS.json`
(目录复用 _known_data.user_data_dir,可用 HOTKEY_DETECTOR_HOME 覆盖)。

纯逻辑,无 Qt 依赖,CI(Session 0)可单测。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from pathlib import Path
from typing import Any

from ._known_data import user_data_dir
from ._version import __version__
from .apps import list_process_names
from .hotkeys import HotkeyCombo, format_combo
from .suspect import deserialize_suspects, rank_suspects, serialize_suspects


SCHEMA_VERSION = 2

# 视为"冲突"的状态值(占用 / 系统保留)——diff 据此判定新增/释放
CONFLICT_STATUSES = {"occupied", "system"}


@dataclass(frozen=True)
class SnapshotEntry:
    """快照里单条结果的轻量表示。"""

    modifiers: int
    vk: int
    name: str
    status: str       # "free" / "occupied" / "system" / "error" / "skipped"
    source: str
    suspects: list = dataclass_field(default_factory=list)  # list[Suspect](冲突项,嫌疑度 top3)


def snapshots_dir() -> Path:
    """快照目录:~/.hotkey_detector/snapshots。"""
    return user_data_dir() / "snapshots"


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------
def to_dict(results: list[Any], meta: dict | None = None) -> dict:
    """把扫描结果(HotkeyResult 列表)序列化为快照 dict。

    results 元素只需暴露 .modifiers/.vk/.name/.status/.source 属性
    (HotkeyResult 满足;status 取 .value)。
    """
    stats: dict[str, int] = {}
    entries: list[dict] = []
    running = None  # 惰性:首个冲突项才枚举一次进程
    for r in results:
        status = getattr(r.status, "value", str(r.status))
        stats[status] = stats.get(status, 0) + 1
        entry = {
            "modifiers": r.modifiers,
            "vk": r.vk,
            "name": r.name,
            "status": status,
            "source": r.source or "",
        }
        if status in CONFLICT_STATUSES and not getattr(r, "evidence", None):
            if running is None:
                running = list_process_names()
            suspects = rank_suspects(
                HotkeyCombo(vk=r.vk, modifiers=r.modifiers), running)
            if suspects:
                entry["suspects"] = serialize_suspects(suspects)
        entries.append(entry)
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": __version__,
        "meta": meta or {},
        "stats": stats,
        "results": entries,
    }


def save(results: list[Any], meta: dict | None = None, path: str | Path | None = None) -> Path:
    """保存快照。path 为空时存到 snapshots 目录、文件名带时间戳。返回写入路径。"""
    data = to_dict(results, meta)
    if path is None:
        directory = snapshots_dir()
        directory.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = directory / f"snapshot_{ts}.json"
        # 同秒内多次保存:追加序号避免覆盖
        n = 2
        while path.exists():
            path = directory / f"snapshot_{ts}_{n}.json"
            n += 1
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load(path: str | Path) -> dict | None:
    """读取快照 dict。文件缺失或损坏返回 None(不抛,调用方给友好提示)。"""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def entries_from_dict(d: dict) -> list[SnapshotEntry]:
    """从快照 dict 取结果条目列表(容错:缺字段回退默认值)。"""
    out: list[SnapshotEntry] = []
    for e in d.get("results", []) or []:
        if not isinstance(e, dict):
            continue
        mods = e.get("modifiers", 0)
        vk = e.get("vk", 0)
        name = e.get("name") or format_combo(mods, vk)
        out.append(SnapshotEntry(
            modifiers=mods, vk=vk, name=name,
            status=e.get("status", ""), source=e.get("source", ""),
            suspects=deserialize_suspects(e.get("suspects")),
        ))
    return out


def _entry_map(d: dict) -> dict[tuple[int, int], dict]:
    return {(e.get("modifiers", 0), e.get("vk", 0)): e for e in (d.get("results", []) or [])}


def diff(old: dict, new: dict) -> dict[str, list]:
    """对比两份快照,返回 {added, removed, changed}。

    - added:   new 中是冲突(occupied/system)、而 old 中不存在或非冲突 → 新增占用
    - removed: old 中是冲突、而 new 中不存在或非冲突 → 已释放
    - changed: 两边都存在且 status 不同(同属冲突或同属非冲突的细节变化)
    """
    old_map = _entry_map(old)
    new_map = _entry_map(new)

    added: list[dict] = []
    removed: list[dict] = []
    changed: list[tuple[dict, dict]] = []

    for key, ne in new_map.items():
        oe = old_map.get(key)
        new_conflict = ne.get("status") in CONFLICT_STATUSES
        old_conflict = (oe.get("status") in CONFLICT_STATUSES) if oe else False
        if oe is None:
            if new_conflict:
                added.append(ne)
        elif new_conflict and not old_conflict:
            added.append(ne)
        elif old_conflict and not new_conflict:
            removed.append(ne)
        elif ne.get("status") != oe.get("status"):
            changed.append((oe, ne))

    # old 中存在、new 中完全消失的冲突项
    for key, oe in old_map.items():
        if key not in new_map and oe.get("status") in CONFLICT_STATUSES:
            removed.append(oe)

    return {"added": added, "removed": removed, "changed": changed}


def list_snapshots() -> list[Path]:
    """列出 snapshots 目录下的历史快照,按文件名(含时间戳)升序。"""
    directory = snapshots_dir()
    if not directory.exists():
        return []
    return sorted(directory.glob("snapshot_*.json"))


def snapshot_label(d: dict) -> str:
    """生成快照的人类可读标签:时间 + 冲突数。"""
    created = d.get("created_at", "?")
    stats = d.get("stats", {})
    conflict = stats.get("occupied", 0) + stats.get("system", 0)
    meta = d.get("meta") or {}
    tag = f" · {meta['label']}" if isinstance(meta, dict) and meta.get("label") else ""
    return f"{created} ({conflict} 冲突){tag}"


__all__ = [
    "SCHEMA_VERSION",
    "CONFLICT_STATUSES",
    "SnapshotEntry",
    "snapshots_dir",
    "to_dict",
    "save",
    "load",
    "entries_from_dict",
    "diff",
    "list_snapshots",
    "snapshot_label",
]
