# Status gegen ABSICHERUNG.md

Stand: 2026-10-18. Gemessen am laufenden secenv, nicht an der älteren PoC-Notiz in `ABSICHERUNG.md`. Belegt ist, was `scripts/test.sh` prüft.

| Punkt | Anforderung | Stand | Beleg |
|---|---|---|---|
| 1 Identität | Eigene ID, Owner, Auftrag, Token nur in diesem Container. Fremdes Token scheitert. | Teilweise | `secenv/agents/agents.json`, Volume `secenv/secrets/`, Test 3. Token ist ein Zufallsstring, kein JWT und nicht fälschungsicher signiert. |
| 1 On-behalf-of | Der Mensch bleibt am Lauf hängen. Rechte des Agenten ≤ Rechte des Nutzers. | Offen | `owner` ist ein Etikett. Kein Login, keine Nutzerrechte im OPA-Input. |
| 2 Default-Deny | Wirkung nur nach Regel. Shell, fremdes Netz, falsches Werkzeug abgelehnt. | Erfüllt für die gebauten Aktionen | `secenv/policies/authz.rego`, Tests 1, 2, 6, 8, 10. Netz `agents` hat keinen Egress. |
| 2 Intent | Aufruf muss zum Auftrag passen. | Erfüllt für die Liste | Auftrag in `agents.json` ist eine Liste. Test 11: `llm_chat` von `agent-b` ist technisch bekannt und trotzdem Deny. |
| 3 HITL | Wenige Aktionen brauchen Freigabe. Timeout und Ablehnung sind Deny. | Teilweise | Nur `egress`. Timeout ist Deny, Test 4. Kein getesteter Genehmigungsfall. Fenster 3 Sekunden. Keine UI. |
| 4 Audit | Unveränderbar, mit ID, Owner, Auftrag, Run-ID. Prompt und Antwort dabei. Manipulation fällt auf. | Teilweise | Hash-Kette in `secenv/data/ledger.jsonl`, `GET /v1/verify`. Prompt und Modellantwort fehlen. Kein immudb. Manipulationsversuch nicht getestet. |
| 5 Eigene Keys | Key und Budget pro Agent, nur mit der ID. | Offen | Ein Weg zum Host-MLX. Kein Key pro Agent. |
| 6 Maskierung | PII und Secrets, zweitrangig. | Bewusst offen | Nicht im Compose. |
| 7 Sichtbarkeit | Canary, Alarm an den Owner. | Offen | `secret_lookup` wird vor dem Dummy-MCP abgelehnt. Kein Alarm. |

## Was der Stack jetzt ist

Register, Broker, OPA, Freigabe, Ledger, zwei Harness (`agent-a`, `agent-b`) und ein Dummy-MCP nur hinter dem Broker. Die Harness fragen das Modell und rufen Werkzeuge nur über den Broker auf. Der MCP-Server entscheidet nichts.

Regeln: `secenv/policies/REGELN.md`. Lauf: `scripts/start.sh`, `scripts/stop.sh`, `scripts/test.sh`.

## Abstand

Die Durchsetzung sitzt an der richtigen Stelle. Es fehlt die Bindung an einen echten Nutzer und dessen Rechte. Ohne das bleibt Alice ein Name in einer Datei. Eigene LLM-Keys und Maskierung sind nachrangig und korrekt noch nicht gebaut.
