# Absicherung von Agenten-Umgebungen, nach Nutzen

Stand: 2026-10-18. Zielbild: Agenten erledigen Arbeitsabläufe, andere Agenten oder Menschen stoßen sie an, der Mensch ist nur noch Human-in-the-Loop. Bewertung gegen diesen Nutzen, nicht gegen einen vollständigen Kontrollkatalog.

Der jetzige secenv-PoC hat die Reihenfolge verkehrt herum begonnen: Gateway, PII-Maskierung und Ledger zuerst, Identität zuletzt. Ohne Identität bleibt jede spätere Kontrolle eine Aussage über einen anonymen Aufrufer.

## 1. Identität des Aufrufers

Höchster Nutzen. Jede andere Kontrolle braucht einen Namen, dem sie die Entscheidung zuordnen kann.

- Jeder Agent hat eine eigene ID, einen Owner und eine Aufgabe, die er nicht selbst erweitern darf.
- Ein Agent kann die ID eines anderen nicht annehmen.
- Der Mensch, der einen Lauf anstößt, bleibt am Lauf hängen (on-behalf-of), auch wenn danach nur noch Agenten arbeiten.

Ohne das sind Keys, Budgets, OPA und das Ledger austauschbar. SPIFFE ist eine mögliche Umsetzung, nicht die Anforderung. Für einen lokalen PoC reicht ein Register plus ein Token, das nur dieser Container hat.

## 2. Default-Deny vor der Wirkung

Zweitwichtigster Nutzen, und der einzige Teil, den der PoC schon belegt. Ein Agent darf eine Wirkung nur auslösen, wenn eine Regel sie vorher erlaubt hat.

- Tool-Calls, Schreiben, Löschen, Shell und Netz gehen durch eine Policy. Default ist Deny.
- Egress nur zu benannten Zielen. Das Netz erzwingt das, nicht nur die Policy.
- Die Prüfung sitzt vor der Wirkung, nicht im Prompt.

Das hält einen kompromittierten Agenten klein, auch wenn das Modell lügt. Intent-Prüfung ("passt das zum Auftrag?") ist dieselbe Stelle, nur mit dem ursprünglichen Auftrag als Input. Ohne sie blockt die Policy Technik, nicht Zweckentfremdung.

## 3. Human-in-the-Loop nur an den wenigen Stellen, die nicht automatisch dürfen

Im Zielbild ist der Mensch nicht der Bearbeiter. Er ist die Freigabe für das, was ein Agent nicht allein entscheiden darf: Geld, externe Wirkung, Rechteänderung, Löschen außerhalb des Workspace, neuer Agent.

- Die Policy nennt diese Aktionen. Alles andere läuft durch.
- Eine Freigabe gilt für diese Aktion und diesen Lauf, nicht als Dauerrecht.
- Ablehnung und Timeout sind Deny, nicht "weitermachen".

Ein Mensch, der jeden Schritt sieht, skaliert nicht. Ein Mensch, der nie gefragt wird, ist kein HITL.

## 4. Zuordenbares Audit

Nutzen erst ab dem Moment, in dem die ID aus Punkt 1 im Eintrag steht. Sonst ist das Ledger ein Protokoll ohne Täter.

- Jede Policy-Entscheidung, jeder Tool-Call, die Freigabe und das Ergebnis, unveränderbar, mit Agent-ID, Owner, Auftrag und Run-ID.
- Prompt und Antwort gehören dazu, sonst ist der Ablauf nicht rekonstruierbar.
- Ein nachträglicher Eingriff muss bei der Prüfung auffallen.

immudb ohne Agent-ID erfüllt die Unveränderbarkeit und verfehlt den Zweck.

## 5. Eigene Keys und Budgets, an die ID gebunden

Nützlich, aber nachrangig. Ein eigener LLM-Key begrenzt Ausgaben und Modellzugriff. Er sagt nicht, wer den Call gemacht hat, wenn der Key geteilt oder gestohlen werden kann.

- Ein Key pro Agent, Budget und erlaubte Modelle daran.
- Der Key wird nur zusammen mit der ID aus Punkt 1 akzeptiert.
- Postgres für LiteLLM-Virtual-Keys ist der Preis dafür, kein Selbstzweck.

Ein gemeinsamer Master-Key plus hartes Default-Deny ist sicherer als viele Keys ohne Identität.

## 6. Daten vor dem Modell und auf dem Rückweg — zweitrangig

Nicht Teil der ersten Testumgebung. Maskierung verhindert, dass Personen und Geheimnisse im Prompt beim Modell landen. Sie ersetzt keine Identität und keine Policy. Erst zuschalten, wenn 1 bis 4 stehen.

