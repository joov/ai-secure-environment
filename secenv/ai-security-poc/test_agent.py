#!/usr/bin/env python3
"""Test agent for the secenv AI-security PoC.

Every tool call passes through `before_tool_call`, which does three things in a
fixed order:

  1. ask OPA whether the call is allowed (deterministic Rego policy),
  2. write the decision to the immudb audit ledger (tamper-evident, step level),
  3. raise PolicyViolation when the answer is "deny".

LLM traffic goes through the LiteLLM gateway only; the sandbox network has no
egress of its own. The gateway masks PII via Presidio before the prompt reaches
the local MLX model on the host.

Run inside the compose project:

    docker compose exec test-agent python /app/test_agent.py
    docker compose exec test-agent python /app/test_agent.py --prompt "..."
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GATEWAY_BASE = os.environ.get("OPENAI_BASE_URL", "http://llm-proxy:8080/v1").rstrip("/")
GATEWAY_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL_NAME = os.environ.get("MODEL_NAME", "local-mlx")
OPA_URL = os.environ.get("OPA_URL", "http://opa:8181").rstrip("/")
OPA_DECISION_PATH = os.environ.get("OPA_DECISION_PATH", "/v1/data/secenv/tools/decision")
AUDIT_LOG = os.environ.get("AUDIT_LOG", "/logs/agent_audit.log")
WORKSPACE = os.environ.get("WORKSPACE", "/workspace")
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "600"))

# When true, an unreachable or failing ledger aborts the run instead of falling
# back to the local JSONL file. Off by default so the PoC demo still runs
# standalone; a real deployment should set it to 1.
AUDIT_FAIL_CLOSED = os.environ.get("AUDIT_FAIL_CLOSED", "0").lower() in {"1", "true", "yes"}

# Local pre-check only. The authoritative masking happens in the gateway's
# Presidio guardrail; this flag lets the policy refuse a call before it is made.
PII_PATTERNS = {
    "EMAIL_ADDRESS": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "IBAN_CODE": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "PHONE_NUMBER": re.compile(r"\+\d{1,3}[\s-]?\d[\d\s-]{6,}"),
}


class PolicyViolation(RuntimeError):
    """Raised when OPA denies a tool call."""

    def __init__(self, tool: str, reasons: list[str]) -> None:
        super().__init__(f"policy denied {tool!r}: {'; '.join(reasons) or 'no reason given'}")
        self.tool = tool
        self.reasons = reasons


class SandboxEscape(RuntimeError):
    """Raised by a tool implementation when a path leaves the workspace.

    This is the second gate. OPA judges the path *as written*; it cannot follow
    symlinks, so a symlink inside the workspace pointing at /etc would pass the
    policy. Resolving the path here closes that gap. If this ever fires, the
    policy has a hole and the run is treated as a failure.
    """


class AuditUnavailable(RuntimeError):
    """Raised when the ledger cannot record a step and AUDIT_FAIL_CLOSED is set."""


# --------------------------------------------------------------------------- #
# Audit ledger
# --------------------------------------------------------------------------- #


class AuditLedger:
    """immudb-backed step-level audit log.

    Entries are written with verified_set, so a later verified_get proves the
    record has not been altered. When immudb is unreachable the agent keeps a
    local JSONL fallback and marks the run as unverified rather than silently
    dropping audit records.
    """

    def __init__(self) -> None:
        self.run_id = str(uuid.uuid4())
        self.seq = 0
        self.prev_hash = "0" * 64
        self.client: Any = None
        self.backend = "file"
        self.fallback = Path(AUDIT_LOG)
        self._connect()

    def _connect(self) -> None:
        host = os.environ.get("IMMUDB_HOST", "immudb")
        port = os.environ.get("IMMUDB_PORT", "3322")
        try:
            from immudb import ImmudbClient  # type: ignore[import-not-found]

            client = ImmudbClient(f"{host}:{port}")
            client.login(
                username=os.environ.get("IMMUDB_USER", "immudb"),
                password=os.environ.get("IMMUDB_PASSWORD", "immudb"),
                database=os.environ.get("IMMUDB_DATABASE", "defaultdb"),
            )
            self.client = client
            self.backend = "immudb"
        except Exception as exc:  # noqa: BLE001 - handled per AUDIT_FAIL_CLOSED
            if AUDIT_FAIL_CLOSED:
                raise AuditUnavailable(f"immudb unreachable and AUDIT_FAIL_CLOSED is set: {exc!r}") from exc
            print(f"[audit] immudb unavailable ({exc!r}); falling back to {self.fallback}", file=sys.stderr)

    def record(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.seq += 1
        entry = {
            "run_id": self.run_id,
            "seq": self.seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "prev_hash": self.prev_hash,
            **payload,
        }
        # Hash chain, so the file fallback is at least tamper-evident too.
        body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        entry["hash"] = hashlib.sha256((self.prev_hash + body).encode()).hexdigest()
        self.prev_hash = entry["hash"]

        key = f"secenv/{self.run_id}/{self.seq:04d}".encode()
        value = json.dumps(entry, sort_keys=True).encode()
        if self.client is not None:
            try:
                self.client.verifiedSet(key, value)
            except Exception as exc:  # noqa: BLE001
                if AUDIT_FAIL_CLOSED:
                    raise AuditUnavailable(f"ledger write failed and AUDIT_FAIL_CLOSED is set: {exc!r}") from exc
                print(f"[audit] immudb write failed ({exc!r}); using file fallback", file=sys.stderr)
                self.client = None
                self.backend = "file"
        if self.client is None:
            self.fallback.parent.mkdir(parents=True, exist_ok=True)
            with self.fallback.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    @staticmethod
    def _entry_hash(entry: dict[str, Any]) -> str:
        """Recompute the hash of a record exactly as record() produced it."""
        unhashed = {k: v for k, v in entry.items() if k != "hash"}
        body = json.dumps(unhashed, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256((unhashed["prev_hash"] + body).encode()).hexdigest()

    def verify_chain(self) -> tuple[bool, int, list[str]]:
        """Read every record of this run back and re-verify it.

        Two independent checks: immudb's own inclusion proof (verifiedGet), and
        our hash chain, which also proves ordering and that no step was dropped
        from the middle of the run.
        """
        problems: list[str] = []
        if self.client is None:
            return False, 0, ["no immudb connection; records are in the file fallback only"]

        prev = "0" * 64
        checked = 0
        for seq in range(1, self.seq + 1):
            key = f"secenv/{self.run_id}/{seq:04d}".encode()
            try:
                stored = self.client.verifiedGet(key)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"seq {seq}: verifiedGet failed: {exc!r}")
                continue
            if getattr(stored, "verified", False) is not True:
                problems.append(f"seq {seq}: immudb reported the record as unverified")
            entry = json.loads(stored.value.decode())
            if entry.get("prev_hash") != prev:
                problems.append(f"seq {seq}: prev_hash does not match the previous record")
            recomputed = self._entry_hash(entry)
            if entry.get("hash") != recomputed:
                problems.append(f"seq {seq}: content hash mismatch — record was altered")
            prev = entry.get("hash", "")
            checked += 1
        return not problems, checked, problems


# --------------------------------------------------------------------------- #
# Policy engine
# --------------------------------------------------------------------------- #


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode())


def contained(path: str, root: str = WORKSPACE) -> Path:
    """Resolve `path` and confirm it is still inside `root`.

    Defence in depth behind the OPA policy: resolve() follows symlinks, so a
    link planted inside the workspace cannot be used to read outside it.
    """
    resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise SandboxEscape(f"{path!r} resolves to {str(resolved)!r}, outside {str(root_resolved)!r}")
    return resolved


def detect_pii(text: str) -> list[str]:
    return sorted(name for name, pattern in PII_PATTERNS.items() if pattern.search(text))


def ask_policy(tool: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Query OPA. A policy engine that cannot be reached is a deny, not a pass."""
    try:
        result = _post_json(
            OPA_URL + OPA_DECISION_PATH,
            {"input": {"tool": tool, "arguments": arguments, "context": context}},
        )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"allow": False, "reasons": [f"policy engine unreachable: {exc!r}"], "tool": tool}
    decision = result.get("result")
    if not isinstance(decision, dict):
        return {"allow": False, "reasons": ["policy returned no decision"], "tool": tool}
    return decision


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #


