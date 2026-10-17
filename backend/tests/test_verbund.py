"""Verbund: die ganze Transkription gegen die echte Entwicklungs-Kellerwolke (backend/.env.test) und eine
nachgestellte Leitstelle (Klangwerk und Sprachmodell). Ein Lauf: Aufnahme hochladen, transkribieren (zwei Abschnitte,
Sprechertrennung fehlt, also Gruppieren), lesen, suchen, ändern mit Stand, Versionen, Export, Profil, Korrektur,
Auswertung, Ton mit Bereichen, Zugriff einer anderen App. Am Ende liegt alles Angelegte im Papierkorb."""

import asyncio
import json
import re
import secrets
from pathlib import Path

import httpx
import numpy as np
import pytest

from app.main import app_bauen
from app.ton import programm
from tests.hilfen import HAT_KELLERWOLKE, W

pytestmark = pytest.mark.skipif(not (HAT_KELLERWOLKE and W.get("KELLERWOLKE_KENNUNG")),
                                reason="keine Test-Kellerwolke eingerichtet (backend/.env.test)")
RNG = np.random.default_rng(3)
STIMMEN = [list(RNG.normal(size=192)), list(RNG.normal(size=192))]


def leitstelle(request: httpx.Request) -> httpx.Response:
    """Klangwerk und Sprachmodell zum Schein: je Abschnitt zwei Sätze, Stimmen im Wechsel, keine Sprechertrennung."""
    pfad = request.url.path
    if pfad == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "klein"}]})
    if pfad.endswith("/stt"):
        woerter = lambda text, a: [{"word": f" {w}", "start": a + i * 0.4, "end": a + i * 0.4 + 0.3} for i, w in enumerate(text.split())]  # noqa: E731
        return httpx.Response(200, json={"language": "de", "model": "Schein", "segments": [
            {"start": 0.0, "end": 2.6, "text": " Hallo Welt wie geht es", "words": woerter("Hallo Welt wie geht es", 0.0)},
            {"start": 4.0, "end": 6.6, "text": " Zweiter Satz mit Nebenkosten", "words": woerter("Zweiter Satz mit Nebenkosten", 4.0)}]})
    if pfad.endswith("/speaker/embed"):
        segmente = json.loads(re.search(rb'name="segments"\r\n\r\n(.*?)\r\n', request.content, re.S).group(1))
        return httpx.Response(200, json={"embeddings": [STIMMEN[i % 2] for i in range(len(segmente))], "dim": 192})
    if pfad.endswith("/speaker/diarize"):
        return httpx.Response(503, json={"detail": "Modell ist nicht bereit (ohne_zugang)"})
    if pfad == "/v1/chat/completions":
        nachrichten = json.loads(request.content)["messages"]
        if "korrigierst" in nachrichten[0]["content"]:
            zeilen = re.findall(r"^\[(\d+)\] (.*)$", nachrichten[1]["content"], re.M)
            text = "\n".join(f"[{n}] {t.replace('Hallo Welt', 'Hallo, Welt,')}" for n, t in zeilen)
        else:
            text = "## Zusammenfassung\n\nZwei Sätze zum Schein."
        return httpx.Response(200, json={"model": "klein", "choices": [{"message": {"content": text}, "finish_reason": "stop"}]})
    return httpx.Response(404, json={"detail": f"unbekannt: {pfad}"})


class Weiche(httpx.AsyncBaseTransport):
    """Leitstelle zum Schein, alles andere echt."""

    def __init__(self):
        self.echt = httpx.AsyncHTTPTransport()
        self.schein = httpx.MockTransport(leitstelle)

    async def handle_async_request(self, request):
        ziel = self.schein if request.url.host == "ls.test" else self.echt
        return await ziel.handle_async_request(request)

    async def aclose(self):
        await self.echt.aclose()


async def warten(c, h, auftrag_id: str) -> dict:
    for _ in range(600):
        a = (await c.get(f"/api/v1/auftraege/{auftrag_id}", headers=h)).json()
        if a["zustand"] in ("fertig", "fehler", "abgebrochen"):
            return a
        await asyncio.sleep(0.05)
    pytest.fail("Auftrag wurde nicht fertig")


