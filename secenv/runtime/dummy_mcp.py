#!/usr/bin/env python3
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOOLS = {
    "ping": lambda _: {"text": "pong"},
    "secret_lookup": lambda _: {"text": "canary-secret"},
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "tools": list(TOOLS)})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/tools/call":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        fn = TOOLS.get(body.get("name", ""))
        if not fn:
            self._send(404, {"error": "unknown tool"})
            return
        self._send(200, fn(body.get("arguments") or {}))


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
