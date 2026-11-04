"""Gespräch in Teilen (HELF-154): Anhängen mit Versatz, Sprecher des Teils auf die bisherigen, Wellenform,
Sprecherweg wie bisher, Abspielfassungen aneinanderhängen."""

import wave
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app import gespraech
from app.modell.transkript import ErzeugtMit, Marker, Segment, Sprecher, Transkript, Wort
from app.sprechererkennung import Schwellen

S = Schwellen()


def _bisher() -> Transkript:
    return Transkript(name="Runde", dauer_s=60.0, wellenform=[10] * 8,
                      sprecher=[Sprecher(kennung="s1", name="Anna", abdruck=[1.0, 0.0, 0.0]),
                                Sprecher(kennung="s2", name="Herr Krüger", abdruck=[0.0, 1.0, 0.0])],
                      segmente=[Segment(start=0, ende=5, sprecher="s1", text="Guten Tag.", woerter=[Wort(wort="Guten", start=0, ende=1)]),
                                Segment(start=50, ende=58, sprecher="s2", text="Bis bald.")],
                      marker=[Marker(zeit=3, titel="Anfang")])


def test_anhaengen_mit_versatz_und_sprechern():
    bisher = _bisher()
    teil = gespraech.teil_eintrag(uuid4(), 20.0, bisher, datetime(2026, 11, 4, 15, 20, tzinfo=UTC))
    assert teil.nummer == 2 and teil.beginn_s == 60.0
    neu_sprecher = [Sprecher(kennung="s1", name="Sprecher 1", abdruck=[0.05, 0.99, 0.0]),     # klingt wie Herr Krüger
                    Sprecher(kennung="s2", name="Sprecher 2", abdruck=[0.0, 0.0, 1.0])]       # neu im Gespräch
    segmente = [Segment(start=1, ende=4, sprecher="s1", text="Wir sind wieder da.", woerter=[Wort(wort="Wir", start=1, ende=1.4)]),
                Segment(start=6, ende=9, sprecher="s2", text="Ich bin neu.")]
    t = gespraech.anhaengen(bisher, teil, segmente, neu_sprecher, [Marker(zeit=2, titel="Weiter")], [90] * 4, S)
    assert [(s.start, s.sprecher, s.text) for s in t.segmente[2:]] == [(61.0, "s2", "Wir sind wieder da."), (66.0, "s3", "Ich bin neu.")]
    assert t.segmente[2].woerter[0].start == 61.0
    assert t.segmente[0].text == "Guten Tag."                  # der bisherige Text bleibt, wie er ist
    assert [s.kennung for s in t.sprecher] == ["s1", "s2", "s3"] and t.sprecher[1].name == "Herr Krüger"
    assert t.sprecher[2].name == "Sprecher 3"
    assert t.dauer_s == 80.0 and [x.nummer for x in t.teile] == [2]
    assert [(m.zeit, m.titel) for m in t.marker] == [(3, "Anfang"), (62.0, "Weiter")]
    assert len(t.wellenform) == 8 and t.wellenform[:6] == [10] * 6 and t.wellenform[-1] == 90
    assert gespraech.naechster_teil(t) == 3
    zweiter = gespraech.teil_eintrag(uuid4(), 5.0, t, None)
    assert zweiter.nummer == 3 and zweiter.beginn_s == 80.0


def test_gleiches_profil_geht_vor_dem_abdruck():
    profil = uuid4()
    bisher = _bisher()
    bisher.sprecher[0] = bisher.sprecher[0].model_copy(update={"profil_id": profil})
    abbildung, alle = gespraech.sprecher_zuordnen(
        bisher.sprecher, [Sprecher(kennung="s1", name="Anna", profil_id=profil, abdruck=[0.0, 1.0, 0.0])], S)
    assert abbildung == {"s1": "s1"} and len(alle) == 2


def test_ohne_sprecher_bleibt_ohne():
    bisher = Transkript(name="Notiz", dauer_s=10, segmente=[Segment(start=0, ende=3, text="Eins.")])
    teil = gespraech.teil_eintrag(uuid4(), 4, bisher, None)
    t = gespraech.anhaengen(bisher, teil, [Segment(start=0.5, ende=2, text="Zwei.")], [], [], None, S)
    assert [(s.start, s.sprecher) for s in t.segmente] == [(0, None), (10.5, None)] and t.sprecher == []


def test_sprecherweg_wie_bisher():
    def mit(aus, sprecher=()):
        return Transkript(name="x", sprecher=list(sprecher), erzeugt_mit=ErzeugtMit(dienst="whisper", app="t", sprecher_aus=aus))
    assert gespraech.sprecher_wie_bisher(mit("ohne")) == ("ohne", None)
    assert gespraech.sprecher_wie_bisher(mit("stimmen")) == ("stimmen", None)
    assert gespraech.sprecher_wie_bisher(mit("pyannote")) == ("trennung", "pyannote")
    assert gespraech.sprecher_wie_bisher(mit("whisper")) == ("trennung", None)
    assert gespraech.sprecher_wie_bisher(Transkript(name="x")) == ("ohne", None)


def _wav(p: Path, frames: int) -> Path:
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x01\x00" * frames)
    return p


def test_abspielfassungen_aneinander(tmp_path: Path):
    ziel = gespraech.aneinanderhaengen([_wav(tmp_path / "a.wav", 44100), _wav(tmp_path / "b.wav", 22050)], tmp_path / "g.wav")
    with wave.open(str(ziel)) as w:
        assert w.getnframes() == 66150 and w.getframerate() == 44100
    assert gespraech.fassung_name("t", ["a-1", "b-1"]) != gespraech.fassung_name("t", ["a-1", "b-2"])


def test_rollen_der_teile():
    from app.ablage import orte
    assert [orte.teil_rolle(n) for n in (2, 3, 26, 27)] == ["teil_b", "teil_c", "teil_z", "teil_aa"]
    assert all(orte.teil_nummer(orte.teil_rolle(n)) == n for n in range(2, 60))
    assert orte.teil_zusatz(2, "Aufnahme.WEBM") == ".teil-2.webm"
