"""Verbund: Transkription und Kellerwolke (Entscheidung 17.10.2026) gegen die echte Entwicklungs-Kellerwolke und eine
nachgestellte Leitstelle.

- aus dem Dateimenü der Kellerwolke transkribieren: eine Datei außerhalb der App, das Transkript kommt neben sie, die
  App darf sie nur für diesen Auftrag lesen;
- in der App aus der ganzen Kellerwolke wählen und mit Optionen transkribieren;
- eine Datei über eine Anfrage öffnen und bearbeiten (Ton, Transkript, neue Version);
- die frühere getrennte Ablage zusammenführen (Vorschau, dann Auftrag; nichts wird gelöscht).
Am Ende liegt alles Angelegte im Papierkorb.
"""

import asyncio
import secrets
from pathlib import Path

import httpx
import pytest

from app.main import app_bauen
from app.modell.transkript import Aenderung, Quelle, Segment, Transkript
from appkern.ton import programm
from tests.hilfen import HAT_KELLERWOLKE, W, aktionen_zurueckziehen
from tests.test_verbund import Weiche, warten

pytestmark = pytest.mark.skipif(not (HAT_KELLERWOLKE and W.get("KELLERWOLKE_KENNUNG")),
                                reason="keine Test-Kellerwolke eingerichtet (backend/.env.test)")


async def _ton(ziel: Path, sekunden: int = 20) -> bytes:
    erzeugen = await asyncio.create_subprocess_exec(
        programm("ffmpeg"), "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        f"aevalsrc='if(lt(mod(t,4),3),0.4*sin(2*PI*330*t),0)':s=16000:d={sekunden}", str(ziel))
    assert await erzeugen.wait() == 0
    return ziel.read_bytes()


@pytest.fixture
async def verbund(tmp_path: Path):
    """App mit Schein-Leitstelle, angemeldet; dazu die Sitzung des Kontos in der Kellerwolke selbst und ein Ordner des
    Kontos außerhalb der Rechte der App."""
    ton = await _ton(tmp_path / "probe.mp3")
    app = app_bauen(tmp_path / "daten", transport=Weiche(tmp_path / "tondienst"))
    g = app.state.geruest
    await g.starten()
    kw_client = httpx.AsyncClient(base_url=W["KELLERWOLKE_ADRESSE"], timeout=60)
    r = await kw_client.post("/api/v1/auth/login", json={"kennung": W["KELLERWOLKE_KENNUNG"], "passwort": W["KELLERWOLKE_PASSWORT"]})
    konto = {"X-Kellerwolke-Sitzung": r.json()["token"]}
    name = f"Transkription Probe {secrets.token_hex(3)}"
    fremd = (await kw_client.post("/api/v1/dateien/ordner", json={"name": name, "parent_id": None}, headers=konto)).json()
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=60)
    r = await c.post("/api/v1/einrichtung", json={"kellerwolke_adresse": W["KELLERWOLKE_ADRESSE"],
                                                  "kellerwolke_schluessel": W["KELLERWOLKE_SCHLUESSEL"]})
    assert r.status_code in (200, 409), r.text
    r = await c.post("/api/v1/anmeldung", json={"kennung": W["KELLERWOLKE_KENNUNG"], "passwort": W["KELLERWOLKE_PASSWORT"]})
    h = {"X-Kellerwolke-Sitzung": r.json()["token"]}
    r = await c.patch("/api/v1/einstellungen", headers=h, json={"werte": {
        "leitstelle_adresse": "http://ls.test", "leitstelle_schluessel": "ls_probe", "abschnitt_min": 2}})
    assert r.status_code == 200, r.text
    # wie die Oberfläche nach der Anmeldung: die App trägt ihre Adresse ein (für Öffnen aus der Kellerwolke)
    assert (await c.post("/api/v1/adresse", headers=h, json={"adresse": "http://t"})).status_code == 200
    angelegt: list[str] = []
    try:
        yield app, g, c, h, kw_client, konto, fremd, ton, angelegt
    finally:
        await c.post("/api/v1/anmeldung/abmelden", headers=h)
        for k in angelegt:
            try:
                await g.kellerwolke.loeschen(k)
            except Exception:  # noqa: BLE001 - schon weg
                pass
        await kw_client.delete(f"/api/v1/dateien/{fremd['id']}", headers=konto)
        await kw_client.post("/api/v1/auth/logout", headers=konto)
        await kw_client.aclose()
        await c.aclose()
        await g.stoppen()
        await aktionen_zurueckziehen()


