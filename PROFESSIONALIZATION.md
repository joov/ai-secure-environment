# Professionalisierung: Entra ID und Bifrost

Stand: 2026-10-18. Empfehlung, kein Bauplan für den lokalen PoC. Der PoC bleibt die Durchsetzung: Broker fragt OPA, dann Wirkung. Entra ID und Bifrost ersetzen das Register und den nackten MLX-Aufruf, nicht den Broker.

## Entra ID für den Menschen

Der Mensch authentifiziert sich bei Entra ID. Gruppen und App-Rollen sind die Rechte, nicht ein Feld `owner` in `agents.json`.

- Der Broker nimmt nur ein Entra-Token an, das zu dem Lauf gehört, und legt `oid`, Gruppen und Rollen in den OPA-Input.
- Das Agent-Token wird von diesem Login abgeleitet und trägt den Auftrag. Es kann keine Rolle enthalten, die der Mensch nicht hat.
- Entzogene Gruppe oder gesperrter Account beendet den Lauf. Ein lokales Token ohne Ablauf tut das nicht.
- Freigabe geht an den Owner in Entra, nicht an eine offene HTTP-Route auf dem Laptop.

OPA bleibt die Entscheidung. Entra ist die Quelle der Rechte, nicht eine zweite Policy.

## Auftragslisten pflegen

Entra pflegt nicht die Liste der erlaubten Aktionen. Eine Gruppe sagt nur, welche Auftragsvorlage jemand starten darf. Die Vorlage liegt versioniert neben der OPA-Regel: Aktionen, Pfade, Ziele, Werkzeuge. Beim Start bindet das Register eine Kopie an den Lauf. Danach ändert sie niemand, auch der Agent nicht.

Eine neue Vorlage ist eine Änderung an dieser Datei, mit Review. Kein Satz im Prompt und kein Ticket, das die Liste zur Laufzeit erweitert. Der lokale PoC hält dieselbe Form schon in `secenv/agents/agents.json`.

## Bifrost als LLM-Gateway

Bifrost sitzt dort, wo der Broker heute `host.docker.internal` aufruft. Der Agent sieht Bifrost nicht und kein Provider-Secret.

- Ein Virtual Key pro Agent, Budget und Modell-Allowlist, gebunden an die Entra-Identität des Laufs.
- Der Broker sendet diesen Key nur nach OPA-Allow für `llm_chat`. Eine vom Agenten gewählte URL bleibt Deny.
- Audit von Bifrost ergänzt das Ledger, ersetzt es nicht. Das Ledger braucht weiter Agent-ID, Auftrag und die OPA-Entscheidung.
- MCP-Werkzeuge bleiben hinter dem Broker. Bifrosts MCP-Gateway ist ein späterer Kandidat für diese Stelle, nicht ein Bypass.

Entra-SSO von Bifrost Enterprise ist der Weg, Virtual Keys an Nutzer und Gruppen zu hängen. Die Open-Source-Variante kann das Gateway und die Keys. Die Bindung an Entra-Gruppen ist die Enterprise-Funktion. Solange die fehlt, bleibt die Zuordnung Aufgabe des Brokers.

## Reihenfolge

1. Entra-Login und Rechte in den OPA-Input. Damit wird Punkt 1 aus `ABSICHERUNG.md` echt.
2. Bifrost nur für `llm_chat`, ein Virtual Key pro Agent.
3. Freigabe an eine Entra-identifizierte Person.
4. Maskierung und Canary danach, wie bisher zweitrangig.

Nicht tun: Bifrost oder Entra vor den Broker setzen und den Agenten direkt dorthin sprechen lassen. Dann ist die Desktop-Lücke nur umgezogen.
