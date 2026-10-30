"""Altbestand der alten App: Auswahl der eigenen Aufnahmen und Umwandeln ins neue Format; im Verbund (Entwicklungs-
Kellerwolke, nachgestellte alte App und Leitstelle) die Übernahme von Hand: Original mit Prüfsumme in einen Unterordner,
alte Stände als Versionen, neu transkribiert als jüngste Version, zweites Übernehmen abgewiesen."""

import asyncio
import hashlib
import json
import secrets
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app import altbestand
from app.main import app_bauen
from app.modell.transkript import Quelle
from appkern.ton import programm
from tests.hilfen import HAT_KELLERWOLKE, W
from tests.test_verbund import Weiche, warten

QUELLE = Quelle(knoten_id="00000000-0000-0000-0000-000000000001", pfad="Apps/T/Aufnahmen/x.mp3", etag=None)


def alt_transkript(nummer: int, mit_woertern: bool) -> dict:
    """Wie die alte App ein Transkript liefert (Felder und Eigenheiten echter Daten)."""
    woerter = [{"word": " Guten", "start": 0.5, "end": 0.9}, {"word": " Tag", "start": 0.9, "end": 1.2}] if mit_woertern else []
    return {
        "id": f"alt{nummer}", "name": "Besprechung.mp3", "language": "german", "created_at": f"2026-06-1{nummer}T10:00:00",
        "segments": [
            {"start": 0.5, "end": 1.2, "text": "Guten Tag", "speaker": "SPEAKER_04", "speaker_cluster": 0, "words": woerter},
            {"start": 1.5, "end": 3.0, "text": "Hallo zusammen", "speaker": "Jens", "speaker_cluster": 1, "words": []},
            {"start": 3.2, "end": 3.4, "text": "  ", "speaker": "Jens", "speaker_cluster": 1},
        ],
        "speakers": [{"label": "SPEAKER_04", "cluster": 0, "embedding": [0.1] * 192},
                     {"label": "Jens", "cluster": 1, "profile_id": "p1", "embedding": None}],
    }


def test_gruppieren_nur_eigene_aufnahmen():
    kurz = [
        {"id": "a", "name": "Besprechung.mp3", "source_audio_path": "/d/storage/x.mp3", "created_at": "2026-06-10", "dauer_s": 60},
        {"id": "b", "name": "Besprechung.mp3", "source_audio_path": "/d/storage/x.mp3", "created_at": "2026-06-12", "dauer_s": 61,
         "mit_woertern": True},
        {"id": "c", "name": "tubevault_abc.wav", "source_audio_path": "/d/storage/y.wav", "created_at": "2026-06-11"},
        {"id": "d", "name": "20260601_clone.wav", "source_audio_path": "/d/results/z.wav", "created_at": "2026-06-11"},
        {"id": "e", "name": "Segment.wav", "source_audio_path": "/d/voices/cut_1.wav", "created_at": "2026-06-13"},
    ]
    gruppen = altbestand.gruppieren(kurz)
    assert [g.name for g in gruppen] == ["Segment.wav", "Besprechung.mp3"]          # neueste zuerst, nur eigene
    b = gruppen[1]
    assert [s.id for s in b.staende] == ["a", "b"] and b.vorschlag == "Besprechung" and b.endung == ".mp3"
    assert b.dauer_s == 61 and b.schluessel == altbestand.schluessel("/d/storage/x.mp3")


@pytest.mark.parametrize("als_text", [False, True])
def test_in_transkript(als_text: bool):
    alt = alt_transkript(2, True)
    if als_text:                         # so liefert sie der Einzelabruf der echten alten App
        alt = {**alt, "segments": json.dumps(alt["segments"]), "speakers": json.dumps(alt["speakers"])}
    t = altbestand.in_transkript(alt, "Besprechung", QUELLE, 3.0)
    assert t.sprache == "de" and [s.name for s in t.sprecher] == ["Sprecher 1", "Jens"]
    assert t.sprecher[0].abdruck is not None and len(t.sprecher[0].abdruck) == 192 and t.sprecher[1].abdruck is None
    assert [(s.text, s.sprecher) for s in t.segmente] == [("Guten Tag", "s1"), ("Hallo zusammen", "s2")]   # leere fallen weg
    assert [w.wort for w in t.segmente[0].woerter] == ["Guten", "Tag"]
    assert t.erstellt_am.year == 2026 and "übernommen" in t.aenderung.was


