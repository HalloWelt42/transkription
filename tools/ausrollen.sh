#!/usr/bin/env bash
# Ausrollen auf den Pi (vom Mac aus). Prüft bei jedem Neubau alles selbst und bricht beim ersten Fehler ab:
#   1. nur gepushte Stände, Tests hier grün
#   2. auf dem Pi: ffmpeg und ffprobe vorhanden und lauffähig (sie kommen nicht in den Container), Lader und
#      Bibliotheken da, Docker mit Compose da
#   3. Zertifikat der Hausstelle für HTTPS vorhanden und noch mindestens 60 Tage gültig, sonst neu ausstellen
#   4. Stand holen, Datenbank sichern (die letzten zehn Sicherungen bleiben)
#   5. Abbild bauen und starten
#   6. im Container eine echte Umwandlung mit dem ffmpeg des Pi; über HTTPS melden Server, gebaute Oberfläche und
#      version.json dieselbe Fassung
#
# Nutzung: tools/ausrollen.sh
set -euo pipefail
PI="${TRANSKRIPTION_PI:-pi@192.168.178.49}"
WURZEL="${TRANSKRIPTION_PI_WURZEL:-/mnt/data/transkription}"
ADRESSE="${TRANSKRIPTION_ADRESSE:-https://192.168.178.49:8631}"
REPO="https://github.com/HalloWelt42/transkription.git"
NAMEN="192.168.178.49 raspberrypi-3.fritz.box raspberrypi-3 transkription.fritz.box transkription.local"
SCHWELLE_S=$((60 * 86400))
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HIER"
schritt() { printf '\n== %s\n' "$1"; }

schritt "Stand und Tests"
[ -z "$(git status --porcelain)" ] || { echo "Erst committen."; exit 1; }
git fetch -q origin
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "Erst pushen (main ist nicht auf origin)."; exit 1; }
(cd backend && set -o pipefail && .venv/bin/python -m pytest -q 2>&1 | tail -1)

schritt "Pi prüfen"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI" 'set -e
  for p in ffmpeg ffprobe; do
    command -v "$p" >/dev/null || { echo "$p fehlt auf dem Pi (sudo apt install ffmpeg)"; exit 1; }
    "$p" -hide_banner -version >/dev/null || { echo "$p startet nicht"; exit 1; }
  done
  test -x /usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1 || { echo "Lader /usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1 fehlt"; exit 1; }
  docker compose version >/dev/null || { echo "Docker Compose fehlt"; exit 1; }
  echo "ffmpeg: $(ffmpeg -hide_banner -version | head -1)"
  echo "Docker: $(docker --version)"'

schritt "Zertifikat"
if ssh -o BatchMode=yes "$PI" "test -f '$WURZEL/zertifikate/transkription.pem' && openssl x509 -in '$WURZEL/zertifikate/transkription.pem' -noout -checkend $SCHWELLE_S" >/dev/null 2>&1; then
  echo "vorhanden, noch mindestens 60 Tage gültig"
else
  command -v mkcert >/dev/null || { echo "mkcert fehlt auf diesem Mac"; exit 1; }
  HAUSSTELLE="$(mkcert -CAROOT)/rootCA.pem"
  [ -f "$HAUSSTELLE" ] || { echo "Die Hausstelle fehlt: $HAUSSTELLE"; exit 1; }
  ARBEIT="$(mktemp -d)"
  trap 'rm -rf "$ARBEIT"' EXIT
  # shellcheck disable=SC2086 - die Namen sind eine Liste
  (cd "$ARBEIT" && mkcert -cert-file transkription.pem -key-file transkription-schluessel.pem $NAMEN >/dev/null 2>&1)
  cp "$HAUSSTELLE" "$ARBEIT/rootCA.pem"
  ssh -o BatchMode=yes "$PI" "mkdir -p '$WURZEL/zertifikate'"
  scp -q "$ARBEIT/transkription.pem" "$ARBEIT/transkription-schluessel.pem" "$ARBEIT/rootCA.pem" "$PI:$WURZEL/zertifikate/"
  ssh -o BatchMode=yes "$PI" "chmod 644 '$WURZEL/zertifikate/transkription.pem' '$WURZEL/zertifikate/rootCA.pem' && chmod 640 '$WURZEL/zertifikate/transkription-schluessel.pem'"
  echo "ausgestellt, gültig bis $(openssl x509 -in "$ARBEIT/transkription.pem" -noout -enddate | sed 's/^.*=//')"
fi

schritt "Stand holen und Datenbank sichern"
ssh -o BatchMode=yes "$PI" "set -e
  mkdir -p '$WURZEL'
  cd '$WURZEL'
  if [ ! -d .git ]; then git clone -q '$REPO' /tmp/transkription-klon && cp -a /tmp/transkription-klon/. . && rm -rf /tmp/transkription-klon; fi
  git pull --ff-only -q
  mkdir -p daten sicherungen
  if [ -f daten/transkription.sqlite ]; then
    ziel=sicherungen/transkription-\$(date +%Y%m%d-%H%M%S).sqlite
    python3 -c 'import sqlite3, sys; q = sqlite3.connect(sys.argv[1]); z = sqlite3.connect(sys.argv[2]); q.backup(z); z.close(); q.close()' daten/transkription.sqlite \"\$ziel\"
    echo \"gesichert: \$ziel\"
    ls -1t sicherungen/transkription-*.sqlite | tail -n +11 | xargs -r rm --
  else
    echo 'noch keine Datenbank'
  fi
  echo \"Stand: \$(git log --oneline -1)\""

schritt "Bauen und starten"
ssh -o BatchMode=yes "$PI" "cd '$WURZEL' && docker compose -f compose.pi.yml build --quiet && docker compose -f compose.pi.yml up -d --remove-orphans"

schritt "Prüfen"
ssh -o BatchMode=yes "$PI" "cd '$WURZEL' && for i in \$(seq 1 30); do curl -sf --cacert zertifikate/rootCA.pem '$ADRESSE/api/v1/app' >/dev/null && break; sleep 2; done
  docker compose -f compose.pi.yml exec -T transkription sh -c 'ffmpeg -nostdin -hide_banner -loglevel error -f lavfi -i sine=frequency=440:duration=1 -ac 1 -ar 16000 -y /tmp/probe.wav && ffprobe -v error -show_entries format=duration -of csv=p=0 /tmp/probe.wav' | sed 's/^/Umwandlung im Container mit dem ffmpeg des Pi, Dauer: /'"
INFO="$(ssh -o BatchMode=yes "$PI" "curl -sf --cacert '$WURZEL/zertifikate/rootCA.pem' '$ADRESSE/api/v1/app'")"
FASSUNG="$(python3 -c 'import json; print(json.load(open("version.json"))["version"])')"
python3 - "$INFO" "$FASSUNG" <<'PRUEFUNG'
import json, sys
info, fassung = json.loads(sys.argv[1]), sys.argv[2]
print(f"Server {info['fassung']}, Oberfläche {info.get('oberflaeche')}, version.json {fassung}, Appkern {info['appkern']}")
assert info["fassung"] == fassung == info.get("oberflaeche"), "Fassungen passen nicht zusammen"
PRUEFUNG
echo
echo "Transkription ausgerollt: $ADRESSE"