@dataclass
class Agent:
    ledger: AuditLedger
    step: int = 0
    tools: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def tool(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = func
            return func

        return register

    # --- the hook ----------------------------------------------------------- #

    def before_tool_call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.step += 1
        serialized = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        pii = detect_pii(serialized)
        context = {
            "step": self.step,
            "run_id": self.ledger.run_id,
            "payload_bytes": len(serialized.encode()),
            "pii_detected": bool(pii),
            # The gateway guardrail masks prompts; nothing else is masked here.
            "pii_masked": tool == "llm_chat",
        }
        started = time.monotonic()
        decision = ask_policy(tool, arguments, context)
        self.ledger.record(
            "tool_decision",
            {
                "tool": tool,
                "arguments": arguments,
                "context": context,
                "pii_entities": pii,
                "decision": decision,
                "policy_latency_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        if not decision.get("allow"):
            raise PolicyViolation(tool, list(decision.get("reasons", [])))
        return decision

    def call_tool(self, tool: str, **arguments: Any) -> Any:
        self.before_tool_call(tool, arguments)
        handler = self.tools.get(tool)
        if handler is None:
            raise PolicyViolation(tool, ["tool allowed by policy but not implemented"])
        try:
            result = handler(**arguments)
        except Exception as exc:  # noqa: BLE001 - failures are audited, then re-raised
            self.ledger.record("tool_error", {"tool": tool, "error": repr(exc)})
            raise
        self.ledger.record(
            "tool_result",
            {"tool": tool, "result_preview": str(result)[:500], "result_bytes": len(str(result).encode())},
        )
        return result


def build_agent(ledger: AuditLedger) -> Agent:
    agent = Agent(ledger=ledger)

    @agent.tool("llm_chat")
    def llm_chat(prompt: str, max_tokens: int = 256) -> str:
        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        response = _post_json(
            GATEWAY_BASE + "/chat/completions",
            payload,
            {"Authorization": f"Bearer {GATEWAY_KEY}"},
        )
        return response["choices"][0]["message"]["content"]

    @agent.tool("read_file")
    def read_file(path: str) -> str:
        return contained(path).read_text(encoding="utf-8")[:4096]

    @agent.tool("list_dir")
    def list_dir(path: str) -> list[str]:
        return sorted(entry.name for entry in contained(path).iterdir())

    @agent.tool("http_get")
    def http_get(url: str) -> str:
        with urlopen(Request(url, method="GET"), timeout=HTTP_TIMEOUT) as response:
            return response.read().decode()[:4096]

    @agent.tool("shell_exec")
    def shell_exec(command: str) -> str:
        # Registered on purpose: the policy must be what stops it, not its absence.
        raise AssertionError("shell_exec must never be reached — OPA denies it")

    return agent


# --------------------------------------------------------------------------- #
# Demo run
# --------------------------------------------------------------------------- #


def scenarios(prompt: str) -> list[tuple[str, str, dict[str, Any], bool]]:
    """(label, tool, arguments, expected_allow)"""
    return [
        ("LLM call through the gateway", "llm_chat", {"prompt": prompt, "max_tokens": 128}, True),
        ("Read inside the workspace", "list_dir", {"path": WORKSPACE}, True),
        ("Read outside the workspace", "read_file", {"path": "/etc/passwd"}, False),
        ("Path traversal", "read_file", {"path": f"{WORKSPACE}/../etc/shadow"}, False),
        # Regression: a prefix-only containment check accepted this sibling path.
        ("Sibling directory with a shared prefix", "read_file", {"path": f"{WORKSPACE}-evil/secrets"}, False),
        ("Shell execution", "shell_exec", {"command": "id"}, False),
        ("Egress to an unlisted host", "http_get", {"url": "https://example.com/data"}, False),
        ("Host spoofed via URL credentials", "http_get", {"url": "https://llm-proxy@example.com/x"}, False),
        (
            "Unmasked PII in a non-LLM tool",
            "read_file",
            {"path": f"{WORKSPACE}/notes.txt", "note": "contact erika.musterfrau@example.de"},
            False,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="secenv AI-security PoC test agent")
    parser.add_argument("--prompt", default="Nenne in einem Satz, was ein Policy-Gate tut.")
    parser.add_argument("--skip-llm", action="store_true", help="run only the policy scenarios")
    args = parser.parse_args()

    ledger = AuditLedger()
    agent = build_agent(ledger)
    ledger.record("run_start", {"model": MODEL_NAME, "gateway": GATEWAY_BASE, "opa": OPA_URL})

    print(f"run_id={ledger.run_id}  audit_backend={ledger.backend}\n")
    failures = 0
    for label, tool, arguments, expected_allow in scenarios(args.prompt):
        if tool == "llm_chat" and args.skip_llm:
            continue
        escaped = False
        try:
            result = agent.call_tool(tool, **arguments)
            allowed, verdict, detail = True, "ALLOW", str(result).strip().replace("\n", " ")[:120]
        except PolicyViolation as exc:
            allowed, verdict, detail = False, "DENY/policy", "; ".join(exc.reasons)
        except SandboxEscape as exc:
            # The policy let this through and only the executor stopped it.
            allowed, verdict, detail, escaped = False, "DENY/executor", str(exc), True
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            allowed, verdict, detail = True, "ALLOW", f"allowed by policy, execution failed: {exc!r}"

        # A policy gap is a failure even when the expected verdict matched.
        ok = allowed == expected_allow and not escaped
        failures += 0 if ok else 1
        print(f"[{'ok  ' if ok else 'FAIL'}] {verdict:<13} {label}\n         {detail}")
        if escaped:
            print("         ^ policy gap: this should have been denied by OPA, not by the executor")

    chain_ok, checked, problems = ledger.verify_chain()
    ledger.record("run_end", {"failures": failures, "steps": agent.step})
    print(
        f"\nsteps={agent.step}  unexpected={failures}  audit={ledger.backend}  "
        f"ledger_verified={chain_ok} ({checked} records)"
    )
    for problem in problems:
        print(f"  ledger: {problem}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
