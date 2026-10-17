#!/usr/bin/env python3
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UPSTREAM = os.environ.get("MLX_UPSTREAM", "http://host.docker.internal:8080").rstrip("/")
API_KEY = os.environ["LOCAL_LLM_API_KEY"]
MODEL = os.environ.get("MLX_MODEL", "")
LOG_PATH = os.environ.get("PROXY_LOG", "/logs/proxy.log")
ALLOWED = {"/v1/models", "/v1/chat/completions"}


def log(message):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


PAGE = """<!doctype html>
<meta charset="utf-8">
<title>secenv</title>
<style>
body { font: 14px ui-monospace, monospace; margin: 2rem; background: #111; color: #eee; }
textarea, input, button { font: inherit; width: 100%; box-sizing: border-box; }
pre { white-space: pre-wrap; }
</style>
<h1>secenv</h1>
<p>Local MLX via the allowlisted proxy. Model: __MODEL__</p>
<input id="key" type="password" placeholder="API key">
<textarea id="prompt" rows="6">Say hello in one sentence.</textarea>
<button id="go">Send</button>
<pre id="out"></pre>
<script>
const model = __MODEL_JSON__;
document.getElementById("go").onclick = async () => {
  const res = await fetch("/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + document.getElementById("key").value,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model,
      messages: [{role: "user", content: document.getElementById("prompt").value}]
    })
  });
  document.getElementById("out").textContent = await res.text();
};
</script>
""".replace("__MODEL__", MODEL).replace("__MODEL_JSON__", json.dumps(MODEL))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log("%s %s" % (self.address_string(), fmt % args))

    def _send(self, code, body, content_type="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        if self.headers.get("Authorization") == f"Bearer {API_KEY}":
            return True
        self._send(401, {"error": "unauthorized"})
        return False

    def do_GET(self):
        if self.path in ("/", "/health"):
            if self.path == "/health":
                self._send(200, "ok\n", "text/plain; charset=utf-8")
            else:
                self._send(200, PAGE, "text/html; charset=utf-8")
            return
        if self.path.split("?", 1)[0] not in ALLOWED or not self._authorized():
            if self.path.split("?", 1)[0] not in ALLOWED:
                self._send(403, {"error": "forbidden"})
            return
        self._proxy()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ALLOWED:
            self._send(403, {"error": "forbidden"})
            return
        if not self._authorized():
            return
        self._proxy()

    def _proxy(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length) if length else None
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
        request = Request(UPSTREAM + self.path, data=payload, headers=headers, method=self.command)
        try:
            with urlopen(request, timeout=300) as response:
                body = response.read()
                log(f"{self.command} {self.path} {response.status} {len(body)}")
                self._send(response.status, body, response.headers.get("Content-Type", "application/json"))
        except HTTPError as exc:
            body = exc.read()
            log(f"{self.command} {self.path} {exc.code} {len(body)}")
            self._send(exc.code, body, exc.headers.get("Content-Type", "application/json"))
        except URLError as exc:
            log(f"{self.command} {self.path} upstream {exc}")
            self._send(502, {"error": "upstream unavailable"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
