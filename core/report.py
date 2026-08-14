"""把扫描结果渲染成单文件自包含 HTML 报告。

纯字符串模板,零第三方依赖。所有用户可控字段(source / meta)经 HTML 转义,
防止破坏结构或注入。色值与本应用 UI(ui/style.py)语义协调,保持视觉一致。

UI 调用:render_html(results, meta) -> str,或 write_html(path, results, meta)。
"""
from __future__ import annotations

import html
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from ._version import __version__

# HTML 配色(与 ui/style.py 协调:绿=空闲 / 红=占用冲突 / 灰=系统 / 橙=异常)
_C_FREE = "#16a34a"
_C_OCCUPIED = "#dc2626"
_C_SYSTEM = "#64748b"
_C_ERROR = "#d97706"
_C_ACCENT = "#2563eb"
_C_BG = "#f4f5f8"
_C_PANEL = "#ffffff"
_C_BORDER = "#e3e7ec"
_C_TEXT = "#1f2933"
_C_MUTED = "#6b7480"

# status 值 → (中文标签, 卡片色)
_STATUS_META: dict[str, tuple[str, str]] = {
    "free": ("空闲", _C_FREE),
    "occupied": ("已占用", _C_OCCUPIED),
    "system": ("系统保留", _C_SYSTEM),
    "error": ("异常", _C_ERROR),
    "skipped": ("已跳过", _C_MUTED),
}


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _status_value(r: Any) -> str:
    return getattr(r.status, "value", str(r.status))


def _extract_app(r: Any) -> str:
    """从结果的 evidence 或 source 文本里提取应用名(用于来源 Top 统计)。"""
    ev = getattr(r, "evidence", None)
    if ev and getattr(ev, "app", None):
        return str(ev.app)
    src = getattr(r, "source", "") or ""
    if src.startswith("可能来自:"):
        rest = src[len("可能来自:"):]
        return rest.split("(")[0].strip()
    return ""


