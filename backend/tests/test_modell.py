"""Fachliches Modell: Transkriptdatei (Stimmigkeit, unbekannte Felder bleiben), Wortangleichung nach Textänderung,
Sprecherprofile (Mitteln, Ähnlichkeit, Zusammenführen)."""

import pytest
from pydantic import ValidationError

from app.modell.sprecherprofil import Probe, Profil, Profile, kosinus
from app.modell.transkript import Segment, Sprecher, Transkript, Wort, woerter_angleichen


def seg(start, ende, text, sprecher="s1", woerter=None):
    return Segment(start=start, ende=ende, text=text, sprecher=sprecher, woerter=woerter or [])


def test_transkript_sortiert_prueft_und_behaelt_unbekanntes():
    t = Transkript.model_validate({
        "name": "Folge 12", "sprecher": [{"kennung": "s1", "name": "Anna"}, {"kennung": "s2", "name": "Bernd"}],
        "segmente": [{"start": 5, "ende": 7, "sprecher": "s2", "text": "b"}, {"start": 1, "ende": 4, "sprecher": "s1", "text": "a"}],
        "zukunft": {"neu": True},
    })
    assert [s.text for s in t.segmente] == ["a", "b"]
    assert t.model_dump(mode="json")["zukunft"] == {"neu": True}
    assert t.anteile() == pytest.approx({"s1": 0.6, "s2": 0.4})
    assert t.neue_sprecherkennung() == "s3" and t.sprecher_name("s2") == "Bernd"
    with pytest.raises(ValidationError):
        Transkript(name="x", segmente=[seg(0, 1, "a", "s9")])
    with pytest.raises(ValidationError):
        Transkript(name="x", sprecher=[Sprecher(kennung="s1", name="A"), Sprecher(kennung="s1", name="B")])
    with pytest.raises(ValidationError):
        seg(3, 2, "rückwärts")


def test_woerter_bleiben_bei_gleichem_text():
    s = seg(0, 2, "Guten Tag", woerter=[Wort(wort="Guten", start=0, ende=0.5), Wort(wort="Tag", start=0.6, ende=1.0)])
    assert woerter_angleichen(s) is s


def test_woerter_nach_korrektur_behalten_ihre_zeit_und_neue_fuellen_luecken():
    alt = [Wort(wort="Dürfen", start=10.0, ende=10.3), Wort(wort="wir", start=10.3, ende=10.5),
           Wort(wort="ein", start=10.5, ende=10.7), Wort(wort="sehen?", start=10.7, ende=11.0),
           Wort(wort="Gut", start=11.5, ende=11.8)]
    s = seg(10.0, 12.0, "Dürfen wir einsehen? Gut.", woerter=alt)
    neu = woerter_angleichen(s).woerter
    assert [w.wort for w in neu] == ["Dürfen", "wir", "einsehen?", "Gut."]
    assert (neu[0].start, neu[1].start) == (10.0, 10.3)
    assert neu[3].start == 11.5                                   # nur Satzzeichen anders: Zeit bleibt
    assert 10.5 <= neu[2].start < neu[2].ende <= 11.5             # neu zwischen den Nachbarn


def test_woerter_ohne_anker_verteilen_die_segmentzeit():
    neu = woerter_angleichen(seg(4.0, 6.0, "ganz neuer Text")).woerter
    assert [(w.start, w.ende) for w in neu] == [(4.0, 4.667), (4.667, 5.333), (5.333, 6.0)]


def test_profile_mitteln_finden_und_zusammenfuehren():
    a = Profil(name="Anna")
    a.einmischen([1.0, 0.0], Probe(transkript_id="00000000-0000-0000-0000-000000000001", start=1, ende=3))
    a.einmischen([0.0, 1.0])
    assert a.abdruck == [0.5, 0.5] and a.proben == 2 and len(a.beispiele) == 1
    b = Profil(name="Bernd", abdruck=[-1.0, 0.0], proben=1)
    p = Profile(profile=[a, b])
    profil, wert = p.aehnlichstes([0.6, 0.4])
    assert profil.name == "Anna" and wert == pytest.approx(kosinus([0.5, 0.5], [0.6, 0.4]))
    ziel = p.zusammenfuehren(a.id, b.id)
    assert ziel.proben == 3 and ziel.abdruck == pytest.approx([0.0, 1 / 3]) and [x.name for x in p.profile] == ["Anna"]
    with pytest.raises(ValueError):
        a.einmischen([1.0, 2.0, 3.0])
