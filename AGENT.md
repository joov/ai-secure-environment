# Ziel der Umgebung

## Rolle
Du bist ein Sec-Engineern mit Erfahrung in Docker und lokalem LLM-Deployment auf dem Mac

## Tätigkeiten

Du entwirfst eine Testumgebung für sichere LLM-Nutzung lokal auf dem Mac. 

Die Umgebung besteht aus den folgenden Komponenten

- Eine Paperclip-Instanz, die das eigentliche Management der Sicheren Umgebung macht. Erstellen einschließlich Betrieb. Diese soll in Docker-Compose laufen. Gerne im Verzeichnis "paperclip"
- Die eigentliche sicherere LLM-Umgebung. Diese soll auch in Docker-Compose laufen, Side-by-side mit der Paperclip-Instanz und von dieser verwaltet werden. Die Mounts sollen so sein, dass ich außerhalb der docker-compose-umgebungen alle IaC, Logs und Konfigurationen sehen kann. Gerne im Verzeichnis "secenv"
- das LLM, das lokal unter mlx auf dem apple laufen soll. Ich habe das gewünschte qwen-modell bereits per mlx_lm.server installiert.

Das lokale LLM soll sowohl das Backend für Paperclip sein, als auch in der sicheren LLM-Umgebung verfügbar sein und genutzt werden. 

## Zusatz

ich hätte gerne ein shell-script, mit dem ich alles starten und stoppen kann (evtl. 2 scripts)