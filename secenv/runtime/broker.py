#!/usr/bin/env python3
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

REGISTRY = os.environ["REGISTRY_URL"].rstrip("/")
OPA = os.environ["OPA_URL"].rstrip("/")
HITL = os.environ["HITL_URL"].rstrip("/")
LEDGER = os.environ["LEDGER_URL"].rstrip("/")
MCP = os.environ.get("MCP_URL", "").rstrip("/")
WORKSPACE = Path(os.environ.get("WORKSPACE", "/workspace"))
TIMEOUT = float(os.environ.get("HITL_TIMEOUT_SEC", "3"))
MLX_UPSTREAM = os.environ.get("MLX_UPSTREAM", "").rstrip("/")
MLX_MODEL = os.environ.get("MLX_MODEL", "")
MLX_API_KEY = os.environ.get("MLX_API_KEY", "")


def post(url, payload, headers=None, timeout=10):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


def get(url):
    with urlopen(url, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode())


def record(entry):
    post(LEDGER + "/v1/entries", entry)


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
            self._send(200, {"ok": True})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/act":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        claimed = body.get("agent_id", "")
        run_id = body.get("run_id") or uuid.uuid4().hex
        try:
            status, agent = post(REGISTRY + "/v1/verify", {"token": token, "agent_id": claimed})
        except Exception:
            status, agent = 401, {}
        if status != 200:
            record({
                "agent_id": claimed,
                "owner": None,
                "task": None,
                "run_id": run_id,
                "action": body.get("action"),
                "decision": "deny",
                "reason": "identity rejected",
            })
            self._send(401, {"decision": "deny", "reason": "identity rejected", "run_id": run_id})
            return
        opa_input = {
            "agent_id": agent["id"],
            "owner": agent["owner"],
            "task": agent["task"],
            "action": body.get("action"),
            "path": body.get("path", ""),
            "url": body.get("url", ""),
            "target": body.get("target", ""),
            "delegate": body.get("delegate", ""),
            "tool": body.get("tool", ""),
        }
        _, opa = post(OPA + "/v1/data/secenv/authz/decision", {"input": opa_input})
        decision = opa.get("result") or {"allow": False, "needs_approval": False, "reason": "default deny"}
        outcome = "deny"
        reason = decision.get("reason", "default deny")
        result = None
        if decision.get("needs_approval"):
            _, pending = post(HITL + "/v1/requests", {"agent_id": agent["id"], "action": body.get("action")})
            deadline = time.time() + TIMEOUT
            approved = False
            while time.time() < deadline:
                _, item = get(HITL + "/v1/requests/" + pending["id"])
                if item.get("status") == "approved":
                    approved = True
                    break
                if item.get("status") == "denied":
                    break
                time.sleep(0.2)
            if not approved:
                reason = "approval timeout or denied"
            else:
                outcome = "allow"
                reason = "approved"
                result = {"sent": False, "note": "egress executor not enabled"}
        elif decision.get("allow") and body.get("action") == "read_file":
            path = Path(body.get("path", ""))
            root = WORKSPACE.resolve()
            try:
                target = path.resolve()
                target.relative_to(root)
                result = {"content": target.read_text()}
                outcome = "allow"
            except Exception:
                reason = "path rejected by broker"
        elif decision.get("allow") and body.get("action") == "llm_chat":
            if body.get("url"):
                reason = "llm url not allowed"
            else:
                headers = {"Authorization": f"Bearer {MLX_API_KEY}"} if MLX_API_KEY else {}
                _, completion = post(
                    MLX_UPSTREAM + "/chat/completions",
                    {
                        "model": MLX_MODEL,
                        "messages": [{"role": "user", "content": body.get("prompt") or "Say hi"}],
                        "max_tokens": 16,
                    },
                    headers,
                    timeout=120,
                )
                result = {"content": completion["choices"][0]["message"]["content"]}
                outcome = "allow"
        elif decision.get("allow") and body.get("action") == "call_agent":
            result = {"delivered": True, "target": body.get("target")}
            outcome = "allow"
        elif decision.get("allow") and body.get("action") == "mcp_call":
            _, result = post(MCP + "/tools/call", {"name": body.get("tool"), "arguments": {}})
            outcome = "allow"
        record({
            "agent_id": agent["id"],
            "owner": agent["owner"],
            "task": agent["task"],
            "run_id": run_id,
            "action": body.get("action"),
            "target": body.get("target"),
            "decision": outcome,
            "reason": reason,
        })
        self._send(200 if outcome == "allow" else 403, {
            "decision": outcome,
            "reason": reason,
            "run_id": run_id,
            "result": result,
        })


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
