#!/usr/bin/env bash
# Hebt den Appkern auf den neuesten Stand von GitHub, für Oberfläche und Backend auf denselben Commit: die Oberfläche
# über package-lock.json, das Backend über requirements.txt (Archiv dieses Commits). So baut Docker neu, sobald sich der
# Stand ändert, und beide Seiten passen zusammen (tools/ausrollen.sh prüft das).
#
# Nutzung: tools/appkern.sh
set -euo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HIER/frontend"
npm install --no-audit --no-fund appkern-oberflaeche@github:HalloWelt42/appkern >/dev/null
STAND="$(python3 -c 'import json; print(json.load(open("package-lock.json"))["packages"]["node_modules/appkern-oberflaeche"]["resolved"].rsplit("#", 1)[1])')"
cd "$HIER/backend"
python3 - "$STAND" <<'PYTHON'
import pathlib, re, sys
p = pathlib.Path("requirements.txt")
s = re.sub(r"appkern\[web\] @ https://github\.com/HalloWelt42/appkern/archive/[^\s]+\.tar\.gz",
           f"appkern[web] @ https://github.com/HalloWelt42/appkern/archive/{sys.argv[1]}.tar.gz", p.read_text())
p.write_text(s)
PYTHON
.venv/bin/pip install -q -r requirements.txt
echo "Appkern auf ${STAND:0:7} (Oberfläche und Backend)"
