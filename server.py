#!/usr/bin/env python3
"""
Vital Vortex - Local Server
Run this script to start the local server.
Then open http://localhost:8765 in your browser.
"""

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8765
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vitalvortex_data.json")
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Index.html")

DEFAULT_DATA = {
    "foods": [],
    "plan": None,
    "log": {}
}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_DATA)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

class VitalVortexHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Suppress default request logging for cleanliness
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self):
        try:
            with open(HTML_FILE, "r", encoding="utf-8") as f:
                content = f.read().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Index.html.txt not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        action = params.get("action", [None])[0]

        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_html()
            return

        if parsed.path != "/api":
            self.send_response(404)
            self.end_headers()
            return

        data = load_data()

        if action == "read":
            self.send_json({"ok": True, "foods": data.get("foods", [])})

        elif action == "loadplan":
            blob = data.get("plan")
            self.send_json({"ok": True, "blob": blob})

        elif action == "readlog":
            self.send_json({"ok": True, "log": data.get("log", {})})

        else:
            self.send_json({"ok": False, "error": "unknown action: " + str(action)})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_json({"ok": False, "error": "invalid JSON"}, 400)
            return

        action = body.get("action", "")
        data = load_data()

        if action == "write":
            data["foods"] = body.get("foods", [])
            save_data(data)
            self.send_json({"ok": True})

        elif action == "saveplan":
            data["plan"] = body.get("blob")
            save_data(data)
            self.send_json({"ok": True})

        elif action == "log":
            date_key = body.get("date")
            entry = body.get("entry")
            if date_key:
                if "log" not in data:
                    data["log"] = {}
                if entry is None:
                    # null entry = delete this date from the log
                    data["log"].pop(date_key, None)
                else:
                    data["log"][date_key] = entry
                save_data(data)
            self.send_json({"ok": True})

        else:
            self.send_json({"ok": False, "error": "unknown action: " + action})


def open_browser():
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), VitalVortexHandler)
    print(f"")
    print(f"  ✦ Vital Vortex is running!")
    print(f"  → Opening http://localhost:{PORT} in your browser...")
    print(f"")
    print(f"  Keep this window open while using the app.")
    print(f"  Press Ctrl+C to stop the server.")
    print(f"")
    threading.Timer(1.2, open_browser).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped. Goodbye!")
        sys.exit(0)
