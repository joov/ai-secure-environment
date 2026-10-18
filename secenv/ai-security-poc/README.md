# AI-Security-PoC (secenv)

Hardened reference setup for an AI agent: every prompt passes a gateway with PII
masking and token rate limiting, every tool call passes a deterministic policy,
and every decision lands in a tamper-evident ledger.

## Components

| Component | Service | Image | Reachable from |
| --- | --- | --- | --- |
| AI Gateway | `llm-proxy` | `ghcr.io/berriai/litellm:main-stable` | `secenv_internal`, published on `127.0.0.1:${SECENV_PROXY_PORT}` |
| PII scanner | `presidio-analyzer`, `presidio-anonymizer` | `ghcr.io/data-privacy-stack/presidio-*` | `secenv_internal` only |
| Policy engine | `opa` | `openpolicyagent/opa:latest-static` | `secenv_internal` only |
| Audit ledger | `immudb` | `codenotary/immudb:latest` | `secenv_internal` only |
| Test agent | `test-agent` | built from `Dockerfile.agent` | `secenv_internal` only |

The LLM itself runs **outside** this compose project: `mlx_lm.server` on the host
at `127.0.0.1:${MLX_PORT}`, model `${MLX_MODEL}`. Only `llm-proxy` is attached to
`secenv_egress` and may reach it via `host.docker.internal`.

Request path:

```
agent → llm-proxy (LiteLLM) → Presidio guardrail (mask) → MLX on the host
agent → before_tool_call → opa (allow/deny) → immudb (audit) → tool
```

## Files

- `litellm_config.yaml` — one deployment with `rpm`/`tpm` limits, Presidio
  guardrail (`default_on: true`), master key from the environment, no model
  database. `local-mlx` is a `model_group_alias`, not a second deployment, so
  it cannot be used to get a second rate-limit budget.
- `policies/tool_policy.rego` — deny-by-default tool policy, package
  `secenv.tools`, queried at `POST /v1/data/secenv/tools/decision`.
- `policies/tool_policy_test.rego` — unit tests for the policy. They need no
  Docker and no network: `opa test policies/ -v`.
- `test_agent.py` — agent with the `before_tool_call` hook.
- `Dockerfile.agent` / `requirements.txt` — image for the test agent
  (`immudb-py` is the only dependency; everything else is standard library).

## Two gates, not one

A tool call has to pass both:

1. **OPA** judges the call *as written* — tool name, path string, URL host,
   payload size, step budget, PII flags.
2. **The tool implementation** re-checks the resolved path (`contained()` in
   `test_agent.py`). OPA cannot follow symlinks, so a link planted inside the
   workspace pointing at `/etc/passwd` passes the policy; `Path.resolve()`
   catches it. If this gate ever fires, the run is reported as a failure with
   `DENY/executor` and a "policy gap" note, because the policy should have
   caught it first.

The workspace root is pinned in two places that must agree: `workspace_root`
in `tool_policy.rego` and the `WORKSPACE` env var / mount in
`docker-compose.yml`. They are both `/workspace`. If you move the mount without
moving the policy constant, the policy denies every file call — noisy, but
fail-closed.

## Operating

This stack is operated through the operator, which exposes status, up and down —
there is no `compose exec` and no log endpoint:

```bash
curl -H "Authorization: Bearer $OPERATOR_TOKEN" http://operator:3199/secenv        # status
curl -X POST -H "Authorization: Bearer $OPERATOR_TOKEN" http://operator:3199/secenv/up
curl -X POST -H "Authorization: Bearer $OPERATOR_TOKEN" http://operator:3199/secenv/down
```

Because there is no `exec`, the test agent runs the smoke test **once at startup**
and writes its output to `/logs/smoke_test.log`. `./logs` is a bind mount, so the
result is readable from outside the stack — this is the only feedback channel an
up/down-only environment has. The container then stays alive, so where `exec` is
available the interactive runs still work:

```bash
docker compose exec test-agent python /app/test_agent.py
docker compose exec test-agent python /app/test_agent.py --skip-llm
docker compose logs -f llm-proxy
```

The agent prints one line per scenario and exits non-zero if a scenario does not
match its expected allow/deny verdict.

Policy changes should be gated on the unit tests, which run on the host in
about a second and need neither Docker nor a network:

```bash
cd /managed/secenv/ai-security-poc
opa check --strict policies/
opa test policies/ -v
opa fmt --diff policies/
```

Presidio needs roughly half a minute to load its NLP model on first start. Until
it is up, the guardrail call fails and `llm-proxy` returns errors; there are no
healthchecks wired, so give it a moment before concluding something is broken.

## Keys