async def _hochladen_fremd(kw_client, konto, fremd, name: str, inhalt: bytes) -> dict:
    r = await kw_client.post("/api/v1/dateien/upload", files={"datei": (name, inhalt, "audio/mpeg")},
                             data={"parent_id": fremd["id"]}, headers=konto)
    assert r.status_code == 200, r.text
    return r.json()


async def _anfrage_bis(kw_client, konto, anfrage_id: str, sekunden: float = 60) -> dict:
    for _ in range(int(sekunden * 10)):
        stand = next((a for a in (await kw_client.get("/api/v1/anfragen", headers=konto)).json() if a["id"] == anfrage_id), None)
        if stand and stand["zustand"] in ("fertig", "fehler", "abgebrochen"):
            return stand
        await asyncio.sleep(0.1)
    pytest.fail("Anfrage wurde nicht fertig")


async def test_aus_dem_dateimenue_der_kellerwolke(verbund):
    app, g, c, h, kw_client, konto, fremd, ton, _ = verbund
    datei = await _hochladen_fremd(kw_client, konto, fremd, "Elternabend.mp3", ton)
    app_name = (await g.kellerwolke.ich()).app
    # die App hat ihre Aktionen gemeldet: Öffnen und Transkribieren passen zu Ton
    aktionen = []
    for _ in range(100):
        aktionen = [a for a in (await kw_client.get(f"/api/v1/dateien/{datei['id']}/aktionen", headers=konto)).json()
                    if a["app"] == app_name]
        if {a["kennung"] for a in aktionen} >= {"transkribieren", "oeffnen"}:
            break
        await asyncio.sleep(0.1)
    transkribieren = next(a for a in aktionen if a["kennung"] == "transkribieren")
    assert {a["kennung"] for a in aktionen} >= {"transkribieren", "oeffnen"} and transkribieren["erreichbar"]
    neu = (await kw_client.post("/api/v1/anfragen", headers=konto, json={
        "zugang_id": transkribieren["zugang_id"], "aktion": "transkribieren", "knoten_id": datei["id"]})).json()["anfrage"]
    stand = await _anfrage_bis(kw_client, konto, neu["id"])
    assert stand["zustand"] == "fertig", stand
    assert stand["ergebnis_name"] == "Elternabend.transkript.json"
    # das Transkript liegt neben der Datei, als ihr Begleiter; im Verzeichnis der App steht es nicht
    kinder = {k["name"]: k for k in (await kw_client.get("/api/v1/dateien", params={"parent_id": fremd["id"]}, headers=konto)).json()}
    assert kinder["Elternabend.transkript.json"]["haupt_id"] == datei["id"]
    assert stand["ergebnis_id"] not in [e["id"] for e in (await c.get("/api/v1/transkripte", headers=h)).json()["eintraege"]]
    # die App kommt danach nicht mehr an die Datei
    assert (await c.get(f"/api/v1/aufnahmen/{datei['id']}", headers=h)).status_code == 404


