"""Sprechererkennung mit künstlichen Abdrücken: Trennung nach Überlappung, Gruppieren ohne Trennung (auch mit
vorgegebener Zahl), kleine Gruppen, Zusammenlegen, Erben, Profilabgleich (sicher, Vorschlag, jedes Profil einmal)."""

import numpy as np

from app.dienste import Wechsel, segmente_aus
from app.modell.sprecherprofil import Profil, Profile
from app.modell.transkript import Segment
from app.sprechererkennung import Schwellen, erben, erkennen, gruppieren, nach_trennung, zusammenlegen

RNG = np.random.default_rng(7)
A, B, C = (RNG.normal(size=192) for _ in range(3))


def stimme(basis, rauschen=0.25):
    return list(basis + RNG.normal(scale=rauschen * np.linalg.norm(basis) / np.sqrt(192), size=192))


def segs(n, laenge=4.0):
    return [Segment(start=i * laenge, ende=i * laenge + laenge - 0.2, text=f"Satz {i}") for i in range(n)]


def test_nach_trennung_groesste_ueberlappung():
    s = segs(3)
    w = [Wechsel(0, 5, "SPEAKER_00"), Wechsel(5, 7.9, "SPEAKER_01"), Wechsel(3.9, 4.1, "SPEAKER_01")]
    assert nach_trennung(s, w) == ["SPEAKER_00", "SPEAKER_01", None]


def test_gruppieren_findet_zwei_stimmen_und_haengt_kleine_an():
    folge = [A, A, B, A, B, B, A, B] + [C]                  # C nur einmal, kurz: kommt in die ähnlichste Gruppe
    abdruecke = [stimme(v) for v in folge] + [None]
    labels = gruppieren(abdruecke, segs(10), 0.6)
    assert labels[:8] == ["G0", "G0", "G1", "G0", "G1", "G1", "G0", "G1"] and labels[8] in ("G0", "G1")
    assert labels[9] is None
    drei = gruppieren([stimme(v) for v in [A, B, C, A, B, C]], segs(6, 10), 0.99, anzahl=3)
    assert len(set(drei)) == 3 and drei[0] == drei[3] and drei[1] == drei[4]


def test_zusammenlegen_und_erben():
    abdruecke = [stimme(A), stimme(A), stimme(B), stimme(A)]
    assert zusammenlegen(["x", "y", "z", "x"], abdruecke, 0.6) == ["x", "x", "z", "x"]
    assert erben([None, "a", None, "b", None]) == ["a", "a", "a", "b", "b"]
    assert erben([None, None]) == [None, None]


def test_erkennen_mit_profilen_sicher_vorschlag_und_jedes_profil_einmal():
    anna = Profil(name="Anna", abdruck=list(A), proben=5)
    anna_zwilling = Profil(name="Anna 2", abdruck=list(A), proben=1)
    halb = Profil(name="Bernd?", abdruck=list(0.6 * B / np.linalg.norm(B) + 0.8 * C / np.linalg.norm(C)), proben=1)
    folge = [A, B, A, B, A]
    neu, sprecher = erkennen(segs(5, 10), [stimme(v, 0.1) for v in folge], None, Profile(profile=[anna, anna_zwilling, halb]),
                             Schwellen())
    assert [s.sprecher for s in neu] == ["s1", "s2", "s1", "s2", "s1"]
    s1, s2 = sprecher
    assert s1.name in ("Anna", "Anna 2") and s1.profil_id in (anna.id, anna_zwilling.id) and s1.aehnlichkeit > 0.9
    assert s2.name == "Sprecher 2" and s2.profil_id is None and s2.vorschlag_id == halb.id and 0.5 <= s2.vorschlag_aehnlichkeit < 0.7
    assert len(s1.abdruck) == 192


def test_erkennen_mit_trennung_und_segmente_aus_dem_hoerdienst():
    roh = [{"start": 0.0, "end": 3.0, "text": " Guten Tag ", "words": [{"word": " Guten", "start": 0.0, "end": 0.4},
                                                                       {"word": " Tag", "start": 0.5, "end": 0.9}]},
           {"start": 3.2, "end": 6.0, "text": "Hallo", "words": []}, {"start": 6, "end": 7, "text": "  "}]
    s = segmente_aus(roh, versatz=600.0)
    assert [x.text for x in s] == ["Guten Tag", "Hallo"] and s[0].start == 600.0 and s[0].woerter[1].wort == "Tag"
    neu, sprecher = erkennen(s, [None, None], [Wechsel(600, 603, "SPEAKER_01"), Wechsel(603.1, 606, "SPEAKER_00")],
                             Profile(), Schwellen())
    assert [x.sprecher for x in neu] == ["s1", "s2"] and [p.name for p in sprecher] == ["Sprecher 1", "Sprecher 2"]


def test_an_wechseln_teilen_nach_wortzeiten():
    from app.modell.transkript import Wort
    from app.sprechererkennung import an_wechseln_teilen
    woerter = [Wort(wort=f"w{i}", start=i * 0.5, ende=i * 0.5 + 0.4) for i in range(10)]   # 0 bis 4,9 s
    seg = Segment(start=0.0, ende=4.9, text=" ".join(w.wort for w in woerter), woerter=woerter)
    wechsel = [Wechsel(0.0, 2.2, "A"), Wechsel(2.3, 3.9, "B"), Wechsel(4.1, 5.0, "A")]
    teile = an_wechseln_teilen([seg], wechsel)
    assert [t.text for t in teile] == ["w0 w1 w2 w3 w4", "w5 w6 w7", "w8 w9"]
    assert (teile[1].start, teile[1].ende) == (2.5, 3.9) and [w.wort for w in teile[2].woerter] == ["w8", "w9"]
    assert nach_trennung(teile, wechsel) == ["A", "B", "A"]
    ohne_woerter = Segment(start=0.0, ende=4.0, text="x")
    assert an_wechseln_teilen([ohne_woerter], wechsel) == [ohne_woerter]
