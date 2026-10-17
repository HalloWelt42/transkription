# Transkription: Entwurf

Stand 17.10.2026, zur Freigabe. Grundlage: Bestandsaufnahme der alten txt2voice (Endpunkte, Daten, Abläufe,
Oberfläche) und die Regeln des Neubaus (`txt2voice/docs/NEUBAU.md`).

Die Transkription macht aus Ton und Video Text mit Wortzeiten und Sprechern. Sie ist die erste App auf dem Appkern:
Dateien in der Kellerwolke, KI nur über die Leitstelle, Anmeldung mit dem Kellerwolke-Konto, gestartet vom Stellwerk.
Alles, was die Oberfläche kann, geht auch über die Schnittstelle (Vertonung, Stimmenausgabe, Assistent, TubeVault,
Pinnwand und morf-gpt sind ihre Kunden).

## 1. Was neu besser wird als in der alten App

| Alt | Neu |
|---|---|
| Transkript in der Datenbank, Master-Datei daneben, beide liefen auseinander (Korrektur nur in der DB) | Eine Wahrheit: die Transkriptdatei in der Kellerwolke; die Datenbank ist nur Verzeichnis und Suchindex |
| Keine Versionen; Korrektur überschreibt | Jede Änderung ist eine neue Version der Datei (die Kellerwolke hält sie), Zurückholen geht |
| Wortzeiten gespeichert, aber nie gezeigt; Text nicht bearbeitbar | Mitlesen Wort für Wort, Klick auf ein Wort springt hin; Text, Sprecher und Zeiten bearbeitbar |
| Vier Exporte je Lauf automatisch (5678 Dateien) | Exporte erst auf Wunsch, als Download oder auf Wunsch als Datei neben dem Transkript |
| Abbruch löscht alles; lange Aufnahmen nur am Stück | Abschnitte an Sprechpausen; nach Abbruch oder Neustart geht es beim nächsten Abschnitt weiter |
| Marker nur in der Master-Datei, Suche fand sie nicht | Marker im Transkript und im Suchindex |
| Fremde Programme ohne Schlüssel (CORS `*`) | Jeder Zugriff mit Anmeldung oder App-Schlüssel |

## 2. Daten

**In der Kellerwolke** (Zweig `Apps/Transkription`, Inhalte als Dateien):

| Ort | Inhalt |
|---|---|
| `Aufnahmen/` | hochgeladene oder aufgenommene Ton- und Videodateien (weitere Ordner gibt der Nutzer der App frei) |
| `Transkripte/<Name>.transkript.json` | das Transkript (Format unten); Herkunftsbezug `transkript_zu` auf die Aufnahme |
| `Transkripte/<Name> (Auswertung).md` | KI-Auswertung, Herkunft `abgeleitet_von` |
| `Sprecher/profile.json` | Sprecherprofile: Name, gemittelter Stimmabdruck, Zahl der Proben |

**Transkriptdatei** (eine Datei je Transkript, versioniert durch die Kellerwolke):

```json
{
  "format": "transkript/1",
  "name": "Folge 12",
  "quelle": {"knoten_id": "...", "pfad": "Apps/Transkription/Aufnahmen/Folge 12.wav", "etag": "..."},
  "sprache": "de",
  "dauer_s": 2712.4,
  "erstellt_am": "...", "geaendert_am": "...",
  "sprecher": [{"kennung": "s1", "name": "Anna", "profil_id": "...", "aehnlichkeit": 0.82}],
  "segmente": [
    {"start": 12.40, "ende": 18.95, "sprecher": "s1", "text": "Guten Tag ...",
     "woerter": [{"wort": "Guten", "start": 12.40, "ende": 12.71}]}
  ],
  "marker": [{"zeit": 301.2, "titel": "Kosten", "farbe": "gelb"}],
  "erzeugt_mit": {"modell": "whisper-large-v3", "app": "0.1.0"}
}
```

**In der App** (SQLite, nur Verzeichnis und Index, jederzeit aus der Kellerwolke neu aufbaubar):
Verzeichnis der Transkripte (Kennung, Name, Knoten der Datei und der Quelle, Sprache, Dauer, Sprecher, Stand),
Volltextindex der Segmente (FTS5, mit Zeiten für den Sprung), Aufträge und Protokoll aus dem Appkern.

