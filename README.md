# Transkription

Transkription macht aus Ton und Video Text mit Wortzeiten und Sprechern. Eine App auf dem
[Appkern](https://github.com/HalloWelt42/appkern): Dateien in der Kellerwolke (Zweig `Apps/Transkription`), KI nur über
die Leitstelle (Hören, Stimmabdrücke und Sprechertrennung aus dem Klangwerk, Sprachmodell für Korrektur und
Auswertung), Anmeldung mit dem Kellerwolke-Konto, gestartet vom Stellwerk.

## Was sie kann

| Bereich | Inhalt |
|---|---|
| Aufnahmen | Ton- und Videodateien aus `Aufnahmen`, mit Dauer und Format; Hochladen (auch Ziehen und Ablegen), Aufnehmen im Browser (Mikrofon wählbar, auch während der Aufnahme; jedes Stück landet sofort im Gerätespeicher und übersteht ein Neuladen), Marker beim Aufnehmen, Live-Mitschrift während der Aufnahme; danach entscheidest du: transkribieren, Live-Text als Transkript speichern oder nur speichern |
| Kellerwolke | alle deine Dateien als Quelle: blättern, Ton und Video wählen und transkribieren; die App liest jede Datei nur für ihren Auftrag (eine Anfrage je Datei), das Transkript liegt danach neben der Datei. Im Dateimenü der Kellerwolke stehen "Transkribieren" und "In Transkription öffnen"; geöffnet zeigt die App, woher die Datei kommt und bis wann sie sie bearbeiten darf |
| Transkribieren | als Auftrag in Abschnitten an Sprechpausen (Länge einstellbar); nach Abbruch oder Neustart geht es beim nächsten Abschnitt weiter; Sprache erkennen oder wählen aus dem, was der Hördienst laut seinem Steckbrief in der Leitstelle kann (keine eigene Liste); Mitlesen an der Aufnahme: der Text erscheint je fertigem Abschnitt, rollt mit (per Stecknadel abschaltbar), dazu die geschätzte Restzeit |
| Sprecher | nur auf deine Wahl (ab Werk ohne): je Aufnahme ohne, Stimmen gruppieren oder mit Sprechertrennung, später jederzeit neu erkennen; von Hand zuordnen im Bearbeiten (Beiträge wählen, auch als Bereich, dann Sprecher per Knopf oder Ziffertaste, neuer Sprecher, Umbenennen, Zusammenführen); Abgleich mit Sprecherprofilen (sicher oder als Vorschlag zum Bestätigen); ein Profil entsteht, wenn du einem Sprecher einen Namen als Profil gibst |
| Lesen | Spieler mit Wellenform, Sprecherspur und Markern; Mitlesen Wort für Wort, Klick auf ein Wort springt hin; Suche im Text mit Trefferzahl beim Tippen, Eingabe springt zum nächsten Treffer |
| Bearbeiten | ein Modus für Text, Sprecher und Marker, am Rechner und am Telefon: oben eine feste Leiste mit kurzer Anleitung, Zahl der Änderungen, Verwerfen, Speichern und Fertig; Klick (am Telefon Antippen) öffnet einen Beitrag: Sprecher, Text, Beginn und Ende (von Hand oder per Knopf als Spielerzeit), Teilen, Zusammenführen, Marker; Schalter "am Ende des Beitrags anhalten"; die Suche bleibt; jede Änderung, auch ein Marker aus der Leiste, sammelt sich im Entwurf; die Wortzeiten gleichen sich dem geänderten Text an; Speichern legt eine neue Version an, nur mit dem zuletzt gelesenen Stand |
| KI | Sprachmodell wählt die App (Einstellungen, KI; Vorgabe das große Gesprächsmodell des Hauses), ohne Wahl sagt die Leiste das; Korrektur als Vorschläge je Beitrag (übernommen wird nur, was du bestätigst), Auswertung nach Vorlage (Protokoll, Zusammenfassung, Aufgaben) als Markdown-Datei neben der Aufnahme |
| Suchen | Volltext über Namen, Text und Marker aller Transkripte, auch Wortteile ("kosten" findet "Nebenkostenabrechnung"), Groß und Klein egal auch bei Umlauten, Treffer mit Zeit; unter Aufnahmen nach Namen, auch in Unterordnern |
| Versionen | jede Änderung ist eine Version der Datei in der Kellerwolke, mit Notiz; Zurückholen legt eine neue Version an |
| Export | Text, Markdown, SRT, WebVTT, DOCX, JSON; als Download oder zusätzlich als Datei neben der Aufnahme |
| Telefon | eigene Ansicht: Aufnehmen, Hochladen, alle Dateien der Kellerwolke, Lesen mit Mitlesen, Suche |

Alles, was die Oberfläche kann, geht auch über die Schnittstelle (`/docs`). Andere Apps melden sich mit ihrem
App-Schlüssel der Kellerwolke an (`Authorization: Bearer kw_app_...`); die Einstellungen bleiben Menschen vorbehalten.

## Daten

Die einzige Wahrheit ist die Transkriptdatei in der Kellerwolke, eine je Aufnahme als ihre Begleitdatei
(`Aufnahmen/Runde.wav` und daneben `Aufnahmen/Runde.transkript.json`, Format `transkript/1`, beschrieben in
[docs/ENTWURF.md](docs/ENTWURF.md)); neu transkribiert wird eine neue Version. Exporte und Auswertungen liegen ebenso
neben der Aufnahme, und Verschieben, Umbenennen und Papierkorb nehmen alles mit. Aus der früheren getrennten Ablage
`Transkripte/` führt "Zusammenführen" unter Aufnahmen alles einmal zusammen, mit Vorschau; gelöscht wird nichts. Die
SQLite-Datei der App hält nur Verzeichnis,
Suchindex, Aufträge, Vorschläge und Protokoll und folgt der Kellerwolke über ihren Ereignisstrom. Sprecherprofile liegen
in `Sprecher/profile.json`.

## Übernahme aus der alten App

Eigene Aufnahmen der alten App samt aller Transkript-Stände (als Versionen) und ihre Sprecherprofile übernimmt die App
selbst. Den Plan baut `scripts/umzug_kellerwolke.py` der alten App; hier reiht ihn das Werkzeug am Rechner der App ein
(ohne `--ausfuehren` nur Vorschau), danach die App neu starten:

```bash
docker exec transkription python -m app.werkzeug altbestand /app/daten/umzug/plan.json --ausfuehren
```

Einzelne Aufnahmen gehen auch von Hand unter Aufnahmen, Ordner, Altbestand. `python -m app.werkzeug umwandeln` bringt
Transkripte der alten App ins Format `transkript/1` für Dateien, die nicht in diese App kommen (Sprachausgaben).

## Betrieb auf dem Pi

Die Transkription läuft neben Kellerwolke und Leitstelle auf dem Pi, im Container (`Dockerfile`, `compose.pi.yml`),
erreichbar über HTTPS auf Port 8631 (Zertifikat der Hausstelle; HTTPS braucht der Browser fürs Mikrofon).
Vorne steht wie bei Kiste und Kellerwolke ein Caddy (`deploy/Caddyfile`, TLS und HTTP/2), die App dahinter ist von außen
nicht erreichbar.
Der Pi rechnet keinen Ton (er liefert nur Daten): Wandeln, Sprechpausen, Wellenform und Abspielfassung macht der
Tondienst auf dem Mac über die Leitstelle (`appkern.ton.TonDienst`, Einstellung "Tondienst"); im Container gibt es kein
ffmpeg. Daten liegen im Ordner der App auf dem Pi unter `daten/`, Sicherungen unter `sicherungen/`; Rechner, Ordner und
Adresse des Hauses stehen nicht im Repo, `tools/ausrollen.sh` holt sie aus der privaten Wahrheit (`handbuch ziel`).

```bash
tools/ausrollen.sh
```

Prüft bei jedem Neubau alles selbst: gepushter Stand und grüne Tests, gleicher Appkern in Oberfläche und Backend,
ob die Leitstelle den Tondienst meldet, Docker, Zertifikat (stellt es bei Bedarf neu aus), wartet auf laufende
Aufträge, sichert die Datenbank, baut und startet und vergleicht über HTTPS die Fassungen von Server,
Oberfläche und `version.json`, HTTP/2 und die Symbole. Die Angaben stehen in `deploy/ausrollen.toml`, der Ablauf für
alle Apps gleich im Appkern (`appkern.werkzeuge.ausrollen`).

## Einrichten (Entwicklung)

```bash
./einrichten.sh
```

Legt die Python-Umgebung an, holt die Pakete der Oberfläche und baut sie. Danach im Stellwerk starten (Eintrag
`stellwerk.toml`) und `http://127.0.0.1:8631` öffnen: die erste Einrichtung fragt nach der Adresse der Kellerwolke
und dem App-Schlüssel (in der Kellerwolke unter Einstellungen, Zugänge). Unter Einstellungen dann die Leitstelle und
ihren Schlüssel (in der Leitstelle unter Anwendungen, mit den Fähigkeiten Hören, Ton bearbeiten, Sprecher erkennen,
Sprecher trennen und Sprachmodell). Die Tests rechnen Ton selbst (der echte Tondienst im Prozess); dafür muss ffmpeg
auf dem Entwicklungsrechner sein.

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
| Appkern heben | `tools/appkern.sh` (Oberfläche und Backend auf denselben Commit; Ausrollen prüft das) |
| Ansicht prüfen | `tools/ansicht.sh` (Seiten aus `frontend/ansicht.json` in allen Breiten, hell und dunkel: seitliches Rollen, Überlauf, Kontrast, Verschiebung beim Wechsel) |
| Pi im Browser ohne Zertifikat | `python3 tools/pi_durchleitung.py`, dann `http://127.0.0.1:8633` (prüft nach außen gegen die Hausstelle) |
| Entwürfe | `python3 -m http.server` im Repo, dann `/mockups/transkription.html` und `/mockups/transkription-mobil.html` |

Die Verbundtests (`test_ablage_verbund.py`, `test_verbund.py`) sprechen mit einer echten Kellerwolke und brauchen
`backend/.env.test` (nicht im Repo) mit `KELLERWOLKE_ADRESSE`, `KELLERWOLKE_SCHLUESSEL`, `KELLERWOLKE_KENNUNG`,
`KELLERWOLKE_PASSWORT`; die Leitstelle ist dabei zum Schein. Ohne die Datei werden sie übersprungen. Der Schlüssel
gehört einem eigenen Zugang nur für die Tests, nie dem der Entwicklungsinstanz: ein Testlauf meldet die Aktionen seines
Zugangs neu und zieht sie am Ende zurück.

## Aufbau

| Ort | Inhalt |
|---|---|
| `backend/app/modell/` | Transkriptdatei und Sprecherprofile (fachlich, ohne Ein- und Ausgabe) |
| `backend/app/ablage/` | Orte im Zweig, Transkripte und Profile in der Kellerwolke |
| `backend/app/suchindex.py`, `abgleich.py` | Verzeichnis und Volltextindex, Abgleich mit der Kellerwolke |
| `backend/app/ton.py` | Hörabschnitte an Sprechpausen planen (die Pausen misst der Tondienst) |
| `backend/app/dienste.py`, `sprechererkennung.py` | Klangwerk über die Leitstelle, Sprecher zuordnen |
| `backend/app/korrektur.py`, `auswertung.py`, `export.py` | KI-Korrektur, Auswertung, Exporte |
| `backend/app/arten.py` | Aufträge (transkribieren, Sprecher erkennen, korrigieren, auswerten) |
| `backend/app/api/` | Schnittstelle |
| `frontend/src/seiten/`, `teile/`, `lib/` | Oberfläche in der gemeinsamen Schale |
| `mockups/` | freigegebene Entwürfe (laden die echte Gestaltung) |

## Version

Die Version steht nur in `version.json`; `tools/version.sh patch|minor|major` zählt hoch, der Pre-Commit-Hook
erzwingt es (`git config core.hooksPath tools/git-hooks`) und prüft die vorgemerkten Dateien: nur gerade Zeichen,
Stil ohne `!important`, ohne einseitige Streifen und ohne Regeln auf Klassen der Schale (`appkern.werkzeuge`).

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
