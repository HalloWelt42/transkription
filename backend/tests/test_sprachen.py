"""Sprachen: allein der Steckbrief des Hördienstes sagt, welche es gibt; ohne Angabe prüft die App nur die Form."""

import pytest

from appkern.leitstelle import NichtErreichbar
from appkern.leitstelle.modelle import Modell, Steckbrief

from app.sprachen import Sprachen, UnbekannteSprache, name


class Schein:
    def __init__(self, sprachen=None, fehler=False):
        self.sprachen, self.fehler, self.fragen = sprachen, fehler, 0

    async def steckbriefe(self, faehigkeit=None, **_):
        self.fragen += 1
        if self.fehler:
            raise NichtErreichbar("weg")
        return [Modell(id="anderer-dienst", steckbrief=Steckbrief(sprachen=["en"])),
                Modell(id="klangwerk-hoeren", steckbrief=Steckbrief(sprachen=self.sprachen or []))]


async def test_liste_aus_dem_steckbrief_mit_namen_und_erkennen_vorn():
    ls = Schein(["ru", "de", "en"])
    s = Sprachen(lambda: ls, lambda: "klangwerk-hoeren", lambda: "de")
    assert [(e.code, e.name) for e in await s.liste()] == [("auto", "Erkennen"), ("de", "Deutsch"), ("en", "Englisch"), ("ru", "Russisch")]
    await s.pruefen("ru")
    await s.pruefen("auto")
    with pytest.raises(UnbekannteSprache, match="Französisch"):
        await s.pruefen("fr")
    assert ls.fragen == 1                                    # gemerkt, nicht bei jeder Frage neu


async def test_ohne_angabe_oder_ohne_leitstelle_wird_nichts_abgewiesen():
    for ls in (Schein([]), Schein(fehler=True), None):
        s = Sprachen(lambda: ls, lambda: "klangwerk-hoeren", lambda: "de")
        await s.pruefen("ru")
        assert [e.code for e in await s.liste()] == ["auto", "de"]          # dann bleibt die eingestellte wählbar


def test_namen_aus_den_sprachdaten_sonst_kuerzel():
    assert (name("uk"), name("jw")) == ("Ukrainisch", "JW")
