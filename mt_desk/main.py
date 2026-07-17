#!/usr/bin/env python3
"""MT Desk — Flask single-file web app. Server-side charts, browser display only."""
import threading, webbrowser, sys, io, os
from mt_desk.web import app, PORT

# Fix PyInstaller --noconsole: sys.stdout is None → uvicorn/werkzeug crash
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = sys.stdout

# Disable Flask/werkzeug access logs
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# Read embedded index.html
_HTML_PATH = os.path.join(os.path.dirname(__file__), "index.html")
with open(_HTML_PATH, "r", encoding="utf-8") as f:
    app.config["INDEX_HTML"] = f.read()

@app.route("/")
def index():
    return app.config["INDEX_HTML"]

def main():
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)

if __name__ == "__main__":
    main()