def frei() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def alte_app(ton: Path, zustand: dict) -> FastAPI:
    """Die alte App zum Schein: zwei Stände einer eigenen Aufnahme und eine Tonspur eines Videos. Mit
    zustand["kaputt"] liefert sie keine Stände (Abbruch nach dem Hochladen)."""
    summe = hashlib.sha256(ton.read_bytes()).hexdigest()
    staende = {"alt1": alt_transkript(1, False), "alt2": alt_transkript(2, True)}
    a = FastAPI()

    @a.get("/api/system/version")
    def version():
        return {"version": "0.130.3"}

    @a.get("/api/transcribe/kurz")
    def kurz():
        eigene = [{"id": k, "name": v["name"], "source_audio_path": "/d/storage/besprechung.mp3", "created_at": v["created_at"],
                   "source_size": ton.stat().st_size, "dauer_s": 3.0, "segment_count": 3, "speaker_count": 2,
                   "mit_woertern": k == "alt2", "language": "german"} for k, v in staende.items()]
        return [*eigene, {"id": "tv", "name": "tubevault_x.wav", "source_audio_path": "/d/storage/tv.wav", "created_at": "2026-01-01"}]

    @a.get("/api/transcribe/{alt_id}")
    def transkript(alt_id: str):
        if alt_id not in staende:
            raise HTTPException(404)
        if zustand.get("kaputt"):
            raise HTTPException(500, "kaputt")
        # wie die echte alte App: Segmente und Sprecher als JSON-Text
        return {**staende[alt_id], "segments": json.dumps(staende[alt_id]["segments"]),
                "speakers": json.dumps(staende[alt_id]["speakers"])}

    @a.get("/api/transcribe/{alt_id}/original")
    def original(alt_id: str):
        return FileResponse(ton, headers={"X-Pruefsumme": summe})

    return a


pytestmark_verbund = pytest.mark.skipif(not (HAT_KELLERWOLKE and W.get("KELLERWOLKE_KENNUNG")),
                                        reason="keine Test-Kellerwolke eingerichtet (backend/.env.test)")


