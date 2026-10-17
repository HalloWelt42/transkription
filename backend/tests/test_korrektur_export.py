"""KI-Korrektur (Fenster, Anfrage, Lesen der Antwort mit Schutz), Auswertung (Vorlagen) und Exporte."""

import io
import json
import zipfile

from app import auswertung, export
from app.korrektur import anfrage, antwort_lesen, fenster, vorschlaege
from app.modell.transkript import Marker, Segment, Sprecher, Transkript


def probe() -> Transkript:
    return Transkript(
        name="Folge 12", sprecher=[Sprecher(kennung="s1", name="Anna", abdruck=[0.1] * 3), Sprecher(kennung="s2", name="Herr Krüger")],
        segmente=[Segment(start=0, ende=4.5, sprecher="s1", text="Guten Tag."),
                  Segment(start=4.5, ende=9, sprecher="s1", text="Es geht um die Abrechnung."),
                  Segment(start=9.2, ende=3725.25, sprecher="s2", text="Die kam spät.")],
        marker=[Marker(zeit=4.0, titel="Kosten")])


def test_fenster_und_anfrage():
    assert [list(r) for r in fenster(7)] == [[0, 1, 2], [3, 4, 5], [6]]
    t = probe()
    system, nutzer = anfrage(t.segmente, range(1, 2))
    assert system.rolle == "system" and "[n] Text" in system.inhalt
    assert "davor (nicht korrigieren): Guten Tag." in nutzer.inhalt and "[1] Es geht um die Abrechnung." in nutzer.inhalt
    assert "danach (nicht korrigieren): Die kam spät." in nutzer.inhalt


def test_antwort_lesen_mit_schutz():
    alte = ["Dürfen wir die Belege vor Ort ein sehen?", "Gut.", "Selbstverständlich nach Absprache."]
    antwort = "Hier die Korrektur:\n[1] Dürfen wir die Belege vor Ort einsehen?\n[3] Selbstverständlich, nach Absprache. Und noch ein sehr langer erfundener Zusatz dazu."
    assert antwort_lesen(antwort, alte) == ["Dürfen wir die Belege vor Ort einsehen?", None, None]
    t = probe()
    v = vorschlaege(t.segmente, range(0, 3), "[1] Guten Tag!\n[2] Es geht um die Abrechnung.\n[3] Die kam spät.")
    assert [(x.start, x.alt, x.neu) for x in v] == [(0.0, "Guten Tag.", "Guten Tag!")]


def test_exporte():
    t = probe()
    assert export.als_text(t) == "Anna: Guten Tag. Es geht um die Abrechnung.\n\nHerr Krüger: Die kam spät.\n"
    md = export.als_markdown(t)
    assert md.startswith("# Folge 12") and "**Anna** [0:00]:" in md and "**Herr Krüger** [0:09]:" in md
    assert md.index("> [0:04] Kosten") > md.index("Abrechnung.")              # Marker vor dem nächsten Absatz
    srt = export.als_srt(t)
    assert "3\n00:00:09,200 --> 01:02:05,250\nHerr Krüger: Die kam spät.\n" in srt
    vtt = export.als_vtt(t)
    assert vtt.startswith("WEBVTT\n") and "01:02:05.250" in vtt and "<v Anna>Guten Tag.</v>" in vtt
    daten = json.loads(export.erzeugen(t, "json"))
    assert daten["format"] == "transkript/1" and "abdruck" not in daten["sprecher"][0]
    docx = export.erzeugen(t, "docx")
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        dokument = z.read("word/document.xml").decode()
    assert "Herr Krüger: " in dokument and "Folge 12" in dokument
    assert export.marke(3725) == "1:02:05" and export.marke(65) == "1:05"


def test_auswertung_vorlagen():
    nachrichten = auswertung.anfrage("protokoll", "# Folge 12")
    assert "## Entscheidungen und Zusagen" in nachrichten[0].inhalt and nachrichten[1].inhalt == "# Folge 12"
    assert auswertung.dateiname("Folge 12", "aufgaben") == "Folge 12 (Aufgaben).md"