## 3. Abläufe (Aufträge)

| Art | Phasen | Fortsetzbar |
|---|---|---|
| `transkribieren` | Vorbereiten (Ton holen, auf 16 kHz mono wandeln, an Sprechpausen in Abschnitte von höchstens 10 min teilen), Hören (Abschnitt für Abschnitt über `klangwerk-hoeren`), Sprecher (Abdrücke über `klangwerk-sprecher`, Trennung über `klangwerk-trennen`, Abgleich mit den Profilen), Speichern (Datei, Herkunft, Index) | ja, je Abschnitt; nach Neustart weiter |
| `sprecher_erkennen` | Sprecher, Speichern (für ein vorhandenes Transkript, auf Wunsch mit Sprecherzahl) | nein |
| `korrigieren` | KI-Korrektur über die Leitstelle in Fenstern von drei Segmenten; Ergebnis ist ein Vorschlag, übernommen wird je Segment | je Fenster |
| `auswerten` | KI-Auswertung (Vorlage wählbar: Protokoll, Zusammenfassung, Aufgaben), Ergebnis als Markdown-Datei | nein |

Wartet die Leitstelle (Modell lädt, Speicher knapp), steht das als Schritt im Auftrag. Abbrechen geht zwischen zwei
Abschnitten; das Bisherige bleibt als Zwischenstand.

## 4. Schnittstelle (`/api/v1`, alles hinter Anmeldung oder App-Schlüssel)

| Aufruf | Zweck |
|---|---|
| `GET /aufnahmen?ordner=` | Ton- und Videodateien in den freigegebenen Ordnern, mit Stand (transkribiert, läuft, nein) |
| `POST /aufnahmen` | hochladen (Strom, große Dateien) nach `Aufnahmen/` |
| `POST /transkribieren` | `{quelle (Knoten oder Pfad), sprache (de, en, auto), sprecher (an/aus, Anzahl), name}` liefert den Auftrag |
| `GET /transkripte?suche=&sprache=&sprecher=&seite=` | Verzeichnis, seitenweise; mit `suche` Treffer im Text samt Zeit |
| `GET /transkripte/{id}` | das Transkript (Datei aus der Kellerwolke) |
| `PATCH /transkripte/{id}` | Änderungen an Text, Sprechern, Zeiten, Markern; nur mit dem zuletzt gelesenen Stand (sonst 409) |
| `GET /transkripte/{id}/versionen`, `POST .../versionen/{v}/zurueck` | Versionen aus der Kellerwolke |
| `GET /transkripte/{id}/export?format=txt\|md\|srt\|vtt\|json\|docx&ablegen=` | Export als Download oder als Datei neben dem Transkript |
| `GET /transkripte/{id}/ton` | Ton zum Mitlesen (aus der Kellerwolke durchgereicht, mit Bereichen) |
| `POST /transkripte/{id}/sprecher-erkennen`, `/korrigieren`, `/auswerten` | Aufträge |
| `DELETE /transkripte/{id}` | in den Papierkorb der Kellerwolke (die Aufnahme bleibt) |
| `GET /sprecher`, `PATCH /sprecher/{id}`, `POST /sprecher/{id}/zusammenfuehren`, `DELETE /sprecher/{id}` | Profile |
| `POST /hoeren` | kurzer Ton (bis 2 min) sofort zu Text, ohne Auftrag: Spracheingabe im Assistenten, Referenztext der Stimmenausgabe |

Fremde Apps sprechen die Transkription mit ihrem App-Schlüssel der Kellerwolke an (`Authorization: Bearer
kw_app_...`); die Transkription prüft ihn bei der Kellerwolke (welches Konto, welche App) und lässt nur die Konten zu,
die sie auch in der Oberfläche zulässt. Dafür bekommt die Anmeldung im Appkern diesen zweiten Weg (siehe Frage 2).

## 5. Oberfläche (Entwürfe in `mockups/`)