async def test_waehlen_mit_optionen_und_oeffnen(verbund):
    app, g, c, h, kw_client, konto, fremd, ton, _ = verbund
    datei = await _hochladen_fremd(kw_client, konto, fremd, "Interview.mp3", ton)
    seite = (await c.get("/api/v1/kellerwolke/wahl", params={"ordner": fremd["id"]}, headers=h)).json()
    assert [e["name"] for e in seite["eintraege"]] == ["Interview.mp3"]
    r = await c.post("/api/v1/kellerwolke/transkribieren", headers=h, json={"knoten_ids": [datei["id"]], "sprecher": "stimmen"})
    assert r.status_code == 201, r.text
    a = await warten(c, h, r.json()[0])
    assert a["zustand"] == "fertig", a.get("fehler")
    tid = a["ergebnis"]["transkript_id"]
    assert a["eingabe"]["sprecher"] == "stimmen"
    # die Anfrage zum Auftrag ist fertig, ihr Recht vorbei
    await asyncio.sleep(0.5)
    erledigt = next(x for x in (await kw_client.get("/api/v1/anfragen", headers=konto)).json() if x["ergebnis_id"] == tid)
    assert erledigt["zustand"] == "fertig"
    assert (await c.get(f"/api/v1/transkripte/{tid}", headers=h)).status_code == 404
    # in der Wahl steht das Transkript als Begleiter der Datei (die Oberfläche zeigt daran "transkribiert")
    seite = (await c.get("/api/v1/kellerwolke/wahl", params={"ordner": fremd["id"]}, headers=h)).json()
    begleiter = next(e for e in seite["eintraege"] if e["id"] == tid)
    assert (begleiter["haupt_id"], begleiter["rolle"]) == (datei["id"], "transkript")

    # öffnen: eine Anfrage zum Öffnen, die App nimmt sie an und zeigt Ton und Transkript mit ihrem Recht
    for _ in range(100):                              # die Adresse der App ist gemeldet, Öffnen wird angeboten
        r = await c.post("/api/v1/kellerwolke/wahl", headers=h, json={"knoten_id": datei["id"], "aktion": "oeffnen"})
        if r.status_code == 200:
            break
        await asyncio.sleep(0.1)
    assert r.status_code == 200, r.text
    gewaehlt = r.json()
    anfrage = gewaehlt["anfrage"]["id"]
    assert (await c.post(f"/api/v1/kellerwolke/anfragen/{anfrage}/oeffnen", headers=h)).json()["zustand"] == "laeuft"
    stand = (await c.get(f"/api/v1/kellerwolke/anfragen/{anfrage}", headers=h)).json()
    assert stand["art"] == "oeffnen" and stand["knoten_id"] == datei["id"] and stand["gueltig_bis"]
    aufnahme = (await c.get(f"/api/v1/aufnahmen/{datei['id']}", params={"anfrage": anfrage}, headers=h)).json()
    assert aufnahme["stand"] == "transkribiert" and aufnahme["transkripte"][0]["id"] == tid
    r = await c.get(f"/api/v1/inhalt/aufnahmen/{datei['id']}/ton", params={"anfrage": anfrage}, headers={**h, "Range": "bytes=0-43"})
    assert r.status_code == 206 and r.content[:4] == b"RIFF"
    t = (await c.get(f"/api/v1/transkripte/{tid}", params={"anfrage": anfrage}, headers=h)).json()
    r = await c.patch(f"/api/v1/transkripte/{tid}", params={"anfrage": anfrage}, headers=h,
                      json={"stand": t["stand"], "name": "Interview Schulleitung"})
    assert r.status_code == 200 and r.json()["transkript"]["name"] == "Interview Schulleitung"
    # auch außerhalb des eigenen Baums sagen die Versionen, was geschah
    versionen = (await c.get(f"/api/v1/transkripte/{tid}/versionen", params={"anfrage": anfrage}, headers=h)).json()
    assert versionen[0]["notiz"]["was"] and versionen[-1]["notiz"]["was"] == "erzeugt"
    # ein Auftrag mit dem Recht der geöffneten Datei schließt die Anfrage nicht
    a = await warten(c, h, (await c.post(f"/api/v1/transkripte/{tid}/korrigieren", params={"anfrage": anfrage}, headers=h)).json()["id"])
    assert a["zustand"] == "fertig", a.get("fehler")
    await asyncio.sleep(0.5)
    assert (await c.get(f"/api/v1/transkripte/{tid}", params={"anfrage": anfrage}, headers=h)).status_code == 200
    # ohne Anfrage kein Zugriff
    assert (await c.get(f"/api/v1/transkripte/{tid}", headers=h)).status_code == 404


