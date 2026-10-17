# Transkription

Transkription macht aus Ton Text. Eine App auf dem [Appkern](https://github.com/HalloWelt42/appkern): Dateien in der Kellerwolke
(Zweig `Apps/Transkription`), KI nur über die Leitstelle, Anmeldung mit dem Kellerwolke-Konto, gestartet vom Stellwerk.

## Einrichten

```bash
./einrichten.sh
```

Legt die Python-Umgebung an, holt die Pakete der Oberfläche und baut sie. Danach im Stellwerk starten (Eintrag
`stellwerk.toml`) und `http://127.0.0.1:8631` öffnen: die erste Einrichtung fragt nach der Adresse der
Kellerwolke und dem App-Schlüssel (in der Kellerwolke unter Einstellungen, Zugänge). Alles Weitere unter Einstellungen.

## Entwickeln

| Teil | Befehl |
|---|---|
| Backend | `cd backend && .venv/bin/uvicorn app.main:app --port 8631 --reload` |
| Oberfläche | `cd frontend && npm run dev` (Port 9631, leitet `/api` ans Backend) |
| Tests | `cd backend && .venv/bin/python -m pytest` |
| Symbole | `python3 tools/symbole.py` nach einer Änderung an `frontend/public/symbol.svg` |

Der Verbundtest (`tests/test_verbund.py`) spricht mit einer echten Kellerwolke und braucht `backend/.env.test` (nicht
im Repo) mit `KELLERWOLKE_ADRESSE`, `KELLERWOLKE_SCHLUESSEL`, `KELLERWOLKE_KENNUNG`, `KELLERWOLKE_PASSWORT`.

## Aufbau

| Ort | Inhalt |
|---|---|
| `backend/app/main.py` | baut die App auf dem Gerüst |
| `backend/app/einstellungen.py` | eigene Einstellungen (dazu kommen Kellerwolke, Leitstelle, Konten) |
| `backend/app/arten.py` | Arten von Aufträgen |
| `backend/app/api.py` | eigene Endpunkte |
| `frontend/src/App.svelte` | Bereiche der App in der gemeinsamen Schale |
| `frontend/src/seiten/` | Seiten der Bereiche |
