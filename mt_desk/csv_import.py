r"""CSV Import Pipeline for MT4/MT5 Trade Data.

Ported from pengfuchao/trading-record-analysis (csv_parser.py + field_mapper.py
+ derived_field_calculator.py + validator.py + symbol_utils.py).

Features:
  - Auto-detect 4 CSV formats: MT4, MT5, Compact English, Chinese MT5
  - Encoding fallback (utf-8 → utf-8-sig → latin-1)
  - Multi-format column normalization (Chinese headers → English)
  - Robust date/number parsing (multiple format fallbacks)
  - Trade row filtering (removes balance/deposit rows)
  - R-Multiple, net PnL, session, asset class computation
  - Per-row validation with error reporting

Usage:
    from mt_desk.csv_import import import_csv
    result = import_csv("path/to/history.csv")
    # result = {
    #   "trades": [{...}],
    #   "detected_platform": "MT4" or "MT5",
    #   "total_rows": N,
    #   "skipped": N,
    #   "errors": [...]
    # }
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
from collections import namedtuple
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("mt_desk.csv_import")

# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class Direction(str, Enum):
    LONG = "Long"
    SHORT = "Short"

class AssetClass(str, Enum):
    FOREX = "Forex"
    GOLD = "Gold"
    SILVER = "Silver"
    OIL = "Oil"
    INDICES = "Indices"
    CRYPTO = "Crypto"
    UNKNOWN = "Unknown"

class TradeResult(str, Enum):
    WIN = "Win"
    LOSS = "Loss"
    BREAKEVEN = "Breakeven"

# ═══════════════════════════════════════════════════════════════════════════════
# Symbol utilities
# ═══════════════════════════════════════════════════════════════════════════════

_BROKER_SUFFIX_PATTERN = re.compile(
    r"[._\-](pro|ecn|raw|std|sb|micro|mini|classic|plus|prime|fix)$",
    re.IGNORECASE,
)

def normalize_symbol(symbol: str) -> str:
    """Strip broker-added suffixes so classification patterns match cleanly."""
    return _BROKER_SUFFIX_PATTERN.sub("", symbol.strip()).upper()

def classify_symbol(symbol: str, rules: dict) -> AssetClass:
    """Match a symbol against ordered regex rules from mt_column_map.yaml."""
    clean = normalize_symbol(symbol)
    for asset_class_name, patterns in rules.items():
        for pattern in patterns:
            if re.match(pattern, clean, re.IGNORECASE):
                try:
                    return AssetClass(asset_class_name.capitalize())
                except ValueError:
                    pass
    return AssetClass.UNKNOWN

# ═══════════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════════

ValidationError = namedtuple("ValidationError", ["trade_id", "field", "message"])

def validate_trade(trade: dict) -> List[ValidationError]:
    """Validate a trade dict and return a list of ValidationErrors. Never raises."""
    errors: List[ValidationError] = []
    tid = trade.get("ticket", "<unknown>")

    if not trade.get("ticket"):
        errors.append(ValidationError(tid, "ticket", "ticket is required"))

    if not trade.get("symbol"):
        errors.append(ValidationError(tid, "symbol", "symbol is required"))

    entry = trade.get("open_time")
    exit_ = trade.get("close_time")
    if entry is None:
        errors.append(ValidationError(tid, "open_time", "open_time is required"))
    if exit_ is None:
        errors.append(ValidationError(tid, "close_time", "close_time is required"))
    if entry is not None and exit_ is not None and exit_ < entry:
        errors.append(
            ValidationError(tid, "close_time",
                            f"close_time {exit_} is before open_time {entry}")
        )

    if trade.get("volume") is not None and trade["volume"] <= 0:
        errors.append(ValidationError(tid, "volume",
                                      f"volume must be > 0, got {trade['volume']}"))

    return errors

# ═══════════════════════════════════════════════════════════════════════════════
# Derived field calculator
# ═══════════════════════════════════════════════════════════════════════════════

_BREAKEVEN_EPSILON = 0.01

def calc_direction(raw_type: Optional[str]) -> Optional[str]:
    """Normalise 'buy'/'sell' to 'Long'/'Short'."""
    if not raw_type:
        return None
    normalized = raw_type.strip().lower()
    if normalized == "buy":
        return "Long"
    if normalized == "sell":
        return "Short"
    return None

def calc_holding_duration(entry: Optional[datetime], exit_: Optional[datetime]) -> Optional[timedelta]:
    if entry is None or exit_ is None:
        return None
    if exit_ < entry:
        return None
    return exit_ - entry

def calc_net_pnl(gross_pnl: Optional[float], commission: Optional[float], swap: Optional[float]) -> Optional[float]:
    """Net PnL = gross_pnl + commission + swap. Commission/swap already signed."""
    if gross_pnl is None:
        return None
    return gross_pnl + (commission or 0.0) + (swap or 0.0)

def calc_result(net_pnl: Optional[float], gross_pnl: Optional[float] = None) -> Optional[str]:
    """Classify trade outcome: Win / Loss / Breakeven."""
    pnl = net_pnl if net_pnl is not None else gross_pnl
    if pnl is None:
        return None
    if pnl > _BREAKEVEN_EPSILON:
        return "Win"
    if pnl < -_BREAKEVEN_EPSILON:
        return "Loss"
    return "Breakeven"

def calc_actual_r(
    exit_price: Optional[float],
    entry_price: Optional[float],
    stop_loss: Optional[float],
    direction: Optional[str],
) -> Optional[float]:
    """Price-based R multiple: how many times risk distance the price moved.

    LONG:  R = (exit_price - entry_price) / abs(entry_price - stop_loss)
    SHORT: R = (entry_price - exit_price) / abs(stop_loss - entry_price)
    """
    if exit_price is None or entry_price is None or not stop_loss or direction is None:
        return None
    sl_distance = abs(entry_price - stop_loss)
    if sl_distance == 0:
        return None
    if direction == "Long":
        return round((exit_price - entry_price) / sl_distance, 2)
    else:
        return round((entry_price - exit_price) / sl_distance, 2)

def calc_asset_class(symbol: Optional[str], rules: dict) -> str:
    if not symbol:
        return "Unknown"
    return classify_symbol(symbol, rules).value

def calc_session(entry_datetime: Optional[datetime], utc_offset: int = 2) -> Optional[str]:
    """Auto-derive trading session from entry datetime hour.

    Normalised to UTC+2 reference:
      Asia         00:00–08:59
      London       09:00–12:59
      London/NY    13:00–16:59
      New York     17:00–20:59
      After Hours  21:00–23:59
    """
    if entry_datetime is None:
        return None
    hour = (entry_datetime.hour - (utc_offset - 2)) % 24
    if hour < 9:
        return "Asia"
    if hour < 13:
        return "London"
    if hour < 17:
        return "London/NY"
    if hour < 21:
        return "New York"
    return "After Hours"

# ═══════════════════════════════════════════════════════════════════════════════
# Field mapper — maps CSV column names to canonical internal field names
# ═══════════════════════════════════════════════════════════════════════════════

# Canonical fields that may appear more than once under the same column name in MT5.
# First occurrence = entry, second = exit.
_MT5_DUPLICATE_COLS = {
    "Time": ("entry_datetime", "exit_datetime"),
    "Price": ("entry_price", "exit_price"),
}

def _load_yaml(path: str) -> dict:
    """Simple YAML loader without pyyaml dependency."""
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

class FieldMapper:
    """Translates a raw CSV row into canonical field names."""

    def __init__(self, platform: str, column_map_path: str) -> None:
        config = _load_yaml(column_map_path)
        platform_key = "mt5" if platform == "MT5" else "mt4"
        self._mapping: Dict[str, str] = config["platforms"][platform_key]
        self._asset_class_rules: dict = config.get("asset_class_rules", {})
        self._platform = platform

    def map_row(self, row: Dict[str, str], df_columns: List[str]) -> Dict[str, Optional[str]]:
        """Map one CSV row to a canonical field dict."""
        result: Dict[str, Optional[str]] = {}

        # Pre-compute positional indices for duplicate column names (MT5 only)
        duplicate_indices: Dict[str, List[int]] = {}
        if self._platform == "MT5":
            for col_name in _MT5_DUPLICATE_COLS:
                indices = [i for i, c in enumerate(df_columns) if c == col_name]
                if indices:
                    duplicate_indices[col_name] = indices

        for canonical_field, source_col in self._mapping.items():
            value = self._resolve_field(
                canonical_field, source_col, row, df_columns, duplicate_indices
            )
            result[canonical_field] = value

        return result

    def _resolve_field(
        self,
        canonical_field: str,
        source_col: str,
        row: Dict[str, str],
        df_columns: List[str],
        duplicate_indices: Dict[str, List[int]],
    ) -> Optional[str]:
        # Handle MT5 duplicate columns by positional index
        if self._platform == "MT5" and source_col in _MT5_DUPLICATE_COLS:
            first_field, second_field = _MT5_DUPLICATE_COLS[source_col]
            indices = duplicate_indices.get(source_col, [])
            if canonical_field == first_field and len(indices) >= 1:
                return self._get_by_index(row, df_columns, indices[0])
            elif canonical_field == second_field and len(indices) >= 2:
                return self._get_by_index(row, df_columns, indices[1])
            else:
                logger.warning(
                    "Duplicate column '%s' not found at expected index for field '%s'",
                    source_col, canonical_field,
                )
                return None

        # Standard lookup by column name
        val = row.get(source_col)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            return None
        return str(val).strip() if hasattr(val, 'strip') else str(val)

    @staticmethod
    def _get_by_index(row: Dict[str, str], df_columns: List[str], index: int) -> Optional[str]:
        """Get value from a row by column index (for duplicate column names)."""
        if index < 0 or index >= len(df_columns):
            return None
        col_name = df_columns[index]
        val = row.get(col_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            return None
        return str(val).strip()

    @property
    def asset_class_rules(self) -> dict:
        return self._asset_class_rules

# ═══════════════════════════════════════════════════════════════════════════════
# CSV parser — format detection, normalization, row parsing
# ═══════════════════════════════════════════════════════════════════════════════

# Column name used to auto-detect platform from CSV headers
_MT5_SENTINEL = "Position"
_MT4_SENTINEL = "Ticket"

# Trade row type values (case-insensitive)
_TRADE_TYPES = {"buy", "sell"}

# MT5 datetime formats to try in order
_DATETIME_FORMATS = [
    "%Y.%m.%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S",
]

# ── Format registry ────────────────────────────────────────────────────────────

# Compact English (MyFXBook / broker compact export)
_COMPACT_EN_SENTINELS = frozenset({"Ticket", "Open", "Close", "SL", "Commissions"})
_COMPACT_EN_SIMPLE_RENAMES = {
    "Open": "Open Time",
    "Close": "Close Time",
    "SL": "S/L",
    "TP": "T/P",
    "Commissions": "Commission",
    "Volume": "Lots",
}
_COMPACT_EN_DUP_RENAMES = [
    ("Price", "Open Price", "Close Price"),
]

# Traditional Chinese MT5 report (FTMO and compatible brokers)
_CHINESE_MT5_SENTINELS = frozenset({"持倉", "交易品種"})
_CHINESE_MT5_SIMPLE_RENAMES = {
    "持倉":   "Position",
    "交易品種": "Symbol",
    "類型":   "Type",
    "交易量":  "Volume",
    "止損":   "S / L",
    "止盈":   "T / P",
    "手續費":  "Commission",
    "隔夜利息": "Swap",
    "盈利":   "Profit",
}
_CHINESE_MT5_DUP_RENAMES = [
    ("時間", "Time", "Time"),
    ("價位", "Price", "Price"),
]

# ── Parsing helpers ────────────────────────────────────────────────────────────

def _parse_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None

def _parse_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        cleaned = str(raw).strip().replace(",", ".").replace(" ", "")
        return float(cleaned)
    except (ValueError, TypeError):
        return None

def _parse_int(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        return None

# ── Format detection ──────────────────────────────────────────────────────────

def _probe_format(file_path: str) -> Tuple[str, int, str]:
    """Peek at the first 12 rows to determine CSV format.

    Returns:
        format_key  — "mt5" | "mt4" | "compact_en" | "chinese_mt5"
        header_row  — 0-based index of the header row
        encoding    — detected encoding
    """
    encodings = ["utf-8", "utf-8-sig", "latin-1"]
    raw_lines: List[str] = []
    used_enc = "utf-8"
    for enc in encodings:
        try:
            with open(file_path, encoding=enc, errors="replace") as fh:
                raw_lines = [fh.readline().rstrip("\n\r") for _ in range(12)]
            used_enc = enc
            break
        except Exception:
            continue

    if not raw_lines:
        return "mt4", 0, "utf-8"

    def _split(line: str) -> List[str]:
        try:
            return [c.strip().strip('"') for c in next(csv.reader(io.StringIO(line)))]
        except Exception:
            return [c.strip().strip('"') for c in line.split(",")]

    for row_idx, line in enumerate(raw_lines):
        cells = _split(line)
        cell_set = set(cells) - {""}

        if _COMPACT_EN_SENTINELS <= cell_set:
            return "compact_en", row_idx, used_enc
        if _CHINESE_MT5_SENTINELS <= cell_set:
            return "chinese_mt5", row_idx, used_enc
        if _MT5_SENTINEL in cell_set:
            return "mt5", row_idx, used_enc
        if _MT4_SENTINEL in cell_set and "Open Time" in cell_set:
            return "mt4", row_idx, used_enc

    return "mt4", 0, used_enc

def _normalize_columns(headers: List[str], format_key: str) -> List[str]:
    """Rename columns for non-standard formats so FieldMapper can handle them."""
    cols = list(headers)
    if format_key == "compact_en":
        # Duplicate renames by position
        for orig, first_new, second_new in _COMPACT_EN_DUP_RENAMES:
            indices = [i for i, c in enumerate(cols) if c == orig]
            if len(indices) >= 1:
                cols[indices[0]] = first_new
            if len(indices) >= 2:
                cols[indices[1]] = second_new
        # Simple renames
        cols = [_COMPACT_EN_SIMPLE_RENAMES.get(c, c) for c in cols]
    elif format_key == "chinese_mt5":
        for orig, first_new, second_new in _CHINESE_MT5_DUP_RENAMES:
            indices = [i for i, c in enumerate(cols) if c == orig]
            if len(indices) >= 1:
                cols[indices[0]] = first_new
            if len(indices) >= 2:
                cols[indices[1]] = second_new
        cols = [_CHINESE_MT5_SIMPLE_RENAMES.get(c, c) for c in cols]
    return cols

# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def import_csv(
    file_path: str,
    column_map_path: Optional[str] = None,
    config_path: Optional[str] = None,
) -> dict:
    """Import an MT4/MT5 CSV file and return parsed trades.

    Returns:
        {
            "trades": [list of trade dicts compatible with mt_desk.analysis],
            "detected_platform": "MT4" or "MT5",
            "total_rows": int (rows in file),
            "trades_parsed": int,
            "skipped": int,
            "errors": [list of error strings],
            "r_multiples": [list of R values for trades that had SL],
            "asset_classes": {symbol: asset_class, ...},
        }
    """
    # Resolve config paths
    if column_map_path is None:
        column_map_path = os.path.join(os.path.dirname(__file__), "config", "mt_column_map.yaml")
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config", "app_config.yaml")

    # Load config
    config = _load_yaml(config_path)
    skip_invalid = config.get("import", {}).get("skip_invalid_rows", True)
    session_cfg = config.get("session_classification", {})
    broker_utc_offset = int(session_cfg.get("broker_utc_offset", 2))

    # Step 1: Detect format and encoding
    format_key, header_row, encoding = _probe_format(file_path)
    logger.info("CSV format=%s, header_row=%d, encoding=%s", format_key, header_row, encoding)

    # Step 2: Read CSV rows
    rows: List[Dict[str, str]] = []
    raw_headers: List[str] = []
    with open(file_path, encoding=encoding, errors="replace") as f:
        reader = csv.reader(f)
        all_rows = list(reader)

    total_rows = len(all_rows)

    # Skip metadata rows before header
    data_rows = all_rows[header_row:]
    if not data_rows:
        return {"trades": [], "detected_platform": "", "total_rows": total_rows,
                "trades_parsed": 0, "skipped": 0, "errors": [], "r_multiples": [],
                "asset_classes": {}}

    raw_headers = [h.strip().strip('"') for h in data_rows[0]]
    logger.info("Raw headers: %s", raw_headers)

    # Step 3: Normalize column names
    # First, strip pandas-style duplicate suffixes (.1, .2) that don't apply here
    normalized_headers = _normalize_columns(raw_headers, format_key)

    # Step 4: Determine platform
    platform = "MT5" if format_key in ("mt5", "chinese_mt5") else "MT4"

    # Step 5: Build dict rows
    for row_data in data_rows[1:]:
        row_dict = {}
        for i, h in enumerate(normalized_headers):
            if i < len(row_data):
                row_dict[h] = row_data[i].strip()
        if row_dict:
            rows.append(row_dict)

    # Step 6: Filter non-trade rows (balance/summary)
    type_values = {r.get("Type", "").strip().lower() for r in rows}
    has_type_col = any(t in _TRADE_TYPES for t in type_values if t)

    if has_type_col:
        trade_rows = [r for r in rows if r.get("Type", "").strip().lower() in _TRADE_TYPES]
        skipped_type = len(rows) - len(trade_rows)
        if skipped_type:
            logger.info("Filtered %d non-trade rows (balance/summary)", skipped_type)
    else:
        trade_rows = rows

    # Step 7: Map fields and compute derived values
    mapper = FieldMapper(platform, column_map_path)
    trades: List[dict] = []
    errors: List[str] = []
    r_multiples: List[float] = []
    asset_classes: Dict[str, str] = {}

    for idx, row in enumerate(trade_rows):
        try:
            raw = mapper.map_row(row, normalized_headers)

            ticket = raw.get("trade_id", "") or f"row_{idx}"
            entry_dt = _parse_datetime(raw.get("entry_datetime"))
            exit_dt = _parse_datetime(raw.get("exit_datetime"))
            entry_price = _parse_float(raw.get("entry_price"))
            exit_price = _parse_float(raw.get("exit_price"))
            stop_loss = _parse_float(raw.get("stop_loss"))
            take_profit = _parse_float(raw.get("take_profit"))
            lot_size = _parse_float(raw.get("volume"))
            commission = _parse_float(raw.get("commission"))
            swap = _parse_float(raw.get("swap"))
            gross_pnl = _parse_float(raw.get("gross_pnl"))
            magic = _parse_int(raw.get("magic"))

            raw_type = raw.get("trade_type")
            direction = calc_direction(raw_type)
            holding_dur = calc_holding_duration(entry_dt, exit_dt)
            net_pnl = calc_net_pnl(gross_pnl, commission, swap)
            result = calc_result(net_pnl, gross_pnl)
            actual_r = calc_actual_r(exit_price, entry_price, stop_loss, direction)
            symbol = raw.get("symbol", "").strip().lower() if raw.get("symbol") else ""
            asset_class = calc_asset_class(symbol, mapper.asset_class_rules)
            session = calc_session(entry_dt, utc_offset=broker_utc_offset)

            # Build mt-desk compatible trade dict
            trade = {
                "ticket": ticket,
                "open_time": entry_dt,
                "close_time": exit_dt or entry_dt,
                "type": raw_type.strip().lower() if raw_type else "",
                "volume": lot_size or 0,
                "symbol": symbol,
                "open_price": entry_price or 0,
                "close_price": exit_price or 0,
                "sl": stop_loss or 0,
                "tp": take_profit or 0,
                "commission": commission or 0,
                "swap": swap or 0,
                "profit": gross_pnl or 0,
                # New fields from derived calculations
                "net_pnl": net_pnl,
                "actual_r": actual_r,
                "direction": direction,
                "result": result,
                "asset_class": asset_class,
                "session": session,
                "holding_duration_seconds": holding_dur.total_seconds() if holding_dur else None,
                "magic": magic,
                "comment": raw.get("comment"),
            }

            # Validate
            val_errors = validate_trade(trade)
            if val_errors:
                if skip_invalid:
                    for ve in val_errors:
                        errors.append(f"Row {idx} (ticket={ticket}): {ve.field} — {ve.message}")
                    logger.warning("Skipping row %d (ticket=%s): validation errors", idx, ticket)
                    continue

            if actual_r is not None:
                r_multiples.append(actual_r)
            if asset_class and symbol:
                asset_classes[symbol.upper()] = asset_class

            trades.append(trade)

        except Exception as exc:
            errors.append(f"Row {idx}: {exc}")
            logger.warning("Failed to parse row %d: %s", idx, exc)

    logger.info("CSV import complete: %d trades, %d skipped, %d errors",
                len(trades), len(trade_rows) - len(trades), len(errors))

    return {
        "trades": trades,
        "detected_platform": platform,
        "total_rows": total_rows,
        "trades_parsed": len(trades),
        "skipped": len(trade_rows) - len(trades),
        "errors": errors,
        "r_multiples": r_multiples,
        "asset_classes": asset_classes,
    }