async def test_zusammenfuehren_der_frueheren_ablage(verbund):
    app, g, c, h, kw_client, konto, fremd, ton, angelegt = verbund
    kw = g.kellerwolke
    zweig = (await kw.ich()).zweig
    lauf = f"Alt {secrets.token_hex(2)}"
    ordner_aufnahmen = await kw.ordner(f"{zweig}/Aufnahmen/{lauf}")
    alt = await kw.ordner(f"{zweig}/Transkripte/{lauf}")
    # beide Ordner gleich zum Aufräumen (mit Inhalt in den Papierkorb), auch wenn der Test unterwegs scheitert;
    # sonst sammeln sich leere Ordner im Testzweig und der erste Abgleich wird mit jedem Lauf langsamer (HELF-58)
    angelegt += [str(ordner_aufnahmen.id), str(alt.id)]
    aufnahme = await kw.schreiben(f"{ordner_aufnahmen.pfad}/Runde.mp3", ton, nur_neu=True, inhaltstyp="audio/mpeg")
    angelegt += [str(aufnahme.id)]

    def transkript(name: str, quelle) -> bytes:
        return Transkript(name=name, quelle=Quelle(knoten_id=quelle, pfad="") if quelle else None, sprache="de", dauer_s=2.0,
                          segmente=[Segment(start=0, ende=2, text=name)],
                          aenderung=Aenderung(was="früher")).model_dump_json().encode()

    neuer = await kw.schreiben(f"{alt.pfad}/Runde (2).transkript.json", transkript("Runde neu", aufnahme.id), nur_neu=True)
    await asyncio.sleep(1.1)
    neuster = await kw.schreiben(f"{alt.pfad}/Runde.transkript.json", transkript("Runde neuer", aufnahme.id), nur_neu=True)
    waise = await kw.schreiben(f"{alt.pfad}/Ohne Ton.transkript.json", transkript("Ohne Ton", None), nur_neu=True)
    notiz = await kw.schreiben(f"{alt.pfad}/Notiz.txt", b"bleibt", nur_neu=True, inhaltstyp="text/plain")
    angelegt += [str(neuer.id), str(neuster.id), str(waise.id), str(notiz.id)]

    plan = (await c.get("/api/v1/ablage/zusammenfuehren", headers=h)).json()
    eigene = {s["knoten_id"]: s for s in plan["schritte"]}
    assert plan["noetig"] and eigene[str(neuster.id)]["art"] == "begleiter" and eigene[str(neuer.id)]["art"] == "daneben"
    assert eigene[str(waise.id)]["art"] == "ohne_aufnahme" and eigene[str(waise.id)]["nach"].endswith(f"/Aufnahmen/{lauf}/Ohne Ton.transkript.json")
    assert str(notiz.id) not in eigene and not any(s["art"] == "ordner" for s in plan["schritte"])   # andere Dateien bleiben

    a = await warten(c, h, (await c.post("/api/v1/ablage/zusammenfuehren", headers=h)).json()["id"])
    assert a["zustand"] == "fertig", a.get("fehler")
    begleiter = await kw.begleiter(aufnahme.id)
    assert [(b.id, b.name, b.rolle) for b in begleiter] == [(neuster.id, "Runde.transkript.json", "transkript")]
    assert (await kw.knoten(neuer.id)).pfad.endswith(f"/Aufnahmen/{lauf}/Runde (2).transkript.json")
    assert (await kw.knoten(waise.id)).pfad.endswith(f"/Aufnahmen/{lauf}/Ohne Ton.transkript.json")
    assert (await kw.knoten(notiz.id)).pfad == f"{alt.pfad}/Notiz.txt"
    assert (await c.get("/api/v1/ablage/zusammenfuehren", headers=h)).json()["noetig"] is False   # nur noch die Notiz dort