- PII-Maskierung (Presidio), vom Aufrufer nicht abschaltbar. Für Deutsch ein passendes Modell, sonst übermaskiert sie.
- Secrets-Scan als Option, nicht als Dienst: ein Aufruf von gitleaks auf Prompt, Tool-Ausgabe und Egress. Kein eigener Container.
- Dieselbe Prüfung auf der Antwort. Nur `pre_call` lässt das Modell den Köder wieder ausgeben.

## 7. Sichtbarkeit von Verstößen

Niedriger, solange 1 bis 4 fehlen. Ein Canary ist dann sinnvoll, wenn ein Alarm einer ID und einem Lauf zugeordnet werden kann.

- Köder-Secrets, die gelesen werden dürfen, aber nie in Egress, Antwort oder Ledger-Inhalt auftauchen dürfen.
- Alarm an den Owner, nicht nur eine Datei, die niemand liest.

## Was sich für dieses Zielbild nicht zuerst lohnt

Mandantentrennung, Modell-Signierung, SBOM und TEE lösen ein anderes Problem: Vertrauen in den Betreiber und das Modell. Sie ändern nichts daran, dass ein Agent ohne ID und ohne Default-Deny einen Arbeitsablauf kaputt oder nach außen tragen kann.

## Reihenfolge, die zum Zielbild passt

1. Agent-Register und nicht fälschbare ID.
2. Default-Deny für Tools und Egress, inklusive Intent gegen den Auftrag.
3. Freigabepflicht für die wenigen externen Wirkungen.
4. Ledger, das diese ID und den Auftrag mitschreibt.
5. Danach eigene LLM-Keys. PII- und Secrets-Maskierung bleiben zweitrangig.

Der bestehende PoC hat 2 und einen Teil von 4 und 6. Er hat 1, 3 und 5 nicht. Dort liegt der Abstand zum Ziel, nicht bei einem weiteren Gateway.

## Docker-Skizze der ersten Testumgebung

Ein Compose-Projekt. Kein LiteLLM, kein Presidio, kein gitleaks. Das Modell bleibt der Host-MLX und ist nicht die Vertrauensgrenze.

Zwei Netze:

- `control`, ohne Egress: Register, Policy, Freigabe, Ledger.
- `agents`, ohne Egress: ein Container pro Agent.

Nur der Broker hängt an beiden und als Einziger an einem dritten Netz `egress`. Agenten erreichen weder den Host noch das Internet.

| Dienst | Rolle | Darf |
|---|---|---|
| `registry` | Vergibt pro Agent eine ID, Owner, Auftrag und ein Token. Das Token liegt in einem Volume, das nur dieser Container sieht. | kein Egress |
| `agent-*` | Ein Container pro Rolle. Read-only, kein Docker-Socket, eigenes Token, gemeinsamer Workspace nur lesend ausser der Broker schreibt. | nur `broker` |
| `broker` | Einziger Prozess, der Tools ausführt und das Modell aufruft. Prüft Token, fragt OPA, holt bei Bedarf Freigabe, schreibt Ledger, dann Wirkung. | `control`, `agents`, `egress` nur zur Allowlist |
| `opa` | Default-Deny. Input ist Agent-ID, Auftrag und die konkrete Aktion. | nur `control` |
| `hitl` | Kleine lokale Freigabe. Timeout und Ablehnung sind Deny. Gilt für Geld, Aussenwirkung, Rechte, Löschen, neuen Agenten. | nur `control`, UI auf `127.0.0.1` |
| `ledger` | immudb. Jeder Eintrag trägt Agent-ID, Owner, Auftrag, Run-ID, Entscheidung, Aktion. | nur `control` |

Der Broker ist die ganze Durchsetzung. Ein Agent, der am Broker vorbei will, hat kein Netz dafür. Ein gefälschtes Token scheitert am Register, weil das Volume nicht geteilt ist.

Zweitrangig, nicht im ersten Compose:

- Presidio vor dem Modell.
- gitleaks als einmaliger Aufruf im Broker, kein Container.
- LiteLLM plus Postgres, wenn eigene Keys an die schon vorhandene ID gebunden werden.

Erster Test, sonst ist die Skizze nichts wert:

1. Agent A ruft ein erlaubtes Lesen auf. Ledger zeigt A und den Auftrag.
2. Agent A ruft Shell oder einen fremden Host auf. OPA lehnt ab, Ledger zeigt A.
3. Agent A legt das Token von B vor. Register lehnt ab.
4. Agent A will nach aussen senden. HITL blockt, Timeout ist Deny, nichts geht raus.
