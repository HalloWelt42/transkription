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


async def test_anlegen_lesen_schreiben_versionen_zurueckholen(umgebung):
    kw, transkripte, index, _, angelegt = umgebung
    name = f"Probe {secrets.token_hex(3)}"
    ich = await kw.ich()
    await kw.ordner(f"{ich.zweig}/Aufnahmen")
    aufnahme = await kw.schreiben(f"{ich.zweig}/Aufnahmen/{name}.wav", b"RIFF", nur_neu=True, inhaltstyp="audio/wav")
    angelegt.append(aufnahme.id)
    erst = await transkripte.anlegen(probe(name, "Erster Text"), aufnahme)
    zweit = await transkripte.anlegen(probe(name, "Gleicher Name"), aufnahme)
    angelegt += [erst.id, zweit.id]
    assert erst.name == f"{name}.transkript.json" and zweit.name == f"{name} (2).transkript.json"
    assert {k.id for k in await transkripte.zur_quelle(aufnahme.id)} == {erst.id, zweit.id}
    assert any(h.art == "transkript_zu" and h.von_id == aufnahme.id for h in await kw.herkunft(erst.id))

    t, k = await transkripte.lesen(erst.id)
    neu = t.model_copy(update={"segmente": [Segment(start=0, ende=2, sprecher="s1", text="Geänderter Text")]})
    _, k2 = await transkripte.schreiben(erst.id, neu, k.etag, Aenderung(was="Text geändert", wer="chef"))
    with pytest.raises(StandVeraltet):
        await transkripte.schreiben(erst.id, neu, k.etag, Aenderung(was="mit altem Stand"))
    versionen = await transkripte.versionen(erst.id)
    assert len(versionen) == 2 and versionen[0].id.hex == k2.etag.replace("-", "")
    assert (await transkripte.version(erst.id, versionen[1].id)).segmente[0].text == "Erster Text"
    _, k3 = await transkripte.zurueckholen(erst.id, versionen[1].id, k2.etag, "chef")
    t3, _ = await transkripte.lesen(erst.id)
    assert t3.segmente[0].text == "Erster Text" and "zurückgeholt" in t3.aenderung.was and k3.etag != k2.etag


async def test_abgleich_folgt_der_kellerwolke(umgebung):
    kw, transkripte, index, abgleich, angelegt = umgebung
    wort = f"Zauberwort{secrets.token_hex(3)}"
    vorher = await transkripte.anlegen(probe(f"Vorher {wort}", f"{wort} ist schon da"))
    angelegt.append(vorher.id)
    await abgleich.verbunden()
    await asyncio.wait_for(abgleich.bereit.wait(), 30)
    assert [e.id for e in (await index.seite(suche=wort)).eintraege] == [vorher.id]

    # danach: neu, geändert (außerhalb der App, etwa von einer anderen App), gelöscht
    neu = await transkripte.anlegen(probe(f"Neu {wort}", f"{wort} kam später"))
    angelegt.append(neu.id)
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
    await kw.loeschen(neu.id)
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
