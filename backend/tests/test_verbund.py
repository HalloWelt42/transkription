"""Verbund: die ganze Transkription gegen die echte Entwicklungs-Kellerwolke (backend/.env.test) und eine
nachgestellte Leitstelle (Klangwerk und Sprachmodell). Ein Lauf: Aufnahme hochladen, transkribieren (zwei Abschnitte,
Sprechertrennung fehlt, also Gruppieren), lesen, suchen, ändern mit Stand, Versionen, Export, Profil, Korrektur,
Auswertung, Ton mit Bereichen, Zugriff einer anderen App. Am Ende liegt alles Angelegte im Papierkorb."""

import asyncio
import secrets
import sys
from pathlib import Path

import httpx
import pytest

from app.main import app_bauen
from app.ton import programm
from tests.hilfen import HAT_KELLERWOLKE, W

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from leitstelle_schein import antworten  # noqa: E402

pytestmark = pytest.mark.skipif(not (HAT_KELLERWOLKE and W.get("KELLERWOLKE_KENNUNG")),
                                reason="keine Test-Kellerwolke eingerichtet (backend/.env.test)")

class Weiche(httpx.AsyncBaseTransport):
    """Leitstelle zum Schein, alles andere echt."""

    def __init__(self):
        self.echt = httpx.AsyncHTTPTransport()
        self.schein = httpx.MockTransport(antworten)

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

                r = await c.put(f"/api/v1/aufnahmen/{aufnahme['id']}/marker", headers=h, json=[{"zeit": 4.5, "titel": "Wichtig"}])
                assert r.status_code == 200, r.text

                # Ohne Wahl gibt es keine Sprecher (ab Werk ohne, nur auf ausdrücklichen Wunsch)
                a = (await c.post("/api/v1/transkribieren", headers=h, json={"quelle_id": aufnahme["id"], "name": f"{name} ohne"})).json()
                a = await warten(c, h, a["id"])
                assert a["zustand"] == "fertig", a.get("fehler")
                erstes = a["ergebnis"]["transkript_id"]
                angelegt.append(erstes)
                ohne = (await c.get(f"/api/v1/transkripte/{erstes}", headers=h)).json()
                assert ohne["transkript"]["sprecher"] == [] and all(s["sprecher"] is None for s in ohne["transkript"]["segmente"])
                assert ohne["pfad"].endswith(f"/Aufnahmen/{name}.transkript.json")      # neben der Aufnahme

                # Transkribieren mit gewählter Sprechertrennung: zwei Abschnitte; die Trennung fehlt, also gruppiert
                a = (await c.post("/api/v1/transkribieren", headers=h, json={"quelle_id": aufnahme["id"], "name": name,
                                                                              "sprecher": "trennung"})).json()
                a = await warten(c, h, a["id"])
                assert a["zustand"] == "fertig", a.get("fehler")
                tid = a["ergebnis"]["transkript_id"]
                assert tid == erstes                     # ein Transkript je Aufnahme: neu transkribiert ist eine Version
                t = (await c.get(f"/api/v1/transkripte/{tid}", headers=h)).json()
                segmente = t["transkript"]["segmente"]
                assert len(segmente) == 4 and segmente[2]["start"] > 100 and segmente[0]["woerter"][0]["wort"] == "Hallo"
                assert [s["sprecher"] for s in segmente] == ["s1", "s2", "s1", "s2"]
                assert all(s.get("abdruck") is None for s in t["transkript"]["sprecher"])
                assert len(t["transkript"]["wellenform"]) == 800
                welle = (await c.get(f"/api/v1/inhalt/aufnahmen/{aufnahme['id']}/wellenform", headers=h)).json()
                assert len(welle) == 800 and max(welle) > 50 and min(welle) < 30      # aus dem Ton, Sprache und Pausen
                assert [(m["zeit"], m["titel"]) for m in t["transkript"]["marker"]] == [(4.5, "Wichtig")]
                eintrag = (await c.get("/api/v1/aufnahmen", headers=h, params={"suche": name})).json()["eintraege"][0]
                assert eintrag["stand"] == "transkribiert" and eintrag["transkripte"][0]["id"] == tid
                assert eintrag["dauer_s"] == pytest.approx(150, abs=1)
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
                # s1 kann schon über ein vorhandenes Profil Anna heißen; s2 bekommt den Namen hier
                assert len(versionen) == 3 and "Sprecher 2 heißt Bernd" in versionen[0]["notiz"]["was"]
                assert [x["name"] for x in neu["transkript"]["sprecher"]] == ["Anna", "Bernd"]
                assert versionen[1]["notiz"]["was"] == "neu transkribiert" and versionen[2]["notiz"]["was"] == "erzeugt"

                # Zurückholen und wieder vor
                r = await c.post(f"/api/v1/transkripte/{tid}/versionen/{versionen[1]['id']}/zurueck", headers=h,
                                 json={"stand": neu["stand"]})
                assert r.status_code == 200 and r.json()["transkript"]["segmente"][0]["text"] == "Hallo Welt wie geht es"
                stand = r.json()["stand"]

                # Von Hand zuordnen: neuer Sprecher für den ersten Beitrag, Sprecher 2 geht in Sprecher 1 auf
                aktuell = r.json()["transkript"]
                von_hand = [{**seg, "sprecher": "s3" if n == 0 else "s1"} for n, seg in enumerate(aktuell["segmente"])]
                r = await c.patch(f"/api/v1/transkripte/{tid}", headers=h, json={"stand": stand, "segmente": von_hand, "sprecher": [
                    {"kennung": "s1", "name": aktuell["sprecher"][0]["name"]}, {"kennung": "s3", "name": "Carla"}]})
                assert r.status_code == 200, r.text
                zugeordnet = r.json()
                assert [x["sprecher"] for x in zugeordnet["transkript"]["segmente"]] == ["s3", "s1", "s1", "s1"]
                assert [x["kennung"] for x in zugeordnet["transkript"]["sprecher"]] == ["s1", "s3"]
                was = (await c.get(f"/api/v1/transkripte/{tid}/versionen", headers=h)).json()[0]["notiz"]["was"]
                assert "Sprecher in 3 Beiträgen zugeordnet" in was and "neu: Carla" in was and "entfällt" in was, was
                # ein Beitrag mit einem Sprecher, den es nicht gibt, wird abgewiesen
                kaputt = [{**seg, "sprecher": "s9"} for seg in von_hand]
                r = await c.patch(f"/api/v1/transkripte/{tid}", headers=h, json={"stand": zugeordnet["stand"], "segmente": kaputt})
                assert r.status_code == 422
                stand = zugeordnet["stand"]

                # Export: Download und als Begleiter neben die Aufnahme
                r = await c.get(f"/api/v1/inhalt/transkripte/{tid}/export", headers=h, params={"format": "srt"})
                assert r.status_code == 200 and "00:00:00,000 --> 00:00:02,600" in r.text and "filename*=UTF-8''" in r.headers["content-disposition"]
                r = await c.post(f"/api/v1/transkripte/{tid}/export", headers=h, json={"format": "docx"})
                assert r.status_code == 201 and r.json()["name"] == f"{name}.docx"
                angelegt.append(r.json()["id"])
                r = await c.post(f"/api/v1/transkripte/{tid}/export", headers=h, json={"format": "docx"})
                assert r.status_code == 201 and r.json()["name"] == f"{name}.docx"            # erneut: neue Version

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
                assert [v["neu"] for v in vorschlaege] == ["Hallo, Welt, wie geht es.", "Zweiter Satz mit Nebenkosten."] * 2
                t = (await c.get(f"/api/v1/transkripte/{tid}", headers=h)).json()
                segs = t["transkript"]["segmente"]
                segs[0]["text"] = vorschlaege[0]["neu"]
                r = await c.patch(f"/api/v1/transkripte/{tid}", headers=h, json={
                    "stand": t["stand"], "segmente": segs,
                    "vorschlaege": [{"id": vorschlaege[0]["id"], "zustand": "uebernommen"}]
                                   + [{"id": v["id"], "zustand": "verworfen"} for v in vorschlaege[1:]]})
                assert r.status_code == 200 and (await c.get(f"/api/v1/transkripte/{tid}/vorschlaege", headers=h)).json() == []

                # Auswertung als Markdown-Begleiter neben der Aufnahme (Runde.protokoll.md)
                a = await warten(c, h, (await c.post(f"/api/v1/transkripte/{tid}/auswerten", headers=h, json={"vorlage": "protokoll"})).json()["id"])
                assert a["zustand"] == "fertig" and a["ergebnis"]["pfad"].endswith(f"/Aufnahmen/{name}.protokoll.md"), a
                angelegt.append(a["ergebnis"]["datei_id"])

                # Ton zum Mitlesen: die Abspielfassung (PCM-WAV 44,1 kHz mono), mit Bereichen
                r = await c.get(f"/api/v1/inhalt/transkripte/{tid}/ton", headers={**h, "Range": "bytes=0-43"})
                assert r.status_code == 206 and r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"
                assert int.from_bytes(r.content[24:28], "little") == 44100 and int.from_bytes(r.content[22:24], "little") == 1
                gesamt = int(r.headers["content-range"].split("/")[1])
                assert gesamt == pytest.approx(44 + 150 * 44100 * 2, rel=0.01)          # 150 s, 16 Bit mono

                # Eine andere App mit ihrem App-Schlüssel: Arbeit ja, Einstellungen nein
                app_kopf = {"Authorization": f"Bearer {W['KELLERWOLKE_SCHLUESSEL']}"}
                assert (await c.get(f"/api/v1/transkripte/{tid}", headers=app_kopf)).status_code == 200
                assert (await c.get("/api/v1/einstellungen", headers=app_kopf)).status_code == 403

                # Aus der Live-Mitschrift (ohne neues Hören): bei vorhandenem Transkript eine neue Version
                r = await c.post("/api/v1/transkripte", headers=h, json={"quelle_id": aufnahme["id"], "name": f"{name} live",
                                                                         "stuecke": [{"start": 0, "ende": 5.5, "text": "Erstes Stück"},
                                                                                     {"start": 5.5, "ende": 12, "text": "Zweites Stück hier"}]})
                assert r.status_code == 201, r.text
                live = r.json()
                assert live["id"] == tid
                assert [s["text"] for s in live["transkript"]["segmente"]] == ["Erstes Stück", "Zweites Stück hier"]
                assert live["transkript"]["segmente"][1]["woerter"][0]["start"] == 5.5 and live["transkript"]["marker"][0]["titel"] == "Wichtig"

                # Unterordner: Aufnahme dort hochgeladen, ihr Transkript daneben, gefunden in Liste und Suche, auch nach dem
                # vollständigen Abgleich
                unter = f"Unter {secrets.token_hex(2)}"
                r = await c.post("/api/v1/aufnahmen", params={"name": f"{name} unten.mp3", "ordner": f"../{unter}"},
                                 content=ton.read_bytes(), headers={**h, "Content-Type": "audio/mpeg"})
                assert r.status_code == 201 and r.json()["pfad"].endswith(f"/Aufnahmen/{unter}/{name} unten.mp3"), r.text
                unten = r.json()
                angelegt.append(unten["id"])
                a = await warten(c, h, (await c.post("/api/v1/transkribieren", headers=h, json={"quelle_id": unten["id"]})).json()["id"])
                assert a["zustand"] == "fertig", a.get("fehler")
                assert a["ergebnis"]["pfad"].endswith(f"/Aufnahmen/{unter}/{name} unten.transkript.json")
                angelegt.append(a["ergebnis"]["transkript_id"])
                im_verzeichnis = lambda seite: a["ergebnis"]["transkript_id"] in [e["id"] for e in seite["eintraege"]]  # noqa: E731
                assert im_verzeichnis((await c.get("/api/v1/transkripte", headers=h, params={"anzahl": 100})).json())
                await app.state.teile.abgleich.vollstaendig()
                assert im_verzeichnis((await c.get("/api/v1/transkripte", headers=h, params={"anzahl": 100})).json())
                for ordnerpfad in (unten["pfad"].rpartition("/")[0], a["ergebnis"]["pfad"].rpartition("/")[0]):
                    k = await g.kellerwolke.finden(ordnerpfad)
                    if k is not None:
                        angelegt.append(str(k.id))

                # Eine Aufnahme lesen (mit Markern und Transkripten), ihr Ton als Abspielfassung
                eine = (await c.get(f"/api/v1/aufnahmen/{aufnahme['id']}", headers=h)).json()
                assert eine["stand"] == "transkribiert" and [(m["zeit"], m["titel"]) for m in eine["marker"]] == [(4.5, "Wichtig")]
                assert live["id"] in [t["id"] for t in eine["transkripte"]]
                r = await c.get(f"/api/v1/inhalt/aufnahmen/{aufnahme['id']}/ton", headers={**h, "Range": "bytes=0-43"})
                assert r.status_code == 206 and r.content[:4] == b"RIFF" and int.from_bytes(r.content[24:28], "little") == 44100

                # Aufnahme in den Papierkorb: einmal ohne (das Transkript bleibt mit seinem Text), einmal mit ihm
                zweite = (await c.post("/api/v1/aufnahmen", params={"name": f"{name} zwei.mp3"}, content=ton.read_bytes(),
                                       headers={**h, "Content-Type": "audio/mpeg"})).json()
                angelegt.append(zweite["id"])
                r = await c.post("/api/v1/transkripte", headers=h, json={"quelle_id": zweite["id"], "name": f"{name} zwei",
                                                                         "stuecke": [{"start": 0, "ende": 2, "text": "Bleibt"}]})
                bleibt = r.json()["id"]
                angelegt.append(bleibt)
                assert (await c.delete(f"/api/v1/aufnahmen/{zweite['id']}", headers=h)).status_code == 204
                angelegt.remove(zweite["id"])
                assert (await c.get(f"/api/v1/aufnahmen/{zweite['id']}", headers=h)).status_code == 404
                behalten = await g.kellerwolke.knoten(bleibt)
                assert behalten.haupt_id is None and (await c.get(f"/api/v1/transkripte/{bleibt}", headers=h)).status_code == 200
                verweise = [t["id"] for t in eine["transkripte"]]
                assert (await c.delete(f"/api/v1/aufnahmen/{aufnahme['id']}", headers=h, params={"mit_transkripten": True})).status_code == 204
                for k in [aufnahme["id"], *verweise]:
                    if k in angelegt:
                        angelegt.remove(k)
                for t in verweise:
                    assert (await c.get(f"/api/v1/transkripte/{t}", headers=h)).status_code == 404
                assert tid in verweise
                protokoll = (await c.get("/api/v1/protokoll", headers=h, params={"ereignis": "aufnahme.geloescht"})).json()
                assert any(name in (e.get("text") or "") for e in protokoll["eintraege"])
            finally:
                await c.post("/api/v1/anmeldung/abmelden", headers=h)
    finally:
        if g.kellerwolke is not None:
            # erst die Dateien, dann die (dann leeren) Ordner; ein Ordner bekommt einen zweiten Versuch
            for runde in (0, 1):
                for k in list(angelegt):
                    try:
                        await g.kellerwolke.loeschen(k)
                        angelegt.remove(k)
                    except Exception:  # noqa: BLE001 - schon weg oder (noch) nicht leer
                        if runde == 1:
                            angelegt.remove(k)
                if angelegt:
                    await asyncio.sleep(0.5)
        await g.stoppen()
