"""NiceGUI frontend — browser-based display with server-side rendering.

Architecture:
  - Python backend parses files and generates chart images (matplotlib → base64 PNG)
  - NiceGUI serves the UI as a local web app
  - Browser only displays <img> tags — no Chart.js or JS computation
"""
from __future__ import annotations

import base64
import io
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

from nicegui import ui, run

from .parser import parse_statement
from .analysis import analyze
from .charts import (
    chart_equity, chart_symbol, chart_monthly, chart_winloss,
    chart_hourly, chart_streaks, chart_equity_overlay, chart_monthly_compare,
)

PORT = 19799
BLUE = "#2563eb"
GREEN = "#10b981"
RED = "#ef4444"
TEXT = "#1f2937"
MUTED = "#6b7280"
BG = "#f8fafc"

# Store loaded accounts for comparison
_accounts: list[dict[str, Any]] = []


def _load_file(path: str) -> dict[str, Any] | None:
    """Parse and analyze a single file."""
    result = parse_statement(path)
    trades = result["trades"]
    if not trades:
        return None
    stats = analyze(trades)
    return {
        "account": result["account"],
        "file": Path(path).name,
        "trades": trades,
        "stats": stats,
        "type": result["type"],
    }


def _stat_card(label: str, value: str, color: str = TEXT) -> str:
    """Render a statistics card."""
    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;
                padding:10px 12px;text-align:center;min-width:90px">
      <div style="font-size:10px;color:#6b7280;margin-bottom:2px">{label}</div>
      <div style="font-size:16px;font-weight:700;color:{color}">{value}</div>
    </div>"""


def _chart_block(img_b64: str, wide: bool = False) -> str:
    """Render a chart image block."""
    if not img_b64:
        return ""
    w = "grid-column:1/-1;" if wide else ""
    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
                padding:10px;overflow:hidden;{w}">
      <img src="data:image/png;base64,{img_b64}" style="width:100%;display:block">
    </div>"""


def _trade_table(trades: list[dict], limit: int = 200) -> str:
    """Render a trade detail table."""
    rows = []
    for t in sorted(trades, key=lambda x: x["profit"], reverse=True)[:limit]:
        ot = t["open_time"].strftime("%Y-%m-%d %H:%M") if t["open_time"] else "-"
        ct = t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else "-"
        cl = "win" if t["profit"] > 0 else "loss"
        rows.append(
            f'<tr class="{cl}"><td>{t["ticket"]}</td><td>{ot}</td>'
            f'<td>{t["type"].upper()}</td><td>{t["volume"]}</td>'
            f'<td>{t["symbol"].upper()}</td><td>{ct}</td>'
            f'<td>${t["profit"]:+,.2f}</td></tr>'
        )
    return f"""
    <div style="max-height:400px;overflow:auto;margin-top:8px">
    <table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr>
      <th style="background:#f1f5f9;padding:6px 8px;text-align:left;font-weight:600;
                 border-bottom:2px solid #2563eb;position:sticky;top:0">Ticket</th>
      <th style="background:#f1f5f9;padding:6px 8px;text-align:left;font-weight:600;
                 border-bottom:2px solid #2563eb;position:sticky;top:0">开仓</th>
      <th style="background:#f1f5f9;padding:6px 8px;text-align:left;font-weight:600;
                 border-bottom:2px solid #2563eb;position:sticky;top:0">方向</th>
      <th style="background:#f1f5f9;padding:6px 8px;text-align:left;font-weight:600;
                 border-bottom:2px solid #2563eb;position:sticky;top:0">手数</th>
      <th style="background:#f1f5f9;padding:6px 8px;text-align:left;font-weight:600;
                 border-bottom:2px solid #2563eb;position:sticky;top:0">品种</th>
      <th style="background:#f1f5f9;padding:6px 8px;text-align:left;font-weight:600;
                 border-bottom:2px solid #2563eb;position:sticky;top:0">平仓</th>
      <th style="background:#f1f5f9;padding:6px 8px;text-align:left;font-weight:600;
                 border-bottom:2px solid #2563eb;position:sticky;top:0">盈亏</th>
    </tr></thead>
    <tbody>{"".join(rows)}</tbody></table></div>
    """


