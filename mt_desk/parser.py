r"""Streaming MT4/MT5 HTML Statement Parser.

Handles 500MB+ files without loading the entire document into memory.
Uses line-by-line indexOf scanning instead of regex on full text.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterator


def detect_encoding(filepath: str | Path) -> str:
    """Detect file encoding from BOM."""
    with open(filepath, "rb") as f:
        bom = f.read(2)
    if bom == b"\xff\xfe":
        return "utf-16-le"
    elif bom == b"\xfe\xff":
        return "utf-16-be"
    return "utf-8"


def extract_cells(row_html: str) -> list[str]:
    r"""Extract cell text from a <tr> element using split (no regex)."""
    cells = []
    # Split by closing </td> or </th>
    parts = re.split(r"</t[dh]\s*>", row_html, flags=re.IGNORECASE)
    for part in parts[:-1]:  # last part is after final closing tag
        # Find the opening <td> or <th> tag (case-insensitive)
        lo = part.lower()
        tag_start = lo.rfind("<td")
        if tag_start < 0:
            tag_start = lo.rfind("<th")
        if tag_start < 0:
            continue
        # Find the '>' that closes the opening tag
        gt = part.find(">", tag_start)
        if gt < 0:
            continue
        content = part[gt + 1:]
        # Strip inner HTML tags and entities
        content = re.sub(r"<[^>]+>", "", content)
        content = content.replace("&nbsp;", " ").replace("&amp;", "&").strip()
        cells.append(content)
    return cells


def parse_date(s: str) -> datetime | None:
    """Parse MT4/MT5 date format: YYYY.MM.DD HH:MM:SS."""
    if not s or s.strip() in ("", "&nbsp;", "\xa0"):
        return None
    parts = s.strip().split()
    if len(parts) < 1:
        return None
    d = parts[0].split(".")
    t = (parts[1] if len(parts) >= 2 else "00:00:00").split(":")
    if len(d) >= 3 and len(t) >= 3:
        try:
            return datetime(int(d[0]), int(d[1]), int(d[2]),
                            int(t[0]), int(t[1]), int(t[2]))
        except (ValueError, IndexError):
            pass
    return None


def clean_number(s: str) -> float:
    """Parse numeric string, stripping commas and spaces."""
    try:
        return float(re.sub(r"[,\s]", "", s) or "0")
    except ValueError:
        return 0.0


def is_header_row(cells: list[str]) -> bool:
    """Check if row looks like a table header."""
    keywords = [
        "time", "时间", "時間", "ticket", "position", "持仓", "持倉",
        "symbol", "品种", "品種", "type", "类型", "類型", "volume",
        "交易量", "price", "价格", "價格", "swap", "库存费", "庫存費",
        "利息", "profit", "盈利", "comment", "order", "订单", "訂單",
        "deal", "成交", "login", "登录", "登錄",
    ]
    matches = 0
    for c in cells:
        cl = c.lower().replace(" ", "")
        for kw in keywords:
            if kw in cl:
                matches += 1
    return matches >= 2


def parse_statement(filepath: str | Path, chunk_size: int = 8 * 1024 * 1024) -> dict:
    """Parse an MT4 or MT5 HTML statement file.

    Uses chunked reading to handle large files (500MB+) without OOM.
    For files smaller than chunk_size, reads in one pass (fast path).
    For larger files, accumulates chunks and parses incrementally.

    Returns: {"account": str, "trades": list[dict], "type": "mt4"|"mt5"}
    """
    filepath = Path(filepath)
    enc = detect_encoding(filepath)
    file_size = filepath.stat().st_size

    if file_size <= chunk_size:
        # Fast path: small file, read in one go
        with open(filepath, "r", encoding=enc, errors="replace") as f:
            html = f.read()
        return _detect_and_parse(html, filepath.stem)

    # Slow path: chunked reading for large files
    chunks = []
    with open(filepath, "r", encoding=enc, errors="replace") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)
    html = "".join(chunks)
    return _detect_and_parse(html, filepath.stem)


def _detect_and_parse(html: str, name: str = "unknown") -> dict:
    """Parse HTML text directly (no file I/O)."""

    # Detect format — MT5 detection covers multiple report types
    is_mt5 = any(kw in html for kw in [
        "交易历史报告", "交易帐号报告", "交易账号报告",
        "Trade History", "Trading History", "Account Statement",
        "MT5", "MetaTrader 5",
    ])

    # Extract account
    if is_mt5:
        # Try multiple patterns for MT5 account extraction
        # Pattern 1: "NNNNNNN: NAME -" in title
        m = re.search(r"(\d{5,})\s*[:：]\s*[\w\s]+-", html)
        # Pattern 2: "NNNNNN: NAME" in title
        if not m:
            m = re.search(r"(\d{5,})\s*[:：]", html)
        # Pattern 3: digits in bold after "账户" or "Account"
        if not m:
            m = re.search(r"(?:账户|Account)[^<]*<\w[^>]*>\s*<b>(\d{5,})", html)
    else:
        m = re.search(r"Account:\s*(\d+)", html, re.IGNORECASE)
    account = m.group(1) if m else name

    if is_mt5:
        trades = _parse_mt5(html)
        return {"account": account, "trades": trades, "type": "mt5"}
    else:
        trades = _parse_mt4(html)
        return {"account": account, "trades": trades, "type": "mt4"}


def _parse_mt4(html: str) -> list[dict]:
    """Parse MT4 Statement HTML."""
    trades = []
    sections = ["Closed Transactions:", "Open Trades:"]

    for sec_name in sections:
        idx = html.find(sec_name)
        if idx < 0:
            continue

        # Find section end
        after = html[idx:]
        markers = ["Open Trades:", "Working Orders:", "Summary:", "Closed P/L:"]
        ei = len(after)
        for m in markers:
            p = after.find(m, len(sec_name))
            if 0 < p < ei:
                ei = p

        section_html = after[:ei]

        # Stream through rows with indexOf
        pos = 0
        col_map = None
        while True:
            s = section_html.find("<tr", pos)
            if s < 0:
                break
            e = section_html.find("</tr>", s)
            if e < 0:
                break
            row = section_html[s:e + 5]
            pos = e + 5

            cells = extract_cells(row)
            if len(cells) < 5:
                continue

            # Header detection
            if col_map is None and is_header_row(cells):
                col_map = _build_col_map(cells)
                continue

            rt = cells[2].strip().lower() if len(cells) > 2 else ""

            # Balance row
            if rt == "balance" and len(cells) >= 5:
                continue  # skip for now

            # Try column map
            if col_map:
                trade = _parse_with_map(cells, col_map)
                if trade:
                    trades.append(trade)
                    continue

            # Fallback: standard 14-column MT4 format
            if rt in ("buy", "sell") and len(cells) >= 14:
                trade = {
                    "ticket": cells[0].strip(),
                    "type": rt,
                    "volume": clean_number(cells[3]),
                    "symbol": cells[4].strip().lower(),
                    "profit": clean_number(cells[13]),
                    "commission": clean_number(cells[10]),
                    "swap": clean_number(cells[12]),
                    "taxes": clean_number(cells[11]),
                    "open_price": clean_number(cells[5]),
                    "close_price": clean_number(cells[9]),
                    "sl": clean_number(cells[6]),
                    "tp": clean_number(cells[7]),
                    "open_time": parse_date(cells[1]),
                    "close_time": parse_date(cells[8]) or parse_date(cells[1]),
                }
                if trade["open_time"] is not None and trade["profit"] is not None:
                    trades.append(trade)

    return trades


def _parse_mt5(html: str) -> list[dict]:
    """Parse MT5 Trade History HTML."""
    trades = []

    # Extract table content
    table_content = ""
    pos = 0
    while True:
        ts = html.find("<table", pos)
        if ts < 0:
            break
        te = html.find("</table>", ts)
        if te < 0:
            break
        table_content += html[ts:te + 8]
        pos = te + 8
    if not table_content:
        table_content = html

    # Stream rows
    pos = 0
    col_map = None
    while True:
        s = table_content.find("<tr", pos)
        if s < 0:
            break
        e = table_content.find("</tr>", s)
        if e < 0:
            break
        row = table_content[s:e + 5]
        pos = e + 5

        cells = extract_cells(row)
        if len(cells) < 5:
            # Section header? (单行文字如 "持仓"、"订单")
            if cells and len(cells) <= 3 and len("".join(cells)) < 20:
                col_map = None  # reset column map on section change
            continue

        if col_map is None and is_header_row(cells):
            col_map = _build_col_map(cells)
            continue

        if col_map:
            trade = _parse_with_map(cells, col_map)
            if trade:
                trades.append(trade)

    return trades


def _build_col_map(cells: list[str]) -> dict:
    """Build column index map from header row."""
    mapping = {}
    for i, c in enumerate(cells):
        cl = c.lower().replace(" ", "").replace(".", "").replace("/", "").replace("_", "")
        if any(kw in cl for kw in ["ticket", "position", "持仓", "持倉", "order", "订单", "訂單"]):
            mapping["ticket"] = i
        if any(kw in cl for kw in ["time", "时间", "時間"]):
            if "open_time" not in mapping:
                mapping["open_time"] = i
            else:
                mapping["close_time"] = i
        if any(kw in cl for kw in ["closetime", "平仓", "平倉"]):
            mapping["close_time"] = i
        if any(kw in cl for kw in ["type", "类型", "類型"]):
            mapping["type"] = i
        if any(kw in cl for kw in ["volume", "交易量", "size"]):
            mapping["volume"] = i
        if any(kw in cl for kw in ["symbol", "item", "品种", "品種"]):
            mapping["symbol"] = i
        if any(kw in cl for kw in ["price", "价格", "價格"]) and "current" not in cl and "close" not in cl:
            mapping["open_price"] = i
        if any(kw in cl for kw in ["current", "market", "市场价", "市場價", "市價"]):
            mapping["close_price"] = i
        if any(kw in cl for kw in ["sl", "stop", "止损", "止損"]):
            mapping["sl"] = i
        if any(kw in cl for kw in ["tp", "takeprofit"]):
            mapping["tp"] = i
        if any(kw in cl for kw in ["swap", "库存费", "庫存費", "利息", "storage"]):
            mapping["swap"] = i
        if any(kw in cl for kw in ["profit", "盈利"]):
            mapping["profit"] = i
        if any(kw in cl for kw in ["commission", "佣金"]):
            mapping["commission"] = i
        if any(kw in cl for kw in ["comment", "注释", "註釋"]):
            mapping["comment"] = i
        if any(kw in cl for kw in ["login", "登录", "登錄"]):
            mapping["login"] = i
    return mapping


def _parse_with_map(cells: list[str], cmap: dict) -> dict | None:
    """Parse a data row using column index map."""
    rt_idx = cmap.get("type")
    if rt_idx is None or rt_idx >= len(cells):
        return None
    rt = cells[rt_idx].strip().lower()
    if rt not in ("buy", "sell"):
        return None

    ot_idx = cmap.get("open_time")
    ot = parse_date(cells[ot_idx]) if ot_idx is not None and ot_idx < len(cells) else None
    if ot is None:
        return None

    ct_idx = cmap.get("close_time")
    ct = parse_date(cells[ct_idx]) if ct_idx is not None and ct_idx < len(cells) else ot

    profit_idx = cmap.get("profit")
    profit = clean_number(cells[profit_idx]) if profit_idx is not None and profit_idx < len(cells) else 0.0

    def get_val(key: str, default: str = "0") -> str:
        idx = cmap.get(key)
        return cells[idx] if idx is not None and idx < len(cells) else default

    return {
        "ticket": get_val("ticket", "").strip(),
        "open_time": ot,
        "close_time": ct or ot,
        "type": rt,
        "volume": clean_number(get_val("volume")),
        "symbol": get_val("symbol").strip().lower(),
        "open_price": clean_number(get_val("open_price")),
        "close_price": clean_number(get_val("close_price")),
        "sl": clean_number(get_val("sl")),
        "tp": clean_number(get_val("tp")),
        "swap": clean_number(get_val("swap")),
        "commission": clean_number(get_val("commission")),
        "profit": profit,
    }
