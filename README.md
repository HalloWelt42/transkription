# Transkription

Transkription macht aus Ton und Video Text mit Wortzeiten und Sprechern. Eine App auf dem
[Appkern](https://github.com/HalloWelt42/appkern): Dateien in der Kellerwolke (Zweig `Apps/Transkription`), KI nur über
die Leitstelle (Hören, Stimmabdrücke und Sprechertrennung aus dem Klangwerk, Sprachmodell für Korrektur und
Auswertung), Anmeldung mit dem Kellerwolke-Konto, gestartet vom Stellwerk.

## Was sie kann

| Bereich | Inhalt |
|---|---|
| Aufnahmen | Ton- und Videodateien aus `Aufnahmen` und aus Ordnern, die du der App in der Kellerwolke freigibst, mit Dauer und Format; Hochladen (auch Ziehen und Ablegen), Aufnehmen im Browser (Mikrofon wählbar, auch während der Aufnahme; jedes Stück landet sofort im Gerätespeicher und übersteht ein Neuladen), Marker beim Aufnehmen, Live-Mitschrift während der Aufnahme; danach entscheidest du: transkribieren, Live-Text als Transkript speichern oder nur speichern |
| Transkribieren | als Auftrag in Abschnitten an Sprechpausen (Länge einstellbar); nach Abbruch oder Neustart geht es beim nächsten Abschnitt weiter; Sprache wählbar oder erkennen |
| Sprecher | Sprechertrennung, ohne sie Gruppieren der Stimmabdrücke; Abgleich mit Sprecherprofilen (sicher oder als Vorschlag zum Bestätigen); ein Profil entsteht, wenn du einem Sprecher einen Namen als Profil gibst |
| Lesen | Spieler mit Wellenform, Sprecherspur und Markern; Mitlesen Wort für Wort, Klick auf ein Wort springt hin; Suche im Text |
| Bearbeiten | Text, Sprecher, Zeiten, Teilen, Zusammenführen, Marker; die Wortzeiten gleichen sich dem geänderten Text an; Speichern legt eine neue Version an, nur mit dem zuletzt gelesenen Stand |
| KI | Korrektur als Vorschläge je Beitrag (übernommen wird nur, was du bestätigst), Auswertung nach Vorlage (Protokoll, Zusammenfassung, Aufgaben) als Markdown-Datei neben dem Transkript |
| Suchen | Volltext über alle Transkripte und Marker, auch Wortteile ("kosten" findet "Nebenkostenabrechnung"), Treffer mit Zeit |
| Versionen | jede Änderung ist eine Version der Datei in der Kellerwolke, mit Notiz; Zurückholen legt eine neue Version an |
| Export | Text, Markdown, SRT, WebVTT, DOCX, JSON; als Download oder zusätzlich als Datei neben dem Transkript |
| Telefon | eigene Ansicht: Aufnehmen, Hochladen, Ordner der Kellerwolke, Lesen mit Mitlesen, Suche |

Alles, was die Oberfläche kann, geht auch über die Schnittstelle (`/docs`). Andere Apps melden sich mit ihrem
App-Schlüssel der Kellerwolke an (`Authorization: Bearer kw_app_...`); die Einstellungen bleiben Menschen vorbehalten.

## Daten

Die einzige Wahrheit ist die Transkriptdatei in der Kellerwolke (`Transkripte/<Name>.transkript.json`, Format
`transkript/1`, beschrieben in [docs/ENTWURF.md](docs/ENTWURF.md)); die SQLite-Datei der App hält nur Verzeichnis,
Suchindex, Aufträge, Vorschläge und Protokoll und folgt der Kellerwolke über ihren Ereignisstrom. Sprecherprofile liegen
in `Sprecher/profile.json`.

## Betrieb auf dem Pi

Die Transkription läuft neben Kellerwolke und Leitstelle auf dem Pi, im Container (`Dockerfile`, `compose.pi.yml`),
erreichbar unter `https://192.168.178.49:8631` (Zertifikat der Hausstelle; HTTPS braucht der Browser fürs Mikrofon).
ffmpeg kommt nicht ins Abbild: das des Pi ist nur lesend eingehängt und läuft mit dem Lader des Pi
(`deploy/ffmpeg-vom-pi`). Daten liegen in `/mnt/data/transkription/daten`, Sicherungen in `.../sicherungen`.

```bash
tools/ausrollen.sh
```

Prüft bei jedem Neubau alles selbst: gepushter Stand und grüne Tests, ffmpeg und ffprobe auf dem Pi, Docker,
Zertifikat (stellt es bei Bedarf neu aus), sichert die Datenbank, baut und startet, wandelt im Container probehalber
mit dem ffmpeg des Pi um und vergleicht über HTTPS die Fassungen von Server, Oberfläche und `version.json`.

## Einrichten (Entwicklung)

```bash
./einrichten.sh
```

Legt die Python-Umgebung an, holt die Pakete der Oberfläche und baut sie. Danach im Stellwerk starten (Eintrag
`stellwerk.toml`) und `http://127.0.0.1:8631` öffnen: die erste Einrichtung fragt nach der Adresse der Kellerwolke
und dem App-Schlüssel (in der Kellerwolke unter Einstellungen, Zugänge). Unter Einstellungen dann die Leitstelle und
ihren Schlüssel (in der Leitstelle unter Anwendungen, mit den Fähigkeiten Hören, Sprecher erkennen, Sprecher trennen
und Sprachmodell). ffmpeg muss auf dem Rechner sein.

## Entwickeln

| Teil | Befehl |
|---|---|
| Backend | `cd backend && .venv/bin/uvicorn app.main:app --port 8631 --reload` (Daten mit `TRANSKRIPTION_DATEN` woanders) |
| Oberfläche | `cd frontend && npm run dev` (Port 9631, leitet `/api` ans Backend) |
| Leitstelle zum Schein | `backend/.venv/bin/python tools/leitstelle_schein.py --port 8698` (Klangwerk und Sprachmodell ohne echte Dienste) |
| Tests | `cd backend && .venv/bin/python -m pytest` |
| Typen | `cd frontend && npm run check` |
| Symbole | `python3 tools/symbole.py` nach einer Änderung an `frontend/public/symbol.svg` |
| Ausrollen | `tools/ausrollen.sh` (auf den Pi, siehe oben) |
| Pi im Browser ohne Zertifikat | `python3 tools/pi_durchleitung.py`, dann `http://127.0.0.1:8633` (prüft nach außen gegen die Hausstelle) |
| Entwürfe | `python3 -m http.server` im Repo, dann `/mockups/transkription.html` und `/mockups/transkription-mobil.html` |

Die Verbundtests (`test_ablage_verbund.py`, `test_verbund.py`) sprechen mit einer echten Kellerwolke und brauchen
`backend/.env.test` (nicht im Repo) mit `KELLERWOLKE_ADRESSE`, `KELLERWOLKE_SCHLUESSEL`, `KELLERWOLKE_KENNUNG`,
`KELLERWOLKE_PASSWORT`; die Leitstelle ist dabei zum Schein. Ohne die Datei werden sie übersprungen.

## Aufbau

| Ort | Inhalt |
|---|---|
| `backend/app/modell/` | Transkriptdatei und Sprecherprofile (fachlich, ohne Ein- und Ausgabe) |
| `backend/app/ablage/` | Orte im Zweig, Transkripte und Profile in der Kellerwolke |
| `backend/app/suchindex.py`, `abgleich.py` | Verzeichnis und Volltextindex, Abgleich mit der Kellerwolke |
| `backend/app/ton.py` | ffmpeg: wandeln, Pausen, Abschnitte, Wellenform |
| `backend/app/dienste.py`, `sprechererkennung.py` | Klangwerk über die Leitstelle, Sprecher zuordnen |
| `backend/app/korrektur.py`, `auswertung.py`, `export.py` | KI-Korrektur, Auswertung, Exporte |
| `backend/app/arten.py` | Aufträge (transkribieren, Sprecher erkennen, korrigieren, auswerten) |
| `backend/app/api/` | Schnittstelle |
| `frontend/src/seiten/`, `teile/`, `lib/` | Oberfläche in der gemeinsamen Schale |
| `mockups/` | freigegebene Entwürfe (laden die echte Gestaltung) |

## Version

Die Version steht nur in `version.json`; `tools/version.sh patch|minor|major` zählt hoch, der Pre-Commit-Hook
erzwingt es (`git config core.hooksPath tools/git-hooks`).

## Lizenz

**Nicht-kommerzielle Nutzung** - Siehe [LICENSE](LICENSE)

Erlaubt: Private Nutzung, Installation, persönliche Anpassungen, Teilen mit Quellenangabe

Verboten: Kommerzielle Nutzung, Verkauf, Einbindung in kommerzielle Produkte

---

## Unterstützen

Transkription ist ein privates Hobby-Projekt. Kein Tracking, keine Werbung, keine Kompromisse.

Wenn dir das Projekt gefällt, kannst du ihm einen Stern geben - oder direkt hier:

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/HalloWelt42)

**Crypto:**

| Coin | Adresse |
|------|---------|
| BTC | `bc1qnd599khdkv3v3npmj9ufxzf6h4fzanny2acwqr` |
| DOGE | `DL7tuiYCqm3xQjMDXChdxeQxqUGMACn1ZV` |
| ETH | `0x8A28fc47bFFFA03C8f685fa0836E2dBe1CA14F27` |

Copyright (c) 2026 HalloWelt42
