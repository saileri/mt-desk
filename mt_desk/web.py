"""Flask backend — reliable file upload, server-side chart rendering.
Browser only displays <img> tags. Zero JS computation.
"""
from __future__ import annotations
import io, sys, threading, webbrowser, json, traceback
from pathlib import Path
from flask import Flask, request, jsonify

from .parser import parse_statement
from .analysis import analyze
from .charts import (chart_equity, chart_symbol, chart_monthly, chart_winloss,
                     chart_hourly, chart_streaks, chart_equity_overlay, chart_monthly_compare)

PORT = 19799
app = Flask(__name__)
_accounts = []

# ─── API ────────────────────────────────────────────────────────

@app.route("/api/parse", methods=["POST"])
def api_parse():
    f = request.files.get("file")
    if not f: return jsonify({"error": "No file"}), 400
    data = f.read()
    text = data.decode("utf-16-le" if data[:2]==b"\xff\xfe" else "utf-8", errors="replace")
    try:
        from .parser import _detect_and_parse
        result = _detect_and_parse(text, f.filename or "upload")
        if not result["trades"]: return jsonify({"error": "No trades"}), 400
        stats = analyze(result["trades"])
        charts = {"equity": chart_equity(stats), "symbol": chart_symbol(stats),
                  "monthly": chart_monthly(stats), "winloss": chart_winloss(stats),
                  "hourly": chart_hourly(stats), "streaks": chart_streaks(stats)}
        global _accounts
        _accounts = [a for a in _accounts if a["account"]!=result["account"]]
        _accounts.append({"account": result["account"], "file": f.filename,
                          "trades": result["trades"], "stats": stats, "type": result["type"]})
        return jsonify({"account": result["account"], "charts": charts, "stats": stats,
                        "count": len(result["trades"]),
                        "trades": [{"ticket": t["ticket"], "open": str(t["open_time"]),
                                    "close": str(t["close_time"]), "type": t["type"],
                                    "symbol": t["symbol"], "volume": t["volume"],
                                    "profit": t["profit"]} for t in sorted(result["trades"],
                                    key=lambda x: x["profit"], reverse=True)[:200]]})
    except Exception as exc:
        return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500

@app.route("/api/compare")
def api_compare():
    if len(_accounts) < 2: return jsonify({"error": "Need 2+"}), 400
    return jsonify({"charts": {"equity": chart_equity_overlay(_accounts),
                               "monthly": chart_monthly_compare(_accounts)},
                    "accounts": [{"account": a["account"], "stats": a["stats"]} for a in _accounts]})


# ─── Main entry ─────────────────────────────────────────────────
