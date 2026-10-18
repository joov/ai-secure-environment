#!/usr/bin/env python3
"""SOC-Leak-Check: sucht Canary-Marker ausserhalb des Koeder-Verzeichnisses.

Scannt Log-Verzeichnis (Default /logs) rekursiv. Treffer = Alarm, Exit 2.
Schreibt den Bericht nach <logdir>/canary_report.txt (einziger Rueckkanal).
Aufruf: python canary_check.py [logdir]
"""
import json, sys
from pathlib import Path

here = Path(__file__).parent
markers = json.loads((here / "canary" / "markers.json").read_text())["markers"]
logdir = Path(sys.argv[1] if len(sys.argv) > 1 else "/logs")
report = logdir / "canary_report.txt"

hits = []
for f in sorted(logdir.rglob("*")):
    if not f.is_file() or f == report:
        continue
    text = f.read_text(errors="replace")
    for m in markers:
        if m in text:
            hits.append(f"{f}: {m}")

lines = [f"canary_check: {len(markers)} Marker, {len(hits)} Treffer"] + [f"ALARM {h}" for h in hits]
out = "\n".join(lines)
print(out)
try:
    report.write_text(out + "\n")
except OSError:
    pass
sys.exit(2 if hits else 0)
