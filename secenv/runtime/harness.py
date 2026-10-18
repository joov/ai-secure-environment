#!/usr/bin/env python3
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

AGENT_ID = os.environ["AGENT_ID"]
BROKER = os.environ["BROKER_URL"].rstrip("/")
TOOL = os.environ.get("TOOL", "ping")
PROMPT = os.environ.get("PROMPT", "Say hi")
TOKEN_FILE = Path(os.environ.get("TOKEN_FILE", "/secrets/token"))


def token():
    for _ in range(30):
        if TOKEN_FILE.exists() and TOKEN_FILE.read_text().strip():
            return TOKEN_FILE.read_text().strip()
        time.sleep(0.2)
    raise SystemExit("token missing")


def act(auth, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BROKER + "/v1/act",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {auth}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def main():
    auth = token()
    print(f"harness {AGENT_ID} asks the model", flush=True)
    status, llm = act(auth, {
        "agent_id": AGENT_ID,
        "action": "llm_chat",
        "prompt": PROMPT,
        "run_id": f"{AGENT_ID}-llm",
    })
    print("llm", status, json.dumps(llm), flush=True)
    print(f"harness {AGENT_ID} calls mcp tool {TOOL}", flush=True)
    status, tool = act(auth, {
        "agent_id": AGENT_ID,
        "action": "mcp_call",
        "tool": TOOL,
        "run_id": f"{AGENT_ID}-mcp",
    })
    print("mcp", status, json.dumps(tool), flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
