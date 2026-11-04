"""Gespräch fortsetzen (HELF-154): Anhängen ab der alten Dauer, Sprecher des neuen Bereichs auf die bisherigen, Marken,
Sprecherweg wie bisher, Kodierer der zusammengefügten Datei."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app import gespraech
from app.modell.transkript import ErzeugtMit, Marker, Quelle, Segment, Sprecher, Transkript, Wort
from app.sprechererkennung import Schwellen

S = Schwellen()
WANN = datetime(2026, 11, 4, 18, 15, tzinfo=UTC)


def _bisher() -> Transkript:
    return Transkript(name="Runde", dauer_s=60.0, wellenform=[10] * 8,
                      sprecher=[Sprecher(kennung="s1", name="Anna", abdruck=[1.0, 0.0, 0.0]),
                                Sprecher(kennung="s2", name="Herr Krüger", abdruck=[0.0, 1.0, 0.0])],
                      segmente=[Segment(start=0, ende=5, sprecher="s1", text="Guten Tag."),
                                Segment(start=50, ende=58, sprecher="s2", text="Bis bald.")],
                      marker=[Marker(zeit=3, titel="Anfang")])


def test_anhaengen_ab_der_alten_dauer():
    bisher = _bisher()
    quelle = Quelle(knoten_id=uuid4(), pfad="Apps/Transkription/Aufnahmen/Runde.webm", etag="neu")
    neu_sprecher = [Sprecher(kennung="s1", name="Sprecher 1", abdruck=[0.05, 0.99, 0.0]),     # klingt wie Herr Krüger
                    Sprecher(kennung="s2", name="Sprecher 2", abdruck=[0.0, 0.0, 1.0])]       # neu im Gespräch
    segmente = [Segment(start=61, ende=64, sprecher="s1", text="Wir sind wieder da.", woerter=[Wort(wort="Wir", start=61, ende=61.4)]),
                Segment(start=66, ende=69, sprecher="s2", text="Ich bin neu.")]
    marker = [Marker(zeit=3, titel="Anfang"), Marker(zeit=62, titel="Weiter")]
    t = gespraech.anhaengen(bisher, 60.0, segmente, neu_sprecher, marker, 80.0, [90] * 8, quelle, WANN, S)
    assert [(s.start, s.sprecher, s.text) for s in t.segmente] == [
        (0, "s1", "Guten Tag."), (50, "s2", "Bis bald."), (61, "s2", "Wir sind wieder da."), (66, "s3", "Ich bin neu.")]
    assert [s.kennung for s in t.sprecher] == ["s1", "s2", "s3"] and t.sprecher[1].name == "Herr Krüger"
    assert t.sprecher[2].name == "Sprecher 3"
    assert [(m.zeit, m.titel) for m in t.marker] == [(3, "Anfang"), (60.0, gespraech.marke(WANN)), (62, "Weiter")]
    assert t.marker[1].titel.startswith("Weiter aufgenommen am 04.11.2026")
    assert t.dauer_s == 80.0 and t.wellenform == [90] * 8 and t.quelle == quelle


def test_gleiches_profil_geht_vor_dem_abdruck():
    profil = uuid4()
    bisher = _bisher()
    bisher.sprecher[0] = bisher.sprecher[0].model_copy(update={"profil_id": profil})
    abbildung, alle = gespraech.sprecher_zuordnen(
        bisher.sprecher, [Sprecher(kennung="s1", name="Anna", profil_id=profil, abdruck=[0.0, 1.0, 0.0])], S)
    assert abbildung == {"s1": "s1"} and len(alle) == 2


def test_ohne_sprecher_bleibt_ohne():
    bisher = Transkript(name="Notiz", dauer_s=10, segmente=[Segment(start=0, ende=3, text="Eins.")])
    q = Quelle(knoten_id=uuid4(), pfad="x.webm")
    t = gespraech.anhaengen(bisher, 10.0, [Segment(start=10.5, ende=12, text="Zwei.")], [], [], 14.0, None, q, WANN, S)
    assert [(s.start, s.sprecher) for s in t.segmente] == [(0, None), (10.5, None)] and t.sprecher == []


def test_sprecherweg_wie_bisher():
    def mit(aus):
        return Transkript(name="x", erzeugt_mit=ErzeugtMit(dienst="whisper", app="t", sprecher_aus=aus))
    assert gespraech.sprecher_wie_bisher(mit("ohne")) == ("ohne", None)
    assert gespraech.sprecher_wie_bisher(mit("stimmen")) == ("stimmen", None)
    assert gespraech.sprecher_wie_bisher(mit("pyannote")) == ("trennung", "pyannote")
    assert gespraech.sprecher_wie_bisher(mit("whisper")) == ("trennung", None)
    assert gespraech.sprecher_wie_bisher(Transkript(name="x")) == ("ohne", None)


def test_kodierer_wie_die_aufnahme():
    assert gespraech.kodierer("opus", ".webm") == "libopus"
    assert gespraech.kodierer(None, ".m4a") == "aac"
    assert gespraech.kodierer("mp3", ".mp3") == "libmp3lame"
    with pytest.raises(ValueError):
        gespraech.kodierer("wmav2", ".wma")