@pytestmark_verbund
async def test_uebernahme_von_hand(tmp_path: Path):
    ton = tmp_path / "besprechung.mp3"
    erzeugen = await asyncio.create_subprocess_exec(
        programm("ffmpeg"), "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        "aevalsrc='0.4*sin(2*PI*330*t)':s=16000:d=4", str(ton))
    assert await erzeugen.wait() == 0
    port = frei()
    zustand = {"kaputt": True}
    server = uvicorn.Server(uvicorn.Config(alte_app(ton, zustand), host="127.0.0.1", port=port, log_level="warning"))
    faden = threading.Thread(target=server.run, daemon=True)
    faden.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)

    app = app_bauen(tmp_path / "daten", transport=Weiche(tmp_path / "tondienst"))
    g = app.state.geruest
    await g.starten()
    angelegt: list[str] = []
    zielordner_pfad = ""
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=60) as c:
            assert (await c.post("/api/v1/einrichtung", json={"kellerwolke_adresse": W["KELLERWOLKE_ADRESSE"],
                                                              "kellerwolke_schluessel": W["KELLERWOLKE_SCHLUESSEL"]})).status_code == 200
            r = await c.post("/api/v1/anmeldung", json={"kennung": W["KELLERWOLKE_KENNUNG"], "passwort": W["KELLERWOLKE_PASSWORT"]})
            h = {"X-Kellerwolke-Sitzung": r.json()["token"]}
            assert (await c.get("/api/v1/altbestand", headers=h)).status_code == 404            # ohne alte App nichts
            r = await c.patch("/api/v1/einstellungen", headers=h, json={"werte": {
                "leitstelle_adresse": "http://ls.test", "leitstelle_schluessel": "ls_probe",
                "altbestand_adresse": f"http://127.0.0.1:{port}"}})
            assert r.status_code == 200, r.text

            seite = (await c.get("/api/v1/altbestand", headers=h)).json()
            assert len(seite["eintraege"]) == 1                                                   # ohne Tonspur des Videos
            eintrag = seite["eintraege"][0]
            assert [s["id"] for s in eintrag["staende"]] == ["alt1", "alt2"] and eintrag["uebernommen"] is None

            zielordner = f"Altbestand {secrets.token_hex(2)}"
            zielordner_pfad = f"{(await g.kellerwolke.ich()).zweig}/Aufnahmen/{zielordner}"
            name = f"Probe Alt {secrets.token_hex(2)}"
            # erst bricht die Übernahme nach dem Hochladen ab: unvollständig, nicht übernommen
            abbruch = await warten(c, h, (await c.post("/api/v1/altbestand/uebernehmen", headers=h, json={
                "schluessel": eintrag["schluessel"], "zielordner": zielordner, "name": name})).json()["id"])
            assert abbruch["zustand"] == "fehler"
            halb = (await c.get("/api/v1/altbestand", headers=h)).json()["eintraege"][0]
            assert halb["uebernommen"] is None and halb["unvollstaendig"] is not None
            angelegt.append(halb["unvollstaendig"]["aufnahme_id"])
            zustand["kaputt"] = False
            # eine neue Übernahme setzt mit derselben Aufnahme fort (nichts doppelt hochgeladen)
            a = (await c.post("/api/v1/altbestand/uebernehmen", headers=h, json={
                "schluessel": eintrag["schluessel"], "zielordner": zielordner, "name": name, "neu_transkribieren": True,
                "sprecher": "ohne"})).json()
            a = await warten(c, h, a["id"])
            assert a["zustand"] == "fertig", a.get("fehler")
            erg = a["ergebnis"]
            angelegt += [erg["aufnahme_id"], erg["transkript_id"]]
            assert erg["pfad"].endswith(f"/Aufnahmen/{zielordner}/{name}.mp3") and erg["staende"] == 2
            assert erg["aufnahme_id"] == halb["unvollstaendig"]["aufnahme_id"]

            # das Original kam unverändert an
            inhalt = await g.kellerwolke.lesen_ganz(erg["aufnahme_id"]) if hasattr(g.kellerwolke, "lesen_ganz") else None
            if inhalt is not None:
                assert hashlib.sha256(inhalt).hexdigest() == hashlib.sha256(ton.read_bytes()).hexdigest()

            # neu transkribiert als jüngste Version über den zwei alten Ständen
            folge = await warten(c, h, erg["folgeauftrag"])
            assert folge["zustand"] == "fertig", folge.get("fehler")
            assert folge["ergebnis"]["transkript_id"] == erg["transkript_id"]
            versionen = (await c.get(f"/api/v1/transkripte/{erg['transkript_id']}/versionen", headers=h)).json()
            assert len(versionen) == 3 and versionen[0]["notiz"]["was"] == "neu transkribiert"
            assert "übernommen aus der alten App" in versionen[2]["notiz"]["was"]
            t = (await c.get(f"/api/v1/transkripte/{erg['transkript_id']}", headers=h)).json()
            assert t["pfad"].endswith(f"/Aufnahmen/{zielordner}/{name}.transkript.json") and t["transkript"]["name"] == name

            # jetzt als übernommen gemeldet; ein zweites Übernehmen wird abgewiesen
            seite = (await c.get("/api/v1/altbestand", headers=h)).json()
            assert seite["eintraege"][0]["uebernommen"]["aufnahme_id"] == erg["aufnahme_id"]
            zweit = await warten(c, h, (await c.post("/api/v1/altbestand/uebernehmen", headers=h, json={
                "schluessel": eintrag["schluessel"], "name": name})).json()["id"])
            assert zweit["zustand"] == "fehler" and "Schon übernommen" in (zweit.get("fehler") or "")

            for pfad in (erg["pfad"].rpartition("/")[0], t["pfad"].rpartition("/")[0]):
                k = await g.kellerwolke.finden(pfad)
                if k is not None:
                    angelegt.append(str(k.id))
    finally:
        if g.kellerwolke is not None:
            # der Zielordner auch dann, wenn der Test vor dem Ende scheiterte (sonst sammeln sich Ordner, HELF-58)
            if zielordner_pfad and (k := await g.kellerwolke.finden(zielordner_pfad)) is not None and str(k.id) not in angelegt:
                angelegt.append(str(k.id))
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
        server.should_exit = True
        faden.join(timeout=5)


