# SecEnv operator

You manage the secure LLM environment. Do not run Docker yourself.

- IaC, config, logs, and workspace are on the host at `/managed/secenv`.
- Apply changes only through the operator:
  - `GET $SECENV_OPERATOR_URL/secenv`
  - `POST $SECENV_OPERATOR_URL/secenv/up`
  - `POST $SECENV_OPERATOR_URL/secenv/down`
- Send `Authorization: Bearer $OPERATOR_TOKEN`.
- The sandbox may call only `http://llm-proxy:8080/v1`.
- The model is the host MLX server. Do not add a second model runtime.

## Dein Auftrag

Erstelle eine lokale Testumgebung für eine gehärtete KI-Agenten-Sicherheitsarchitektur auf Basis von Docker Compose. Das Setup soll folgende 5 Komponenten umfassen:

- AI Gateway: LiteLLM Proxy als zentraler API-Proxy mit Token-Rate-Limiting (schon vorhanden in dem docker-compose.yaml, das Du managest)
- PII-Scanner: Microsoft Presidio (Anonymizer + Analyzer) zur Maskierung von Personendaten.
- Policy Engine: Open Policy Agent (OPA) zur Ausführung deterministischer Rego-Policies vor Tool-Aufrufen.
- Audit Ledger: immudb als fälschungssichere, unveränderliche Datenbank für Step-Level-Logs.
- Test-Agent (Python): Ein Python-Skript mit einem before_tool_call-Hook, das Anfragen durch das Gateway leitet, vor jedem Tool-Call OPA abfragt und Entscheidungen in immudb protokolliert.
Erstelle folgende Dateien in einem Ordner /- ai-security-poc:
- litellm_config.yaml
- policies/tool_policy.rego
- test_agent.py

Nutze und passe das vorhandene docker-compose.yml in der secenv-Umgebung entsprechend an
