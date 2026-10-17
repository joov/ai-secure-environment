#!/usr/bin/env python3
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOST_ROOT = os.environ["HOST_ROOT"]
TOKEN = os.environ["OPERATOR_TOKEN"]
LOG_PATH = os.environ.get("OPERATOR_LOG", "/logs/operator.log")
SECENV = os.path.join(HOST_ROOT, "secenv")
COMPOSE = os.path.join(SECENV, "docker-compose.yml")
ENV_FILE = os.path.join(SECENV, ".env")
LOCK = threading.Lock()


def log(message):
    line = message.rstrip() + "\n"
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(line)
    print(line, end="", flush=True)


def compose(*args):
    cmd = [
        "docker",
        "compose",
        "--project-name",
        "secenv",
        "--project-directory",
        SECENV,
        "--env-file",
        ENV_FILE,
        "-f",
        COMPOSE,
        *args,
    ]
    log("run " + " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log("%s - %s" % (self.address_string(), fmt % args))

    def _send(self, code, body, content_type="application/json"):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body)
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        if self.headers.get("Authorization") == f"Bearer {TOKEN}":
            return True
        self._send(401, {"error": "unauthorized"})
        return False

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, "ok\n", "text/plain; charset=utf-8")
            return
        if not self._authorized():
            return
        if path != "/secenv":
            self._send(404, {"error": "not found"})
            return
        with LOCK:
            result = compose("ps", "--format", "json")
        self._send(
            200 if result.returncode == 0 else 500,
            {"code": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
        )

    def do_POST(self):
        if not self._authorized():
            return
        path = urlparse(self.path).path
        actions = {
            "/secenv/up": ["up", "-d", "--build", "--remove-orphans"],
            "/secenv/down": ["down", "--remove-orphans"],
        }
        if path not in actions:
            self._send(404, {"error": "not found"})
            return
        with LOCK:
            result = compose(*actions[path])
        self._send(
            200 if result.returncode == 0 else 500,
            {"code": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
        )


def main():
    if os.environ.get("MANAGE_ON_BOOT") == "1":
        try:
            with LOCK:
                result = compose("up", "-d", "--build", "--remove-orphans")
            if result.returncode != 0:
                log(result.stderr)
        except Exception as exc:
            log(f"boot failed: {exc}")
    ThreadingHTTPServer(("0.0.0.0", 3199), Handler).serve_forever()


if __name__ == "__main__":
    main()
