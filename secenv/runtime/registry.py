#!/usr/bin/env python3
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AGENTS = json.loads(Path(os.environ.get("AGENTS_FILE", "/agents/agents.json")).read_text())
SECRET_ROOT = Path(os.environ.get("SECRET_ROOT", "/secrets"))
TOKENS = {}


def issue():
    for agent in AGENTS:
        token = secrets.token_urlsafe(32)
        dest = SECRET_ROOT / agent["id"]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "token").write_text(token + "\n")
        os.chmod(dest / "token", 0o600)
        TOKENS[token] = agent


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
            self._send(200, {"ok": True, "agents": [a["id"] for a in AGENTS]})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/verify":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        agent = TOKENS.get(body.get("token", ""))
        if not agent or body.get("agent_id") != agent["id"]:
            self._send(401, {"error": "rejected"})
            return
        self._send(200, {"id": agent["id"], "owner": agent["owner"], "task": agent["task"]})


if __name__ == "__main__":
    issue()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