def build_single_view(acc: dict[str, Any]) -> str:
    """Build HTML for single-account analysis view."""
    stats = acc["stats"]
    if not stats:
        return "<p>No data</p>"

    charts = {
        "equity": chart_equity(stats),
        "symbol": chart_symbol(stats),
        "monthly": chart_monthly(stats),
        "winloss": chart_winloss(stats),
        "hourly": chart_hourly(stats),
        "streaks": chart_streaks(stats),
    }

    cards_html = "".join([
        _stat_card("总交易", str(stats["count"])),
        _stat_card("总盈亏", f"${stats['total_pl']:+,.2f}",
                   GREEN if stats["total_pl"] >= 0 else RED),
        _stat_card("胜率", f"{stats['wr']:.0f}%", GREEN),
        _stat_card("盈利因子",
                   f"{stats['pf']:.2f}" if stats["pf"] != float("inf") else "∞"),
        _stat_card("最大回撤", f"${stats['max_dd']:,.2f}", RED),
        _stat_card("夏普比率", f"{stats['sharpe']:.2f}",
                   GREEN if stats["sharpe"] >= 0 else RED),
        _stat_card("均盈", f"+${stats['avg_win']:,.2f}", GREEN),
        _stat_card("均亏", f"-${abs(stats['avg_loss']):,.2f}", RED),
        _stat_card("最佳", f"+${stats['best']:,.2f}", GREEN),
        _stat_card("最差", f"-${abs(stats['worst']):,.2f}", RED),
        _stat_card("连续盈利", f"{stats['max_win_streak']}笔"),
        _stat_card("连续亏损", f"{stats['max_loss_streak']}笔"),
    ])

    return f"""
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">
      {cards_html}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
      {_chart_block(charts['equity'], wide=True)}
      {_chart_block(charts['symbol'])}
      {_chart_block(charts['winloss'])}
      {_chart_block(charts['monthly'], wide=True)}
      {_chart_block(charts['streaks'])}
      {_chart_block(charts['hourly'])}
    </div>
    <h3 style="font-size:14px;margin:12px 0 6px">📋 逐笔明细</h3>
    {_trade_table(acc['trades'])}
    """


