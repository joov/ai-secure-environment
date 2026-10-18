#!/usr/bin/env python3
import hashlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PATH = Path(os.environ.get("LEDGER_FILE", "/data/ledger.jsonl"))
LOCK = threading.Lock()


def canonical(entry):
    return json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()


def load():
    if not PATH.exists():
        return []
    rows = []
    for line in PATH.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def verify(rows):
    prev = "0" * 64
    for row in rows:
        expect = hashlib.sha256(prev.encode() + canonical(row["entry"])).hexdigest()
        if row.get("prev") != prev or row.get("hash") != expect:
            return False
        prev = expect
    return True


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
        rows = load()
        if self.path == "/health":
            self._send(200, {"ok": True})
            return
        if self.path == "/v1/entries":
            self._send(200, {"entries": rows})
            return
        if self.path == "/v1/verify":
            self._send(200, {"ok": verify(rows), "count": len(rows)})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/entries":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        entry = json.loads(self.rfile.read(length) or b"{}")
        with LOCK:
            rows = load()
            prev = rows[-1]["hash"] if rows else "0" * 64
            digest = hashlib.sha256(prev.encode() + canonical(entry)).hexdigest()
            row = {"seq": len(rows) + 1, "prev": prev, "hash": digest, "entry": entry}
            PATH.parent.mkdir(parents=True, exist_ok=True)
            with PATH.open("a") as handle:
                handle.write(json.dumps(row) + "\n")
        self._send(201, row)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