def _stat_counts(results: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        s = _status_value(r)
        counts[s] = counts.get(s, 0) + 1
    return counts


def render_html(results: list[Any], meta: dict | None = None) -> str:
    """渲染自包含 HTML 报告字符串。"""
    meta = meta or {}
    counts = _stat_counts(results)
    total = len(results)
    occupied = counts.get("occupied", 0)
    system = counts.get("system", 0)
    free = counts.get("free", 0)
    error = counts.get("error", 0)
    conflict = occupied + system

    generated = meta.get("generated_at") or datetime.now().isoformat(timespec="seconds")

    # 统计卡片
    cards = [
        ("组合总数", total, _C_ACCENT),
        ("冲突", conflict, _C_OCCUPIED),
        ("已占用", occupied, _C_OCCUPIED),
        ("系统保留", system, _C_SYSTEM),
        ("空闲", free, _C_FREE),
        ("异常", error, _C_ERROR),
    ]
    cards_html = "\n".join(
        f'<div class="card"><div class="card-val" style="color:{c}">{n}</div>'
        f'<div class="card-lab">{_esc(label)}</div></div>'
        for label, n, c in cards
    )

    # 冲突详情表(按冲突优先排序:occupied > system)
    conflict_rows = [r for r in results if _status_value(r) in ("occupied", "system")]
    conflict_rows.sort(key=lambda r: (0 if _status_value(r) == "occupied" else 1, r.name))

    if conflict_rows:
        body = "\n".join(_row_html(r) for r in conflict_rows)
        table_html = (
            '<table class="grid"><thead><tr>'
            '<th>组合</th><th>状态</th><th>作用域</th><th>可能来源</th>'
            '</tr></thead><tbody>\n' + body + "\n</tbody></table>"
        )
    else:
        table_html = '<div class="empty">未检测到冲突组合 🎉</div>'

    # 来源 Top
    src_counter: Counter[str] = Counter()
    for r in conflict_rows:
        app = _extract_app(r)
        if app:
            src_counter[app] += 1
    if src_counter:
        top_items = sorted(src_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        top_html = '<ul class="top">\n' + "\n".join(
            f'<li><span class="app">{_esc(app)}</span>'
            f'<span class="cnt">{n} 个组合</span></li>'
            for app, n in top_items
        ) + "\n</ul>"
    else:
        top_html = '<div class="empty">无已知来源匹配(多为程序注册/钩子占用)</div>'

    # meta 附加信息
    meta_items = []
    if meta.get("label"):
        meta_items.append(("备注", meta["label"]))
    if meta.get("scan_range"):
        meta_items.append(("扫描范围", meta["scan_range"]))
    meta_html = ""
    if meta_items:
        meta_html = '<div class="meta-extra">' + "".join(
            f'<span><b>{_esc(k)}:</b> {_esc(v)}</span>' for k, v in meta_items
        ) + "</div>"

    return _TEMPLATE.format(
        bg=_C_BG, panel=_C_PANEL, border=_C_BORDER, text=_C_TEXT, muted=_C_MUTED, accent=_C_ACCENT,
        title=_esc(meta.get("title", "全局热键冲突检测报告")),
        generated=_esc(generated), version=_esc(__version__),
        conflict_n=conflict, total_n=total,
        cards=cards_html, table=table_html, top=top_html, meta_extra=meta_html,
    )


def _row_html(r: Any) -> str:
    s = _status_value(r)
    label, color = _STATUS_META.get(s, (s, _C_MUTED))
    scope = "系统级" if s == "system" else "全局占用" if s == "occupied" else "—"
    source = getattr(r, "source", "") or "—"
    return (
        f'<tr>'
        f'<td class="combo">{_esc(r.name)}</td>'
        f'<td><span class="badge" style="background:{color}1a;color:{color}">{_esc(label)}</span></td>'
        f'<td>{_esc(scope)}</td>'
        f'<td class="src">{_esc(source)}</td>'
        f'</tr>'
    )


def write_html(path: str | Path, results: list[Any], meta: dict | None = None) -> Path:
    """渲染并写入 HTML 文件,返回路径。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(results, meta), encoding="utf-8")
    return target


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei UI","Segoe UI","PingFang SC",sans-serif;
         background:{bg}; color:{text}; margin:0; padding:24px; }}
  .wrap {{ max-width: 980px; margin:0 auto; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .meta {{ color:{muted}; font-size:13px; margin-bottom:16px; }}
  .meta b {{ color:{text}; }}
  .meta-extra {{ margin-top:8px; display:flex; gap:18px; flex-wrap:wrap; font-size:13px; }}
  .stats {{ display:flex; gap:12px; flex-wrap:wrap; margin:16px 0 24px; }}
  .card {{ background:{panel}; border:1px solid {border}; border-radius:10px;
          padding:14px 18px; min-width:104px; text-align:center; }}
  .card-val {{ font-size:26px; font-weight:700; }}
  .card-lab {{ font-size:12px; color:{muted}; margin-top:2px; }}
  h2 {{ font-size:16px; margin:24px 0 10px; border-left:4px solid {accent};
        padding-left:10px; }}
  table.grid {{ width:100%; border-collapse:collapse; background:{panel};
               border:1px solid {border}; border-radius:8px; overflow:hidden; }}
  table.grid th {{ background:#f7f8fa; color:{muted}; font-size:12px;
                  text-align:left; padding:10px; border-bottom:1px solid {border}; }}
  table.grid td {{ padding:9px 10px; border-bottom:1px solid {border}; font-size:13px; }}
  table.grid tr:last-child td {{ border-bottom:none; }}
  td.combo {{ font-weight:600; font-family:Consolas,monospace; }}
  td.src {{ color:{muted}; font-size:12px; }}
  .badge {{ padding:3px 10px; border-radius:5px; font-size:12px; font-weight:600; }}
  .top {{ list-style:none; padding:0; margin:0; }}
  .top li {{ background:{panel}; border:1px solid {border}; border-radius:8px;
            padding:10px 14px; margin-bottom:8px; display:flex; justify-content:space-between; }}
  .top .app {{ font-weight:600; }} .top .cnt {{ color:{muted}; font-size:13px; }}
  .empty {{ background:{panel}; border:1px solid {border}; border-radius:8px;
           padding:18px; color:{muted}; text-align:center; }}
  footer {{ margin-top:28px; color:{muted}; font-size:12px; text-align:center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>⌨️ {title}</h1>
  <div class="meta">生成时间:<b> {generated}</b> · 版本:<b> v{version}</b>
      · 冲突 <b>{conflict_n}</b> / 共 <b>{total_n}</b> 个组合</div>
  {meta_extra}
  <div class="stats">{cards}</div>
  <h2>冲突详情</h2>
  {table}
  <h2>占用来源 Top</h2>
  {top}
  <footer>由全局热键冲突检测器生成 · RegisterHotKey 探测法 · 来源为尽力推断</footer>
</div>
</body>
</html>"""


__all__ = ["render_html", "write_html"]