def build_compare_view(accounts: list[dict[str, Any]]) -> str:
    """Build HTML for multi-account comparison view."""
    if len(accounts) < 2:
        return ("<p style='padding:40px;text-align:center;color:#6b7280'>"
                "请先加载 2 个以上账户</p>")

    # Comparison stat cards
    headers = ["指标"] + [a["account"] for a in accounts]
    rows_data = [
        ("笔数", [str(a["stats"]["count"]) for a in accounts], TEXT),
        ("总盈亏", [f"${a['stats']['total_pl']:+,.2f}" for a in accounts],
         lambda vs: [GREEN if float(v.replace("$","").replace("+","").replace(",","")) >= 0 else RED for v in vs]),
        ("胜率", [f"{a['stats']['wr']:.0f}%" for a in accounts], GREEN),
        ("最大回撤", [f"${a['stats']['max_dd']:,.2f}" for a in accounts], RED),
        ("夏普", [f"{a['stats']['sharpe']:.2f}" for a in accounts], TEXT),
        ("连续盈利", [str(a["stats"]["max_win_streak"]) for a in accounts], TEXT),
        ("连续亏损", [str(a["stats"]["max_loss_streak"]) for a in accounts], TEXT),
    ]

    def _color_for(val_str, spec):
        if callable(spec):
            return spec([val_str])[0] if spec else TEXT
        return spec if isinstance(spec, str) else TEXT

    # Build comparison table
    table_html = "<table style='width:100%;border-collapse:collapse;font-size:12px;margin:12px 0'>"
    table_html += "<thead><tr>"
    for h in headers:
        table_html += f"<th style='background:#f1f5f9;padding:8px 10px;text-align:center;font-weight:600;border-bottom:2px solid #2563eb'>{h}</th>"
    table_html += "</tr></thead><tbody>"
    for label, values, color_spec in rows_data:
        table_html += f"<tr><td style='padding:6px 10px;font-weight:600;border-bottom:1px solid #e5e7eb'>{label}</td>"
        for v in values:
            c = _color_for(v, color_spec)
            table_html += f"<td style='padding:6px 10px;text-align:center;border-bottom:1px solid #e5e7eb;color:{c};font-weight:600'>{v}</td>"
        table_html += "</tr>"
    table_html += "</tbody></table>"

    # Symbol comparison
    all_syms: set[str] = set()
    for a in accounts:
        all_syms.update(a["stats"].get("sym_pl", {}).keys())
    top_syms = sorted(all_syms, key=lambda s: sum(
        abs(a["stats"].get("sym_pl", {}).get(s, 0)) for a in accounts
    ), reverse=True)[:15]

    sym_table = "<table style='width:100%;border-collapse:collapse;font-size:11px;margin:12px 0'>"
    sym_headers = ["品种"] + [a["account"] for a in accounts]
    sym_table += "<thead><tr>"
    for h in sym_headers:
        sym_table += f"<th style='background:#f1f5f9;padding:6px 8px;text-align:center;font-weight:600;border-bottom:2px solid #2563eb'>{h}</th>"
    sym_table += "</tr></thead><tbody>"
    for sym in top_syms:
        sym_table += f"<tr><td style='padding:5px 8px;font-weight:600;border-bottom:1px solid #e5e7eb'>{sym.upper()}</td>"
        for a in accounts:
            pl = a["stats"].get("sym_pl", {}).get(sym, 0)
            c = GREEN if pl >= 0 else RED
            sym_table += f"<td style='padding:5px 8px;text-align:center;border-bottom:1px solid #e5e7eb;color:{c}'>${pl:+,.0f}</td>"
        sym_table += "</tr>"
    sym_table += "</tbody></table>"

    # Charts
    charts_html = f"""
    <div style="display:grid;grid-template-columns:1fr;gap:10px;margin-bottom:10px">
      {_chart_block(chart_equity_overlay(accounts), wide=True)}
      {_chart_block(chart_monthly_compare(accounts), wide=True)}
    </div>
    """

    return f"""
    {charts_html}
    <h3 style="font-size:14px;margin:12px 0 6px">📊 统计对比</h3>
    {table_html}
    <h3 style="font-size:14px;margin:12px 0 6px">🎯 品种对比</h3>
    {sym_table}
    """


# ─── NiceGUI UI ─────────────────────────────────────────────────

@ui.page("/")
def index():
    """Main page with tabs for single analysis and comparison."""
    # CSS
    ui.add_head_html("""
    <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:'Segoe UI',system-ui,sans-serif;background:#f8fafc;color:#1f2937}
    .win{color:#10b981}.loss{color:#ef4444}
    tr:hover td{background:#f0f4ff}
    td{padding:5px 8px;border-bottom:1px solid #e5e7eb}
    </style>
    """)

    # Header
    with ui.header(elevated=True).classes("bg-blue-700 text-white"):
        ui.label("📊 MT Desk — MT4/MT5 Trading Analytics").classes("text-lg font-bold")
        ui.label("Python 本地解析 · 浏览器只显示不计算").classes("text-sm opacity-80")

    # Tabs
    with ui.tabs().classes("w-full") as tabs:
        single_tab = ui.tab("📈 单账户分析")
        compare_tab = ui.tab("👥 多账户对比")

    with ui.tab_panels(tabs, value=single_tab).classes("w-full"):
        # === Tab 1: Single Account ===
        with ui.tab_panel(single_tab):
            status_label = ui.label("拖放 MT4/MT5 HTML 文件到下方区域").classes("text-sm text-gray-500 mb-2")

            upload = ui.upload(
                label="📂 选择文件 (.htm/.html)",
                on_upload=lambda e: _handle_upload(e, content_display, status_label),
                auto_upload=True,
                multiple=False,
            ).classes("w-full").props('accept=".htm,.html"')

            content_display = ui.html("").classes("w-full")

        # === Tab 2: Compare ===
        with ui.tab_panel(compare_tab):
            compare_status = ui.label(f"已加载 {len(_accounts)} 个账户").classes("text-sm text-gray-500 mb-2")

            compare_upload = ui.upload(
                label="📂 添加对比账户 (.htm/.html)",
                on_upload=lambda e: _handle_compare_upload(e, compare_content, compare_status),
                auto_upload=True,
                multiple=False,
            ).classes("w-full").props('accept=".htm,.html"')

            with ui.row().classes("gap-2 mt-2"):
                ui.button("🔄 清除全部", on_click=lambda: _clear_accounts(compare_content, compare_status))

            compare_content = ui.html("").classes("w-full")


