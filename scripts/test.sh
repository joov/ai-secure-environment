#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
load_env

token_a="$(tr -d '\n' <"$SECENV_DIR/secrets/agent-a/token")"
token_b="$(tr -d '\n' <"$SECENV_DIR/secrets/agent-b/token")"
broker="http://127.0.0.1:${BROKER_PORT}"
ledger="http://127.0.0.1:${LEDGER_PORT}"

act() {
  local token="$1" payload="$2"
  curl -sS -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" \
    -d "$payload" "$broker/v1/act"
}

echo "==> 1 read"
act "$token_a" '{"agent_id":"agent-a","action":"read_file","path":"/workspace/notes.txt","run_id":"t1"}' | grep -q '"decision": "allow"'
echo "==> 2 shell"
act "$token_a" '{"agent_id":"agent-a","action":"shell","path":"/bin/sh","run_id":"t2"}' | grep -q '"decision": "deny"'
echo "==> 3 forged token"
act "$token_b" '{"agent_id":"agent-a","action":"read_file","path":"/workspace/notes.txt","run_id":"t3"}' | grep -q 'identity rejected'
echo "==> 4 egress timeout"
act "$token_a" '{"agent_id":"agent-a","action":"egress","url":"http://example.com","run_id":"t4"}' | grep -q 'approval timeout or denied'
echo "==> 5 llm allow"
act "$token_a" '{"agent_id":"agent-a","action":"llm_chat","prompt":"Say hi","run_id":"t5"}' | grep -q '"decision": "allow"'
echo "==> 6 llm deny"
act "$token_a" '{"agent_id":"agent-a","action":"llm_chat","url":"http://example.com","run_id":"t6"}' | grep -q 'llm url not allowed'
echo "==> 7 call agent-b allow"
act "$token_a" '{"agent_id":"agent-a","action":"call_agent","target":"agent-b","run_id":"t7"}' | grep -q '"decision": "allow"'
echo "==> 8 call agent-b deny"
act "$token_a" '{"agent_id":"agent-a","action":"call_agent","target":"agent-b","delegate":"shell","run_id":"t8"}' | grep -q 'delegate not allowed'
echo "==> 9 mcp ping allow"
act "$token_a" '{"agent_id":"agent-a","action":"mcp_call","tool":"ping","run_id":"t9"}' | grep -q '"text": "pong"'
echo "==> 10 mcp secret deny"
act "$token_a" '{"agent_id":"agent-a","action":"mcp_call","tool":"secret_lookup","run_id":"t10"}' | grep -q 'outside task'
echo "==> 11 outside task"
act "$token_b" '{"agent_id":"agent-b","action":"llm_chat","prompt":"Say hi","run_id":"t11"}' | grep -q 'outside task'
echo "==> ledger"
curl -fsS "$ledger/v1/verify" | grep -q '"ok": true'
curl -fsS "$ledger/v1/entries" | grep -q 'agent-a'
echo "ok"
