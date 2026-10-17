#!/usr/bin/env bash
# Ausrollen auf diesem Rechner (Stellwerk): nur gepushte Stände, Tests grün, Oberfläche neu bauen, Backend neu starten,
# danach prüfen, dass Server und gebaute Oberfläche dieselbe Fassung melden.
set -euo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HIER"
[ -z "$(git status --porcelain)" ] || { echo "Erst committen."; exit 1; }
git fetch -q origin
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "Erst pushen (main ist nicht auf origin)."; exit 1; }
(cd backend && .venv/bin/python -m pip install -q -r requirements.txt && .venv/bin/python -m pytest -q)
(cd frontend && npm install --no-audit --no-fund --silent && npm run build --silent)
curl -sf -X POST -H "X-Stellwerk: 1" http://127.0.0.1:8550/api/apps/transkription/neustarten >/dev/null
sleep 4
python3 - <<'PRUEFUNG'
import json, urllib.request
info = json.load(urllib.request.urlopen("http://127.0.0.1:8631/api/v1/app", timeout=10))
fassung = json.load(open("version.json"))["version"]
print(f"Server {info['fassung']}, Oberfläche {info.get('oberflaeche')}, version.json {fassung}")
assert info["fassung"] == fassung == info.get("oberflaeche"), "Fassungen passen nicht zusammen"
PRUEFUNG
echo "Transkription ausgerollt."
