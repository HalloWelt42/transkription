"""Verbund: Ablage und Abgleich gegen die echte Entwicklungs-Kellerwolke (backend/.env.test). Jeder Lauf legt eigene
Transkripte an und am Ende in den Papierkorb des Kontos."""

import asyncio
import secrets
from types import SimpleNamespace
from uuid import uuid4

import pytest

from appkern.datenbank import Datenbank
from appkern.kellerwolke import Kellerwolke, StandVeraltet

from app.abgleich import Abgleich
from app.ablage.profile import Sprecherprofile
from app.ablage.transkripte import Transkripte
from app.modell.sprecherprofil import Profil
from app.modell.transkript import Aenderung, Segment, Sprecher, Transkript
from app.suchindex import Suchindex
from tests.hilfen import HAT_KELLERWOLKE, W

pytestmark = pytest.mark.skipif(not HAT_KELLERWOLKE, reason="keine Test-Kellerwolke eingerichtet (backend/.env.test)")


@pytest.fixture
async def umgebung():
    kw = Kellerwolke(W["KELLERWOLKE_ADRESSE"], W["KELLERWOLKE_SCHLUESSEL"])
    db = await Datenbank(":memory:").oeffnen()
    index = Suchindex(db)
    transkripte = Transkripte(lambda: kw)
    abgleich = Abgleich(SimpleNamespace(kellerwolke=kw), transkripte, index)
    await index.einrichten()
    angelegt: list = []
    yield kw, transkripte, index, abgleich, angelegt
    await abgleich.stoppen()
    for k in angelegt:
        try:
            await kw.loeschen(k)
        except Exception:  # noqa: BLE001 - schon weg
            pass
    await db.schliessen()
    await kw.schliessen()


def probe(name: str, text: str) -> Transkript:
    return Transkript(name=name, sprecher=[Sprecher(kennung="s1", name="Anna")],
                      segmente=[Segment(start=0, ende=2, sprecher="s1", text=text)], aenderung=Aenderung(was="erzeugt"))


async def _aufnahme(kw, angelegt, name: str):
    ich = await kw.ich()
    await kw.ordner(f"{ich.zweig}/Aufnahmen")
    aufnahme = await kw.schreiben(f"{ich.zweig}/Aufnahmen/{name}.wav", b"RIFF", nur_neu=True, inhaltstyp="audio/wav")
    angelegt.append(aufnahme.id)
    return aufnahme


async def test_ein_transkript_je_aufnahme_mit_versionen(umgebung):
    kw, transkripte, index, _, angelegt = umgebung
    name = f"Probe {secrets.token_hex(3)}"
    aufnahme = await _aufnahme(kw, angelegt, name)
    erst, k1 = await transkripte.speichern(probe(name, "Erster Text"), aufnahme, Aenderung(was="erzeugt"))
    # neu transkribiert: dieselbe Datei, eine neue Version; Name und Anlagezeit bleiben
    zweit, k2 = await transkripte.speichern(probe("anderer Name", "Zweiter Lauf"), aufnahme, Aenderung(was="erzeugt"),
                                            erneut=Aenderung(was="neu transkribiert"))
    assert k1.id == k2.id and k1.name == f"{name}.transkript.json" and k1.parent_id == aufnahme.parent_id
    assert (k2.haupt_id, k2.rolle) == (aufnahme.id, "transkript")
    assert zweit.name == name and zweit.aenderung.was == "neu transkribiert"
    assert (await transkripte.zur_quelle(aufnahme.id)).id == k1.id

    t, k = await transkripte.lesen(k1.id)
    neu = t.model_copy(update={"segmente": [Segment(start=0, ende=2, sprecher="s1", text="Geänderter Text")]})
    _, k3 = await transkripte.schreiben(k1.id, neu, k.etag, Aenderung(was="Text geändert", wer="chef"))
    with pytest.raises(StandVeraltet):
        await transkripte.schreiben(k1.id, neu, k.etag, Aenderung(was="mit altem Stand"))
    versionen = await transkripte.versionen(k1.id)
    assert len(versionen) == 3 and versionen[0].id.hex == k3.etag.replace("-", "")
    assert (await transkripte.version(k1.id, versionen[2].id)).segmente[0].text == "Erster Text"
    _, k4 = await transkripte.zurueckholen(k1.id, versionen[2].id, k3.etag, "chef")
    t4, _ = await transkripte.lesen(k1.id)
    assert t4.segmente[0].text == "Erster Text" and "zurückgeholt" in t4.aenderung.was and k4.etag != k3.etag


async def test_abgleich_folgt_der_kellerwolke(umgebung):
    kw, transkripte, index, abgleich, angelegt = umgebung
    wort = f"Zauberwort{secrets.token_hex(3)}"
    eins = await _aufnahme(kw, angelegt, f"Vorher {wort}")
    _, vorher = await transkripte.speichern(probe(f"Vorher {wort}", f"{wort} ist schon da"), eins, Aenderung(was="erzeugt"))
    await abgleich.verbunden()
    await asyncio.wait_for(abgleich.bereit.wait(), 30)
    assert [e.id for e in (await index.seite(suche=wort)).eintraege] == [vorher.id]

    # danach: neu, geändert (außerhalb der App, etwa von einer anderen App), gelöscht
    zwei = await _aufnahme(kw, angelegt, f"Neu {wort}")
    _, neu = await transkripte.speichern(probe(f"Neu {wort}", f"{wort} kam später"), zwei, Aenderung(was="erzeugt"))
    t, k = await transkripte.lesen(vorher.id)
    await transkripte.schreiben(vorher.id, t.model_copy(update={"segmente": [Segment(start=0, ende=1, text="ohne das Wort")]}),
                                k.etag, Aenderung(was="extern"))

    async def stand(erwartet):
        for _ in range(100):
            if {e.id for e in (await index.seite(suche=wort)).eintraege} == erwartet:
                return True
            await asyncio.sleep(0.1)
        return False

    assert await stand({neu.id})
    await kw.loeschen(zwei.id)                       # die Aufnahme nimmt ihr Transkript mit in den Papierkorb
    assert await stand(set())
    assert await index.eintrag(neu.id) is None


async def test_profile_aendern_mit_stand(umgebung):
    kw, *_ = umgebung
    profile = Sprecherprofile(lambda: kw)
    name = f"Probe {uuid4().hex[:6]}"
    pid = await profile.aendern(lambda p: (p.profile.append(Profil(name=name)), p.profile[-1].id)[1])
    gelesen, stand = await profile.lesen()
    assert gelesen.holen(pid).name == name and stand
    await profile.aendern(lambda p: setattr(p, "profile", [x for x in p.profile if x.id != pid]))
    assert (await profile.lesen())[0].holen(pid) is None
