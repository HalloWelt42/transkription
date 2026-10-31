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


def test_aufnahme_eines_transkripts():
    """Die Begleiter-Beziehung geht vor der Angabe in der Datei; ohne beides gibt es keine Aufnahme."""
    from datetime import datetime, timezone
    from uuid import uuid4

    from appkern.kellerwolke import Knoten

    from app.ablage.transkripte import aufnahme_id
    from app.modell.transkript import Quelle, Transkript

    jetzt = datetime.now(timezone.utc)

    def knoten(haupt=None) -> Knoten:
        return Knoten(id=uuid4(), name="Runde.transkript.json", typ="datei", pfad="Apps/T/Runde.transkript.json",
                      recht="schreiben", haupt_id=haupt, erstellt_am=jetzt, geaendert_am=jetzt)

    haupt, alt = uuid4(), uuid4()
    mit_quelle = Transkript(name="Runde", quelle=Quelle(knoten_id=alt, pfad="Transkripte/Runde.wav"))
    assert aufnahme_id(mit_quelle, knoten(haupt)) == haupt
    assert aufnahme_id(mit_quelle, knoten()) == alt
    assert aufnahme_id(Transkript(name="Runde"), knoten(haupt)) == haupt
    assert aufnahme_id(Transkript(name="Runde"), knoten()) is None


def test_anfrage_einer_anderen_app_gibt_sprache_mit():
    from uuid import uuid4

    from appkern.anfragen import AnfrageEingabe

    from app.arten import eingabe_aus_anfrage
    e = AnfrageEingabe(anfrage_id=uuid4(), knoten_id=uuid4(), aktion="transkribieren",
                       optionen={"sprache": "en", "fremd": "egal"})
    t = eingabe_aus_anfrage(e)
    assert (t.sprache, t.sprecher, t.quelle_id) == ("en", None, e.knoten_id)
    assert eingabe_aus_anfrage(e.model_copy(update={"optionen": {}})).sprache is None   # dann gilt die Einstellung
    # jede Sprache in der Form ISO 639-1 (ob der Hördienst sie kann, prüft der Auftrag), nur keine andere Form
    assert eingabe_aus_anfrage(e.model_copy(update={"optionen": {"sprache": "ru"}})).sprache == "ru"
    with pytest.raises(ValidationError):
        eingabe_aus_anfrage(e.model_copy(update={"optionen": {"sprache": "russisch"}}))


# --- Fassungen je Hördienst (HELF-79) ---------------------------------------------------------------------------

def _gehoert(dienst: str, text: str, mit_sprecher: bool = False) -> Transkript:
    from app.modell.transkript import ErzeugtMit
    sprecher = [Sprecher(kennung="s1", name="Sprecher 1")] if mit_sprecher else []
    return Transkript(name="Folge", sprecher=sprecher, segmente=[seg(0, 2, text, "s1" if mit_sprecher else None)],
                      erzeugt_mit=ErzeugtMit(dienst=dienst, modell=dienst.upper(), app="t", hoeren_s=1.5))


def test_anderer_hoerdienst_wird_fassung_und_die_alte_bleibt():
    from app.modell.transkript import gehoert_einfuegen
    alt = _gehoert("klangwerk-hoeren", "alt")
    t, haupt = gehoert_einfuegen(alt, _gehoert("klangwerk-hoeren-moss", "moss", True))
    assert not haupt and t.segmente[0].text == "alt" and [f.erzeugt_mit.dienst for f in t.fassungen] == ["klangwerk-hoeren-moss"]
    assert t.fassungen[0].sprecher[0].kennung == "s1" and t.fassungen[0].erzeugt_mit.hoeren_s == 1.5
    t, _ = gehoert_einfuegen(t, _gehoert("klangwerk-hoeren-moss", "moss neu"))       # derselbe Dienst ersetzt seine Fassung
    t, _ = gehoert_einfuegen(t, _gehoert("klangwerk-hoeren-turbo", "turbo"))
    assert [f.segmente[0].text for f in t.fassungen] == ["moss neu", "turbo"] and t.segmente[0].text == "alt"
    t, haupt = gehoert_einfuegen(t, _gehoert("klangwerk-hoeren", "alt neu"))        # Dienst der Hauptfassung: neue Hauptfassung
    assert haupt and t.segmente[0].text == "alt neu" and len(t.fassungen) == 2


def test_mit_hauptfassung_rueckt_die_bisherige_unter_die_fassungen():
    from app.modell.transkript import gehoert_einfuegen
    t, haupt = gehoert_einfuegen(_gehoert("altbestand", "alt"), _gehoert("klangwerk-hoeren", "neu"), hauptfassung=True)
    assert haupt and t.segmente[0].text == "neu" and [f.segmente[0].text for f in t.fassungen] == ["alt"]


def test_zur_hauptfassung_tauscht_und_behaelt_marker():
    from app.modell.transkript import Marker, gehoert_einfuegen, zur_hauptfassung
    alt = _gehoert("klangwerk-hoeren", "alt").model_copy(update={"marker": [Marker(zeit=1, titel="Stelle")]})
    t, _ = gehoert_einfuegen(alt, _gehoert("klangwerk-hoeren-moss", "moss", True))
    neu = zur_hauptfassung(t, t.fassungen[0].id)
    assert neu.segmente[0].text == "moss" and neu.erzeugt_mit.dienst == "klangwerk-hoeren-moss" and neu.sprecher[0].kennung == "s1"
    assert [f.segmente[0].text for f in neu.fassungen] == ["alt"] and neu.marker[0].titel == "Stelle"
    with pytest.raises(KeyError):
        zur_hauptfassung(neu, t.fassungen[0].id)
    with pytest.raises(ValidationError):                                             # je Hördienst höchstens eine Fassung
        Transkript.model_validate({**neu.model_dump(), "fassungen": [neu.fassungen[0].model_dump()] * 2})


def test_sprecher_des_hoerdienstes_als_wechsel():
    from app.dienste import wechsel_aus
    roh = [{"start": 0.5, "end": 2, "text": "Hallo", "speaker": "S01"}, {"start": 2.5, "end": 4, "text": "Ja", "speaker": "S02"}]
    assert [(w.start, w.ende, w.sprecher) for w in wechsel_aus(roh, 600, "A2:")] == [(600.5, 602.0, "A2:S01"), (602.5, 604.0, "A2:S02")]
    assert wechsel_aus([{**roh[0], "speaker": None}, roh[1]]) == []                  # nicht für jedes Segment: keine
    assert wechsel_aus([{"start": 0, "end": 1, "text": "x", "words": []}]) == []
