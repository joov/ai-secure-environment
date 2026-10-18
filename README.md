# AI Secure Environment

Lokale Testumgebung für Agenten, die nicht der Nutzer sind. Der Broker ist die einzige Wirkung. OPA entscheidet vorher. Der Auftrag ist eine Liste, keine Formulierung.

## Dokumente

| Datei | Inhalt |
|---|---|
| `ABSICHERUNG.md` | Maßnahmen nach Nutzen, und die Skizze |
| `STATUS.md` | Was davon der laufende Stand erfüllt |
| `PROFESSIONALIZATION.md` | Entra ID, Bifrost, Pflege der Auftragslisten |
| `secenv/policies/REGELN.md` | Die Regeln, die OPA jetzt anwendet |

## Lauf

```bash
scripts/start.sh
scripts/test.sh
scripts/stop.sh
```

`start.sh` startet MLX auf dem Host und danach Compose. Der Test braucht kein Zutun. Eine fehlende Freigabe ist Deny.

| Dienst | Adresse |
|---|---|
| Broker | http://127.0.0.1:8090 |
| Freigabe | http://127.0.0.1:8091 |
| Ledger | http://127.0.0.1:8092 |
| MLX | http://127.0.0.1:8080/v1 |

Agenten haben kein Netz nach draußen. Das Modell und der Dummy-MCP sind nur über den Broker erreichbar. Tokens liegen unter `secenv/secrets/` und gehören nicht ins Git.
