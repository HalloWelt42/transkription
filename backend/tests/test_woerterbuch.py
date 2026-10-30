"""Fachwörter-Wörterbuch und Zusammenfügen an Satzenden (ohne Dienste)."""

import pytest

from app.modell.transkript import Segment, Wort
from app.modell.woerterbuch import START, Woerterbuch, hinweis
from app.zusammenfuegen import an_satzenden


def test_woerterbuch_bereinigt_und_nimmt_nur_neue_auf():
    wb = Woerterbuch(woerter=[" Qwen ", "qwen", "ComfyUI,", "", "Zigbee"])
    assert wb.woerter == ["ComfyUI", "Qwen", "Zigbee"]
    assert wb.dazu(["QWEN", "Ollama", "VAE."]) == ["Ollama", "VAE"]
    assert wb.woerter == ["ComfyUI", "Ollama", "Qwen", "VAE", "Zigbee"]
    with pytest.raises(ValueError):
        Woerterbuch(woerter=["x" * 61])
    assert "Qwen" in START


def test_hinweis_aus_stil_und_woertern():
    assert hinweis("Hallo, wie geht es?", ["Qwen", "VAE"]) == "Hallo, wie geht es? Fachwörter: Qwen, VAE."
    assert hinweis("", ["Qwen"]) == "Fachwörter: Qwen."
    assert hinweis("Satz.", []) == "Satz."


def seg(start, ende, text, sprecher=None):
    return Segment(start=start, ende=ende, text=text, sprecher=sprecher,
                   woerter=[Wort(wort=w, start=start, ende=ende) for w in text.split()])


def test_an_satzenden_zusammenfuegen():
    s = [seg(0, 5, "Wir brauchen das, um das"), seg(5.2, 9, "zum Laufen zu bringen."), seg(9.5, 12, "Gut."),
         seg(12.1, 14, "und dann", "s2"), seg(14.1, 16, "weiter.", "s1")]
    aus = an_satzenden(s)
    assert [x.text for x in aus] == ["Wir brauchen das, um das zum Laufen zu bringen.", "Gut.", "und dann", "weiter."]
    assert aus[0].start == 0 and aus[0].ende == 9 and len(aus[0].woerter) == 9


def test_an_satzenden_nicht_ueber_lange_pausen_oder_zu_lang():
    assert len(an_satzenden([seg(0, 5, "ohne punkt"), seg(8, 10, "weiter")])) == 2           # Pause 3 s
    lang = [seg(i * 10, i * 10 + 9.9, "klein ohne satzzeichen") for i in range(10)]
    aus = an_satzenden(lang)
    assert all(x.ende - x.start <= 40 for x in aus) and len(aus) == 3
