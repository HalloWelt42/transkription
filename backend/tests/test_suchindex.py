"""Suchindex: Eintragen, Teilwortsuche über Text und Marker, Filter nach Sprache und Sprecher, seitenweise,
Transkripte je Aufnahme, Notizen der Versionen, Entfernen."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from appkern.datenbank import Datenbank
from appkern.kellerwolke import Knoten

from app.modell.transkript import Aenderung, Marker, Quelle, Segment, Sprecher, Transkript
from app.suchindex import Suchindex, ausschnitt


def knoten(name: str, etag: str = "v1") -> Knoten:
    jetzt = datetime.now(UTC)
    return Knoten(id=uuid4(), name=f"{name}.transkript.json", typ="datei", pfad=f"Apps/T/Transkripte/{name}.transkript.json",
                  recht="schreiben", etag=etag, erstellt_am=jetzt, geaendert_am=jetzt)


def transkript(name: str, saetze: list[str], sprecher=("Anna",), sprache="de", alter_h=0, marker=()) -> Transkript:
    zeit = datetime.now(UTC) - timedelta(hours=alter_h)
    sp = [Sprecher(kennung=f"s{i + 1}", name=n) for i, n in enumerate(sprecher)]
    segs = [Segment(start=i * 10.0, ende=i * 10.0 + 8, text=t, sprecher=sp[i % len(sp)].kennung) for i, t in enumerate(saetze)]
    return Transkript(name=name, sprache=sprache, sprecher=sp, segmente=segs, geaendert_am=zeit, erstellt_am=zeit,
                      quelle=Quelle(knoten_id=uuid4(), pfad=f"Apps/T/Aufnahmen/{name}.wav"),
                      marker=[Marker(zeit=z, titel=t) for z, t in marker],
                      aenderung=Aenderung(was="erzeugt"))


@pytest.fixture
async def index():
    db = await Datenbank(":memory:").oeffnen()
    i = Suchindex(db)
    await i.einrichten()
    yield i
    await db.schliessen()


async def test_suche_findet_teilwoerter_marker_und_filtert(index):
    k12, kev, kmv = knoten("Folge 12"), knoten("Eigentümer"), knoten("Mieterverein")
    await index.eintragen(transkript("Folge 12", ["Die Nebenkostenabrechnung kam spät.", "Grundsteuer und Müll sind in den Nebenkosten gestiegen.", "Gut."],
                                     sprecher=("Anna", "Herr Krüger")), k12)
    await index.eintragen(transkript("Eigentümer", ["Vorschlag: Nebenkostenvorauszahlung anheben."], sprecher=("Bernd",),
                                     alter_h=48, marker=[(3725.0, "Nebenkosten Abstimmung")]), kev)
    await index.eintragen(transkript("Mieterverein", ["Ganz anderes Thema."], sprache="en", alter_h=96), kmv)

    alle = await index.seite()
    assert alle.gesamt == 3 and [e.name for e in alle.eintraege] == ["Folge 12", "Eigentümer", "Mieterverein"]

    s = await index.seite(suche="kosten")
    assert s.gesamt == 2 and [(e.name, e.treffer) for e in s.eintraege] == [("Folge 12", 2), ("Eigentümer", 2)]
    assert s.eintraege[0].fundstellen[0].zeit == 0.0 and "Nebenkostenabrechnung" in s.eintraege[0].fundstellen[0].ausschnitt
    assert {f.art for f in s.eintraege[1].fundstellen} == {"text", "marker"}
    assert (await index.seite(suche="MÜLL")).gesamt == 1                      # Groß- und Kleinschreibung egal
    assert (await index.seite(suche="Nebenkosten gestiegen")).gesamt == 1     # alle Begriffe in einer Fundstelle
    assert (await index.seite(suche="Gu")).gesamt == 1                        # kurz: über LIKE
    assert (await index.seite(suche='50% "x')).gesamt == 0                   # Sonderzeichen brechen nichts
    assert [e.name for e in (await index.seite(sprecher=["herr krüger"])).eintraege] == ["Folge 12"]
    assert [e.name for e in (await index.seite(sprache="en")).eintraege] == ["Mieterverein"]
    seite2 = await index.seite(ab=1, anzahl=1)
    assert seite2.gesamt == 3 and [e.name for e in seite2.eintraege] == ["Eigentümer"]
    assert set(await index.sprecher_namen()) == {"Anna", "Herr Krüger", "Bernd"}


async def test_neu_eintragen_ersetzt_und_entfernen_raeumt_auf(index):
    k = knoten("Folge 12", "v1")
    t = transkript("Folge 12", ["alter Text über Heizung"])
    await index.eintragen(t, k)
    quelle = str(t.quelle.knoten_id)
    k2 = k.model_copy(update={"etag": "v2"})
    t2 = t.model_copy(update={"segmente": [Segment(start=0, ende=1, text="neuer Text über Wasser")],
                              "aenderung": Aenderung(was="Text korrigiert", wer="chef")})
    await index.eintragen(t2, k2)
    assert (await index.seite(suche="Heizung")).gesamt == 0 and (await index.seite(suche="Wasser")).gesamt == 1
    assert (await index.lagen()) == {str(k.id): ("v2", k.pfad)}
    assert [e.id for e in (await index.zur_quelle([quelle]))[quelle]] == [k.id]
    notizen = await index.notizen(k.id)
    assert notizen["v1"].was == "erzeugt" and notizen["v2"].wer == "chef"
    await index.entfernen(k.id)
    assert (await index.seite()).gesamt == 0 and await index.notizen(k.id) == {} and await index.eintrag(k.id) is None


def test_ausschnitt():
    text = "Am Anfang stand etwas ganz anderes, dann kam die Nebenkostenabrechnung für das Jahr 2025 und noch viel mehr Text danach."
    a = ausschnitt(text, ["kosten"], rand=20)
    assert a.startswith("... ") and a.endswith(" ...") and "Nebenkostenabrechnung" in a
    assert ausschnitt("kurz", ["kurz"]) == "kurz"


async def test_suche_findet_namen_und_kurze_begriffe_mit_umlaut(index):
    """Der Name eines Transkripts ist suchbar (zählt aber nicht als Treffer im Text); kurze Begriffe mit Umlaut finden
    jede Schreibweise ("äh" auch "Äh")."""
    await index.eintragen(transkript("REKO 2026 Januar", ["Äh, wir fangen an."]), knoten("REKO 2026 Januar"))
    await index.eintragen(transkript("Sprachnotiz", ["Der Reko-Termin ist verschoben, äh, auf Montag."]), knoten("Sprachnotiz"))

    s = await index.seite(suche="reko")
    assert {(e.name, e.treffer, e.im_namen) for e in s.eintraege} == {("REKO 2026 Januar", 0, True), ("Sprachnotiz", 1, False)}
    assert all(f.art != "name" for e in s.eintraege for f in e.fundstellen)   # der Name ist keine Fundstelle mit Zeit
    for begriff in ("äh", "Äh", "ÄH"):
        assert (await index.seite(suche=begriff)).gesamt == 2, begriff