def test_profile_einmischen():
    """Alte Profile kommen dazu, gleiche Namen bleiben unberührt, Abdrücke auf Länge 1."""
    from app.modell.sprecherprofil import Profil, Profile
    profile = Profile(profile=[Profil(name="Jens", abdruck=[1.0, 0.0])])
    ergebnis = altbestand.profile_einmischen(profile, [altbestand.AltesProfil(name="jens", abdruck=[0.0, 3.0], proben=2),
                                                       altbestand.AltesProfil(name="Heiko", abdruck=[3.0, 4.0], proben=2)])
    assert ergebnis == {"neu": ["Heiko"], "vorhanden": ["jens"]}
    assert profile.profile[0].abdruck == [1.0, 0.0] and profile.profile[1].abdruck == [0.6, 0.8]
    assert profile.profile[1].proben == 2


async def test_werkzeug_vorschau_einreihen_umwandeln(tmp_path: Path, capsys):
    """Das Werkzeug am Rechner der App: Vorschau ändert nichts, Ausführen reiht je Aufnahme einen Auftrag und einen für
    die Profile ein und trägt die alte App ein, ein zweiter Lauf reiht nichts doppelt; Umwandeln schreibt transkript/1."""
    from app import werkzeug
    from app.modell.transkript import Transkript
    from appkern.datenbank import Datenbank

    ton = tmp_path / "besprechung.mp3"
    ton.write_bytes(b"ID3-probe")
    port = frei()
    server = uvicorn.Server(uvicorn.Config(alte_app(ton, {}), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    adresse = f"http://127.0.0.1:{port}"
    try:
        plan = tmp_path / "plan.json"
        plan.write_text(json.dumps({"adresse": adresse, "aufnahmen": [
            {"quelle": "/d/storage/besprechung.mp3", "zielordner": "REKO/2026"},
            {"quelle": "/d/storage/gibt-es-nicht.mp3", "name": "Gibt es nicht"}],
            "profile": [{"name": "Jens", "abdruck": [0.1] * 192, "proben": 3}]}), encoding="utf-8")
        daten = tmp_path / "daten"
        assert await werkzeug.altbestand(plan, False, daten) == 1                 # eine fehlt in der alten App
        ausgabe = capsys.readouterr().out
        assert "neu              Aufnahmen/REKO/2026/Besprechung.mp3  (2 Stände, " in ausgabe and "fehlt" in ausgabe
        db = await Datenbank(daten / "transkription.sqlite").oeffnen()
        try:
            assert await db.zeilen("SELECT id FROM auftrag") == []               # die Vorschau ändert nichts
        finally:
            await db.schliessen()
        await werkzeug.altbestand(plan, True, daten)
        await werkzeug.altbestand(plan, True, daten)                             # nichts doppelt
        db = await Datenbank(daten / "transkription.sqlite").oeffnen()
        try:
            arten = sorted(z["art"] for z in await db.zeilen("SELECT art FROM auftrag WHERE zustand='wartet'"))
            adresse_gespeichert = (await db.zeilen("SELECT wert FROM einstellung WHERE schluessel='altbestand_adresse'"))[0]["wert"]
        finally:
            await db.schliessen()
        assert arten == ["profile_uebernehmen", "uebernehmen"]
        assert json.loads(adresse_gespeichert) == adresse

        liste = tmp_path / "liste.json"
        liste.write_text(json.dumps({"adresse": adresse, "eintraege": [
            {"id": "alt2", "name": "Ansage", "dauer_s": 3.0, "datei": "Ansage.transkript.json"}]}), encoding="utf-8")
        assert await werkzeug.umwandeln(liste, tmp_path / "aus") == 0
        t = Transkript.model_validate_json((tmp_path / "aus" / "Ansage.transkript.json").read_text(encoding="utf-8"))
        assert t.name == "Ansage" and t.quelle is None and t.segmente[0].text == "Guten Tag"
    finally:
        server.should_exit = True
