#!/usr/bin/env python3
"""On-device signing bridge.

Runs frida against a device/emulator where com.dragon.read is installed, loads
hooks/frida_metasec.js, and exposes a tiny HTTP endpoint:

    POST /sign  {"method": "GET", "url": "https://...", "headers": {...}}
      -> {"headers": {"x-gorgon": "...", ...}}

Point the Python client at it:
    FQNOVEL_SIGN_SERVER=http://127.0.0.1:8686/sign python cli.py search --query 斗罗大陆

Requires: pip install frida frida-tools  (and frida-server on the device).
This file is intentionally dependency-optional: it only imports frida when run.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "frida_metasec.js")
TARGET = os.environ.get("FQNOVEL_PACKAGE", "com.dragon.read")


class Handler(BaseHTTPRequestHandler):
    session = None
    script = None

    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):
        if self.path.rstrip("/") != "/sign":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        url = req.get("url", "")
        headers = req.get("headers", {})
        try:
            raw = self.script.exports_sync.sign(url, json.dumps(headers))
            out = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception as exc:  # pragma: no cover - device dependent
            out = {"_error": str(exc)}
        body = json.dumps({"headers": out}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    try:
        import frida
    except ImportError:
        print("frida is not installed. Run: pip install frida frida-tools")
        return 2

    device = frida.get_usb_device(timeout=10)
    session = device.attach(TARGET)
    with open(SCRIPT, "r", encoding="utf-8") as fh:
        script = session.create_script(fh.read())
    script.load()
    Handler.session, Handler.script = session, script
    port = int(os.environ.get("FQNOVEL_BRIDGE_PORT", "8686"))
    print(f"[bridge] signing bridge on http://127.0.0.1:{port}/sign (target {TARGET})")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
