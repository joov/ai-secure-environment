#!/usr/bin/env python3
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
REQUESTS = {}


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

    def _read(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True})
            return
        if self.path == "/v1/requests":
            with LOCK:
                self._send(200, {"requests": list(REQUESTS.values())})
            return
        if self.path.startswith("/v1/requests/"):
            item = REQUESTS.get(self.path.rsplit("/", 1)[-1])
            self._send(200 if item else 404, item or {"error": "not found"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/v1/requests":
            body = self._read()
            item = {
                "id": uuid.uuid4().hex,
                "agent_id": body.get("agent_id"),
                "action": body.get("action"),
                "status": "pending",
                "created": time.time(),
            }
            with LOCK:
                REQUESTS[item["id"]] = item
            self._send(201, item)
            return
        if self.path.endswith("/decide"):
            req_id = self.path.split("/")[-2]
            body = self._read()
            with LOCK:
                item = REQUESTS.get(req_id)
                if not item or item["status"] != "pending":
                    self._send(404, {"error": "not pending"})
                    return
                item["status"] = "approved" if body.get("approve") else "denied"
            self._send(200, item)
            return
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
