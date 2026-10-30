---
zweck: "Macht aus Ton und Video Text mit Wortzeiten und Sprechern; das Transkript liegt als Begleitdatei neben der Aufnahme in der Kellerwolke."
geraet: [pi]
abhaengigkeiten: [kellerwolke, leitstelle, klangwerk, appkern]
daten:
  - "Kellerwolke: die einzige Wahrheit, je Aufnahme ein Transkript `<name>.transkript.json` als Begleitdatei (mit Versionen), dazu Exporte, Auswertungen und `Sprecher/profile.json`"
  - "Pi: `{{wurzel}}/daten/transkription.sqlite` (Verzeichnis, Suchindex, Aufträge, Vorschläge, Protokoll; folgt der Kellerwolke), `abspielen/` (Abspielfassungen, rund 20 GB, neu erzeugbar), `arbeit/`, `umzug/`"
sicherung:
  - "nach der Regel des Appkerns eine Kopie von `transkription.sqlite` nach `{{wurzel}}/sicherungen`, wöchentlich und vor dem Ausrollen (nur, wenn die jüngste älter als 24 Stunden ist), nie ohne Änderung, höchstens drei Stände (Einstellungen, Sicherung); das Werkzeug Sicherungen holt sie täglich nach `~/Sicherungen/transkription/pi`"
  - "Transkripte und Aufnahmen liegen in der Kellerwolke und hängen an deren Sicherung; `abspielen/` braucht keine Sicherung"
schluessel_orte:
  - "Pi: Einstellungen im Verzeichnis `transkription.sqlite`: App-Schlüssel der Kellerwolke, Schlüssel der Leitstelle (in der Oberfläche unter Einstellungen, verdeckt)"
  - "Pi: `{{wurzel}}/zertifikate/`, Blattzertifikat mit Schlüssel aus der Hausstelle (vom Ausrollen)"
einrichten: einrichten.sh
stand: 520c4ab
---

# Transkription

## Zweck

Die Transkription macht aus Aufnahmen Text: in Abschnitten an Sprechpausen, mit Wortzeiten, auf Wunsch mit Sprechern
(gruppiert oder getrennt, mit Profilen), Korrekturvorschlägen und Auswertungen durch ein Sprachmodell. Quelle ist jede
Datei der [[Kellerwolke]]; das Transkript liegt danach als Begleitdatei neben ihr, und Verschieben, Umbenennen und
Papierkorb nehmen es mit. Während ein Auftrag läuft, zeigt die Aufnahme den schon gehörten Text je Abschnitt und
die geschätzte Restzeit. Im Dateimenü der Kellerwolke stehen "Transkribieren" und "In Transkription öffnen". Aufnehmen
geht im Browser und auf dem Telefon (HTTPS ist dafür nötig). Andere Apps (etwa [[Assistent]] für die Spracheingabe)
melden sich mit ihrem App-Schlüssel der Kellerwolke an.

Der Pi rechnet keinen Ton: Hören, Stimmabdrücke und Sprechertrennung kommen aus dem [[Klangwerk]] über die
[[Leitstelle]], Wandeln, Sprechpausen, Wellenform und Abspielfassung macht der Tondienst. Auf dem Pi läuft sie als
Compose-Projekt aus `compose.pi.yml` hinter ihrem Vorschaltdienst `vorne`. Adresse: {{adresse}}.

## Was sie braucht

- Pi nach [[Grundlage Pi]] mit Docker; Mac nach [[Grundlage Mac]] für Entwicklung, Ausrollen und Hausstelle (für die
  Tests der Entwicklung auch ffmpeg am Mac).
- [[Kellerwolke]]: Konto zum Anmelden und ein App-Schlüssel für die Transkription.
- [[Leitstelle]]: Anwendung "Transkription" mit den Fähigkeiten hoeren, ton, sprecher_erkennen, sprecher_trennen und
  text; das Ausrollen prüft, dass die Leitstelle den Tondienst meldet (fehlt er, ist das eine Warnung, kein Abbruch).
- [[Klangwerk]] am Mac mit den Diensten hoeren, sprecher, trennen und ton (über den [[Maschinenraum]]).

## Neu einrichten

Zwei Wege. Aus der Sicherung: die jüngste Kopie von `transkription.sqlite` zurückspielen; dann sind Einstellungen,
Aufträge und Vorschläge wie vorher. Frisch: leere Datenbank, erste Einrichtung mit neuem App-Schlüssel, Leitstelle
unter Einstellungen. Die Transkripte gehen dabei nicht verloren, weil sie in der Kellerwolke liegen; was nur die
SQLite-Datei hielt (Aufträge, Vorschläge, Suchindex, Protokoll), beginnt neu.

### 1. Repo und Entwicklungsumgebung am Mac

```
git clone {{repo}} {{ordner}}
cd {{ordner}} && ./einrichten.sh
```