async def test_ganzer_ablauf(tmp_path: Path):
    ton = tmp_path / "probe.mp3"
    erzeugen = await asyncio.create_subprocess_exec(
        programm("ffmpeg"), "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        "aevalsrc='if(lt(mod(t,4),3),0.4*sin(2*PI*330*t),0)':s=16000:d=150", str(ton))
    assert await erzeugen.wait() == 0

    app = app_bauen(tmp_path / "daten", transport=Weiche())
    g = app.state.geruest
    await g.starten()
    angelegt: list[str] = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=60) as c:
            r = await c.post("/api/v1/einrichtung", json={"kellerwolke_adresse": W["KELLERWOLKE_ADRESSE"],
                                                          "kellerwolke_schluessel": W["KELLERWOLKE_SCHLUESSEL"]})
            assert r.status_code == 200, r.text
            r = await c.post("/api/v1/anmeldung", json={"kennung": W["KELLERWOLKE_KENNUNG"], "passwort": W["KELLERWOLKE_PASSWORT"]})
            h = {"X-Kellerwolke-Sitzung": r.json()["token"]}
            try:
                r = await c.patch("/api/v1/einstellungen", headers=h, json={"werte": {
                    "leitstelle_adresse": "http://ls.test", "leitstelle_schluessel": "ls_probe", "abschnitt_min": 2}})
                assert r.status_code == 200, r.text

                # Aufnahme hochladen und in der Liste sehen
                name = f"Verbund {secrets.token_hex(3)}"
                r = await c.post("/api/v1/aufnahmen", params={"name": f"{name}.mp3"}, content=ton.read_bytes(),
                                 headers={**h, "Content-Type": "audio/mpeg"})
                assert r.status_code == 201, r.text
                aufnahme = r.json()
                angelegt.append(aufnahme["id"])
                liste = (await c.get("/api/v1/aufnahmen", headers=h, params={"filter": "ohne", "suche": name})).json()
                assert [a["id"] for a in liste["eintraege"]] == [aufnahme["id"]] and liste["eintraege"][0]["stand"] == "ohne"

                # Transkribieren: zwei Abschnitte, ohne Sprechertrennung gruppiert
                a = (await c.post("/api/v1/transkribieren", headers=h, json={"quelle_id": aufnahme["id"], "name": name})).json()
                a = await warten(c, h, a["id"])
                assert a["zustand"] == "fertig", a.get("fehler")
                tid = a["ergebnis"]["transkript_id"]
                angelegt.append(tid)
                t = (await c.get(f"/api/v1/transkripte/{tid}", headers=h)).json()
                segmente = t["transkript"]["segmente"]
                assert len(segmente) == 4 and segmente[2]["start"] > 100 and segmente[0]["woerter"][0]["wort"] == "Hallo"
                assert [s["sprecher"] for s in segmente] == ["s1", "s2", "s1", "s2"]
                assert all(s.get("abdruck") is None for s in t["transkript"]["sprecher"])
                eintrag = (await c.get("/api/v1/aufnahmen", headers=h, params={"suche": name})).json()["eintraege"][0]
                assert eintrag["stand"] == "transkribiert" and eintrag["transkripte"][0]["id"] == tid
                protokoll = (await c.get("/api/v1/protokoll", headers=h, params={"ereignis": "sprecher"})).json()
                assert any("ohne_trennung" in e["ereignis"] for e in protokoll["eintraege"])

                # Suchen
                treffer = (await c.get("/api/v1/transkripte", headers=h, params={"suche": "nebenkost"})).json()
                assert tid in [e["id"] for e in treffer["eintraege"]]

                # Ändern nur mit Stand, Notiz der Version
                stand = t["stand"]
                segmente[0]["text"] = "Hallo liebe Welt wie geht es"
                r = await c.patch(f"/api/v1/transkripte/{tid}", headers=h, json={
                    "stand": stand, "segmente": segmente, "sprecher": [{"kennung": "s1", "name": "Anna"}, {"kennung": "s2", "name": "Bernd"}]})
                assert r.status_code == 200, r.text
                neu = r.json()
                assert [w["wort"] for w in neu["transkript"]["segmente"][0]["woerter"]][:3] == ["Hallo", "liebe", "Welt"]
                assert (await c.patch(f"/api/v1/transkripte/{tid}", headers=h, json={"stand": stand, "name": "x"})).status_code == 409
                versionen = (await c.get(f"/api/v1/transkripte/{tid}/versionen", headers=h)).json()
                assert len(versionen) == 2 and "Sprecher 1 heißt Anna" in versionen[0]["notiz"]["was"]
                assert versionen[1]["notiz"]["was"] == "erzeugt"

                # Zurückholen und wieder vor
                r = await c.post(f"/api/v1/transkripte/{tid}/versionen/{versionen[1]['id']}/zurueck", headers=h,
                                 json={"stand": neu["stand"]})
                assert r.status_code == 200 and r.json()["transkript"]["segmente"][0]["text"] == "Hallo Welt wie geht es"
                stand = r.json()["stand"]

                # Export: Download und als Datei daneben
                r = await c.get(f"/api/v1/inhalt/transkripte/{tid}/export", headers=h, params={"format": "srt"})
                assert r.status_code == 200 and "00:00:00,000 --> 00:00:02,600" in r.text and "filename*=UTF-8''" in r.headers["content-disposition"]
                r = await c.post(f"/api/v1/transkripte/{tid}/export", headers=h, json={"format": "docx"})
                assert r.status_code == 201 and r.json()["name"] == f"{name}.docx"
                angelegt.append(r.json()["id"])

                # Profil: Sprecher 1 wird zum neuen Profil
                profilname = f"Probe {secrets.token_hex(2)}"
                r = await c.post(f"/api/v1/transkripte/{tid}/sprecher/s1/profil", headers=h, json={"stand": stand, "name": profilname})
                assert r.status_code == 200, r.text
                stand = r.json()["stand"]
                assert r.json()["transkript"]["sprecher"][0]["name"] == profilname
                profile = {p["name"]: p for p in (await c.get("/api/v1/sprecher", headers=h)).json()}
                assert profile[profilname]["proben"] == 1 and profile[profilname]["transkripte"] == 1
                assert (await c.delete(f"/api/v1/sprecher/{profile[profilname]['id']}", headers=h)).status_code == 200

                # Korrektur als Vorschläge, einer wird übernommen
                a = await warten(c, h, (await c.post(f"/api/v1/transkripte/{tid}/korrigieren", headers=h)).json()["id"])
                assert a["zustand"] == "fertig", a.get("fehler")
                vorschlaege = (await c.get(f"/api/v1/transkripte/{tid}/vorschlaege", headers=h)).json()
                assert [v["neu"] for v in vorschlaege] == ["Hallo, Welt, wie geht es", "Hallo, Welt, wie geht es"]
                t = (await c.get(f"/api/v1/transkripte/{tid}", headers=h)).json()
                segs = t["transkript"]["segmente"]
                segs[0]["text"] = vorschlaege[0]["neu"]
                r = await c.patch(f"/api/v1/transkripte/{tid}", headers=h, json={
                    "stand": t["stand"], "segmente": segs,
                    "vorschlaege": [{"id": vorschlaege[0]["id"], "zustand": "uebernommen"}, {"id": vorschlaege[1]["id"], "zustand": "verworfen"}]})
                assert r.status_code == 200 and (await c.get(f"/api/v1/transkripte/{tid}/vorschlaege", headers=h)).json() == []

                # Auswertung als Markdown-Datei daneben
                a = await warten(c, h, (await c.post(f"/api/v1/transkripte/{tid}/auswerten", headers=h, json={"vorlage": "protokoll"})).json()["id"])
                assert a["zustand"] == "fertig" and a["ergebnis"]["pfad"].endswith(f"{name} (Protokoll).md")
                angelegt.append(a["ergebnis"]["datei_id"])

                # Ton mit Bereichen
                r = await c.get(f"/api/v1/inhalt/transkripte/{tid}/ton", headers={**h, "Range": "bytes=0-99"})
                assert r.status_code == 206 and len(r.content) == 100 and r.headers["content-range"].startswith("bytes 0-99/")

                # Eine andere App mit ihrem App-Schlüssel: Arbeit ja, Einstellungen nein
                app_kopf = {"Authorization": f"Bearer {W['KELLERWOLKE_SCHLUESSEL']}"}
                assert (await c.get(f"/api/v1/transkripte/{tid}", headers=app_kopf)).status_code == 200
                assert (await c.get("/api/v1/einstellungen", headers=app_kopf)).status_code == 403

                # Löschen: in den Papierkorb, aus dem Index
                assert (await c.delete(f"/api/v1/transkripte/{tid}", headers=h)).status_code == 204
                angelegt.remove(tid)
                assert (await c.get(f"/api/v1/transkripte/{tid}", headers=h)).status_code == 404
            finally:
                await c.post("/api/v1/anmeldung/abmelden", headers=h)
    finally:
        if g.kellerwolke is not None:
            for k in angelegt:
                try:
                    await g.kellerwolke.loeschen(k)
                except Exception:  # noqa: BLE001 - schon weg
                    pass
        await g.stoppen()