Bereiche in der Schale: **Aufnahmen**, **Transkripte**, **Sprecher**; dazu aus dem Appkern Aufträge, Protokoll,
Einstellungen. Die Entwürfe laden die echte Gestaltung der Schale aus dem eingebundenen Appkern
(`mockups/kopf.css`); ansehen mit einem statischen Server aus dem Repo-Wurzelordner, etwa
`python3 -m http.server` und dann `/mockups/transkription.html` (Knopf unten rechts: hell oder dunkel).

`mockups/transkription.html`, am Rechner:

1. **Aufnahmen**: Ton- und Videodateien aus `Aufnahmen/` und den freigegebenen Ordnern, Filter (alle, ohne
   Transkript, transkribiert), Hochladen per Knopf oder Ziehen, Aufnehmen im Browser; gewählte Dateien bekommen eine
   Leiste mit Sprache, Sprechererkennung und Anzahl und starten den Auftrag.
2. **Transkripte**: Verzeichnis seitenweise, Volltextsuche über Text und Marker mit Trefferzeilen samt Zeit (Klick
   springt in den Ton), Filter nach Sprache und Sprecher.
3. **Transkript lesen** (Adresse `/transkripte/<kennung>`): Spieler mit Wellenform, Sprecherspur und Markern,
   Tempo; Mitlesen Wort für Wort, Klick auf Wort oder Zeit springt hin. Rechts Sprecher (mit Vorschlag aus den
   Profilen zum Übernehmen), Marker, Export (Text, Markdown, SRT, WebVTT, DOCX, JSON, auf Wunsch auch als Datei neben
   dem Transkript), KI über die Leitstelle (Korrigieren, Auswerten), Versionen.
4. **Bearbeiten**: ein Beitrag offen (Text, Sprecher, Zeiten, am Cursor teilen, mit dem nächsten zusammenführen,
   Marker); Vorschläge der KI-Korrektur je Beitrag als Gegenüberstellung zum Übernehmen oder Verwerfen; Speichern
   legt eine neue Version an, die alte bleibt abrufbar. Hat jemand anderes inzwischen gespeichert, sagt das die
   Speicherleiste und bietet Neuladen an (409 der Schnittstelle).
5. **Sprecher**: Profile mit Zahl der Transkripte und Proben, Proben zum Anhören, Umbenennen, Zusammenführen, Löschen;
   Schwellen für "sicher" und "Vorschlag" kommen aus den Einstellungen.

`mockups/transkription-mobil.html`, eigene Telefonansicht (Reiter Aufnahmen, Transkripte, Aufträge, Mehr; Sprecher
unter Mehr):

1. **Aufnahmen**: großer Aufnahmeknopf, Datei wählen oder aus der Kellerwolke, die letzten Aufnahmen mit Stand.
2. **Aufnahme läuft**: Zeit, Pegel, Anhalten, Beenden, Marker setzen; der Ton wird laufend in Stücken gesichert
   (fortsetzbarer Upload der Kellerwolke), Name und "danach transkribieren" gleich darunter.
3. **Transkript lesen**: Beiträge untereinander mit Mitlesen, Spieler über den Reitern.
4. **Suche**: Treffer mit Zeit, Tippen springt in den Ton; weitere Treffer seitenweise.

## 6. Übernahme des Altbestands (eigener Schritt, später)

1455 fertige Transkripte (327 MB Segmente mit Wortzeiten), 6 Sprecherprofile, Marker aus den Master-Dateien; die
Quellaufnahmen sind 74 GB. Ein Werkzeug mit Probelauf und Prüfsumme schreibt Transkriptdateien in die Kellerwolke; ob
die Aufnahmen mitkommen oder dort bleiben, wo sie sind, entscheidet der Nutzer vor dem Lauf.

## 7. Offene Fragen an den Nutzer

1. Freigabe der Entwürfe (Seiten am Rechner und am Telefon).
2. App-zu-App: Fremde Apps melden sich mit ihrem App-Schlüssel der Kellerwolke an (Vorschlag) oder bekommen je App
   einen eigenen Schlüssel in jeder Ziel-App.
3. Repository: öffentlich wie Appkern und Leitstelle, oder privat.
