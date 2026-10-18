# Regeln

Stand: 2026-10-18. Quelle ist `authz.rego`. Der Broker fragt `POST /v1/data/secenv/authz/decision`. Was hier nicht steht, ist Deny.

Identität prüft das Register vor OPA. Ein Token gilt nur für die Agent-ID, die dazu gehört. Der Auftrag ist eine Liste von Aktionen, Pfaden, Zielen und Werkzeugen. OPA erlaubt nur die Schnittmenge aus dieser Liste und der technischen Regel. Der Agent kann die Liste nicht erweitern.

| Aktion | Entscheidung | Grund |
|---|---|---|
| `read_file` | Allow | Pfad beginnt mit `/workspace/` und enthält kein `..`. Der Broker prüft das noch einmal. |
| `shell` | Deny | Kein Shell-Werkzeug. |
| `llm_chat` | Allow | Nur ohne Ziel-URL. Der Broker ruft fest `host.docker.internal` und das Modell aus der Umgebung auf. Der Agent wählt das Ziel nicht. |
| `llm_chat` mit URL | Deny | Umleitung auf einen anderen Host ist kein Modellaufruf. |
| `egress` | Freigabe | Timeout oder Ablehnung ist Deny. Der Broker sendet danach nichts. |
| `call_agent` | Allow | Nur `agent-a` an `agent-b`, ohne mitgeschickte Aktion. Der Broker stellt die Nachricht zu, die Container sprechen sich nicht direkt an. |
| `call_agent` mit `delegate` | Deny | Eine mitgeschickte Shell oder andere Aktion ist kein Aufruf. |
| `mcp_call` `ping` | Allow | Nur `agent-a`. Der Broker ruft den Dummy-MCP. Der Server selbst entscheidet nichts. |
| `mcp_call` sonst | Deny | Zum Beispiel `secret_lookup` oder ein Aufruf von `agent-b`. |
| alles andere | Deny | Default. |

Freigabe gilt für diese Anfrage, nicht als Dauerrecht.