`LITELLM_MASTER_KEY` is derived in `docker-compose.yml` as `sk-${LOCAL_LLM_API_KEY}` —
LiteLLM requires the `sk-` prefix, so there is no second secret to maintain, and
`sandbox` uses the same derived value. `IMMUDB_ADMIN_PASSWORD` defaults to
`immudb`; set it in `.env` before using this for anything but a local PoC.

## What was verified, and what was not

The stack was started through the operator on 2026-10-18 and is running. All
seven containers came up and stayed up; `immudb`, `presidio-analyzer` and
`presidio-anonymizer` report healthy.

Verified in the running stack (`logs/smoke_test.log`, `EXIT=0`):

- 9 of 9 smoke-test scenarios matched their expected verdict:
  `steps=9  unexpected=0  audit=immudb  ledger_verified=True (12 records)`.
- The LLM call went through the gateway to the local MLX model and came back.
- All four upstream image tags pull and boot.
- `read_only: true` holds for `llm-proxy`, `presidio-*` and `immudb` — no
  service needed the line removed.
- The immudb write path works: `audit=immudb`, so the JSONL fallback was not
  used, and the ledger verified over 12 records.
- The Presidio guardrail is genuinely in the request path — see the finding
  below.

One finding from the live run: **Presidio over-masks German text.** The prompt
"Nenne in einem Satz, was ein Policy-Gate tut." reached the model as "Nenne in
`<PERSON>`, was ein Policy-Gate tut." — `einem Satz` was masked as `PERSON`,
because the analyzer runs its default English NLP engine against German input.
The failure direction is over-masking rather than leakage, so this costs utility,
not safety. Fixing the root cause means giving the analyzer a German spaCy model
and setting the request language to `de`, which needs a custom analyzer image;
that is a scope decision and has not been done.

Earlier, before any container existed, the following was verified with OPA
1.21.2 and CPython 3.13 on the runner itself:

- `opa check --strict policies/` passes and `opa fmt --diff` is clean.
- `opa test policies/` — 36 of 36 unit tests pass.
- `test_agent.py --skip-llm` ran against a real OPA server loaded with this
  policy: 8 of 8 scenarios matched their expected verdict, exit code 0. The
  `before_tool_call` hook queried the policy over HTTP, received the deny
  reasons, and wrote the audit chain.
- The audit hash chain verifies over 11 records, and altering one field of one
  record is detected.
- `contained()` blocks a symlink pointing out of the workspace and admits a
  real file inside it.
- Both YAML files parse; compose declares 7 services, 1 named volume, 2 networks.
- The `immudb-py` 1.5.0 API used here matches the published wheel
  (`login(username, password, database)` accepts `str`; `verifiedSet`/
  `verifiedGet` take `bytes`; `SafeGetResponse` has `.value` and `.verified`).
- The exact OPA server command from `docker-compose.yml` — including
  `--ignore=*_test.rego` — loads only `tool_policy.rego`.

Two defects were found and fixed during this verification; both are now
regression-tested:

- Path containment used a plain `startswith`, so `/workspace-evil/secrets` was
  **allowed**. Containment is now checked on a path-segment boundary.
- `not is_number(input.context.step)` does not fire when the field is absent —
  an undefined operand makes the built-in call undefined and the negated body
  then fails, i.e. it failed *open*. The required-field and `pii_masked` rules
  now resolve the path with `object.get(..., default)` first.

Still not verified, even with the stack running:

- Whether `rpm`/`tpm` actually **reject** the 31st request in a minute rather
  than only influencing load-balancing. The smoke test does not generate enough
  traffic to trigger the limit, so this needs a dedicated load check.
- Presidio's entity coverage beyond the one false positive found above;
  `DATE_TIME` masking in particular is still aggressive.
- The image tags float (`:latest`, `main-stable`). A working combination is now
  known, so they should be pinned to the digests currently running.

Known limitations, by design in a PoC:

- Rate limits are **per deployment**, protecting the upstream MLX server. They
  are not per caller: every client shares the one master key and therefore the
  one budget. Per-caller limits need LiteLLM virtual keys, which need Postgres.
- The old proxy's path allowlist (`/v1/models`, `/v1/chat/completions`) has no
  direct equivalent here — LiteLLM's `allowed_routes` is an enterprise feature.
  Containment is at the network layer instead: the gateway port is bound to
  `127.0.0.1` and every other service sits on the egress-less network.
- The PII pre-check in `test_agent.py` is four regexes, used only to set a flag
  for the policy. The authoritative masking is Presidio in the gateway.

## Rollback

The previous hand-written proxy is untouched: `../Dockerfile.proxy` and
`../proxy/proxy.py`. The compose file as it was before this change is kept at
`../docker-compose.yml.pre-ai-security-poc.bak`.

```bash
cp ../docker-compose.yml.pre-ai-security-poc.bak ../docker-compose.yml
docker compose up -d --build
```