async def _handle_upload(e, display, status_label):
    """Handle file upload for single account analysis."""
    status_label.set_text("⏳ 解析中...")

    # NiceGUI upload: read content directly (supports bytes or stream)
    data = e.content.read() if hasattr(e.content, 'read') else e.content
    if isinstance(data, str):
        data = data.encode("utf-8")

    # Detect encoding from BOM and decode to string
    if data[:2] == b"\xff\xfe":
        text = data.decode("utf-16-le", errors="replace")
    elif data[:2] == b"\xfe\xff":
        text = data.decode("utf-16-be", errors="replace")
    else:
        text = data.decode("utf-8", errors="replace")

    try:
        result = await run.io_bound(_load_from_text, text, getattr(e, 'name', 'upload.htm'))
        if result is None or result["stats"] is None:
            display.set_content("<p style='padding:40px;text-align:center;color:#ef4444'>未找到交易记录</p>")
            status_label.set_text("❌ 未找到交易")
            return

        global _accounts
        _accounts = [a for a in _accounts if a["account"] != result["account"]]
        _accounts.append(result)

        html = build_single_view(result)
        display.set_content(html)
        status_label.set_text(
            f"✅ {result['file']} — {result['stats']['count']}笔 · "
            f"P/L: ${result['stats']['total_pl']:+,.2f} · "
            f"胜率: {result['stats']['wr']:.0f}%"
        )
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        display.set_content(f"<pre style='color:#ef4444;font-size:11px'>{tb}</pre>")
        status_label.set_text(f"❌ 错误: {exc}")


def _load_from_text(text: str, filename: str) -> dict[str, Any] | None:
    """Parse statement directly from text string (no file I/O)."""
    from .parser import _detect_and_parse
    from .analysis import analyze
    result = _detect_and_parse(text, filename)
    trades = result["trades"]
    if not trades:
        return None
    stats = analyze(trades)
    return {
        "account": result["account"],
        "file": filename,
        "trades": trades,
        "stats": stats,
        "type": result["type"],
    }


async def _handle_compare_upload(e, display, status_label):
    """Handle file upload for comparison."""
    await _handle_upload(e, display, status_label)
    global _accounts
    if len(_accounts) >= 2:
        html = build_compare_view(_accounts)
        display.set_content(html)
    status_label.set_text(f"已加载 {len(_accounts)} 个账户")


def _clear_accounts(display, status_label):
    """Clear all loaded accounts."""
    global _accounts
    _accounts = []
    display.set_content("")
    status_label.set_text("已加载 0 个账户")


def _open_browser():
    """Open default browser after server starts."""
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def main():
    """Entry point for the desktop app."""
    # Fix PyInstaller --noconsole: stdout/stderr are None, uvicorn crashes
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = sys.stdout

    # Disable uvicorn access logs to avoid isatty issues
    import logging
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    # Start browser after a short delay (server needs to be ready)
    threading.Timer(0.8, _open_browser).start()

    ui.run(
        title="MT Desk — Trading Analytics",
        host="127.0.0.1",
        port=PORT,
        reload=False,
        show=False,
        uvicorn_logging_level="warning",
    )


if __name__ == "__main__":
    main()