Python-Umgebung, Oberfläche, Appkern auf einen Commit, Git-Haken; das Ausrollen prüft mit dieser Umgebung.

Probe: `test -f frontend/dist/index.html && backend/.venv/bin/python -c "import appkern"` endet ohne Fehler.

### 2. Ordner auf dem Pi

Auf dem Pi `mkdir -p {{wurzel}}/daten {{wurzel}}/sicherungen` (sonst legt Docker sie für root an). Aus der Sicherung die jüngste Kopie als
`{{wurzel}}/daten/transkription.sqlite` ablegen (Besitzer `pi`).

Probe: `stat -c %U {{wurzel}}/daten` meldet `pi`.

### 3. Ausrollen

Am Mac `tools/ausrollen.sh`: Tests, Appkern-Stand, Tondienst bei der Leitstelle, Zertifikat, Bau, Start und Prüfung von
Fassung, HTTP/2 und Symbolen. Vorher läuft `handbuch freigabe` (Prüfung der Seite, Probelauf, Handbuch).

Probe: `curl -s --cacert "$(mkcert -CAROOT)/rootCA.pem" {{adresse}}/api/v1/app` meldet `"fassung": "{{fassung}}"`.

### 4. Erste Einrichtung

Aus der Sicherung entfällt sie. Frisch: in der [[Kellerwolke]] einen App-Schlüssel für die Transkription anlegen,
{{adresse}} öffnen und mit dem Einrichtungscode die Adresse der Kellerwolke und den Schlüssel eintragen; danach mit dem
eigenen Kellerwolke-Konto anmelden. Telefone koppeln sich einmal je Web-App.

Probe: `/api/v1/app` meldet `"einrichtung_noetig": false` und den Besitzer.

### 5. Leitstelle und Tondienst

Aus der Sicherung stehen sie im Verzeichnis. Frisch: in der [[Leitstelle]] die Anwendung "Transkription" anlegen, ihren
Schlüssel unter Einstellungen, Verbindungen eintragen, "Tondienst" wählen und "Adresse dieser App" auf {{adresse}}
setzen (damit die Aktionen im Dateimenü der Kellerwolke hierher führen).

Probe: unter Einstellungen, Verbindungen sind Kellerwolke und Leitstelle grün, und eine kurze Aufnahme wird
transkribiert.

## Sicherung und Rückspielen

Nach der Regel der Sicherung aus dem [[Appkern]] legt die App einmal je Woche, das Ausrollen vor dem Neustart (nur,
wenn die jüngste älter als 24 Stunden ist) eine stimmige Kopie von `transkription.sqlite` nach
`{{wurzel}}/sicherungen/transkription-<Zeit>.sqlite`; hat sich seit der jüngsten nichts geändert, entsteht keine, und
höchstens drei bleiben (Werte unter Einstellungen, Sicherung). Das Werkzeug Sicherungen am Mac holt sie täglich nach
`~/Sicherungen/transkription/pi` (Stand in `~/Sicherungen/LIESMICH.md`). Transkripte, Aufnahmen und Sprecherprofile
hängen an der Sicherung der Kellerwolke; `abspielen/` entsteht neu.

Zurückspielen: auf dem Pi im Ordner {{wurzel}} `docker compose -f compose.pi.yml stop transkription`, die Kopie als
`daten/transkription.sqlite` ablegen (alte `-wal` und `-shm` daneben entfernen), `docker compose -f compose.pi.yml start
transkription`. Probe wie in Schritt 3.

## Wenn etwas klemmt

- Transkribieren hängt: die Leitstelle meldet keinen Hördienst (Klangwerk hoeren nicht gestartet, oder der Mac
  schläft); Aufträge warten und laufen am nächsten Abschnitt weiter.
- Das Mikrofon geht nicht: die Seite muss über HTTPS kommen ({{adresse}}), und das Gerät muss der Hausstelle vertrauen.
- Eine Aktion im Dateimenü der Kellerwolke fehlt: "Adresse dieser App" ist nicht gesetzt (Schritt 5).
- Korrigieren oder Auswerten geht nicht: unter Einstellungen, KI ist kein Sprachmodell gewählt, oder die Leitstelle
  bietet das gewählte der Anwendung Transkription nicht an (Fähigkeit text).
- Eine Sprache fehlt zur Wahl: die Sprachen kommen aus dem Steckbrief des Hördienstes (Selbstauskunft in seiner
  Dienstdatei, siehe [[Klangwerk]]); antwortet die Leitstelle nicht, steht nur Erkennen und die eingestellte zur Wahl.
- Die Suche findet etwas nicht: unter Transkripte sucht sie in Namen, Text und Markern der eigenen Transkripte
  (nicht in denen, die andere Apps bestellen), unter Aufnahmen nur nach Dateinamen ab dem gewählten Ordner abwärts.
- Das Ausrollen wartet lange: es wartet auf eine Lücke ohne laufenden Auftrag (bis vier Stunden); `--sofort` rollt
  trotzdem aus.
