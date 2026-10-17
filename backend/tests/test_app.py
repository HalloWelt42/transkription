"""Transkription gegen eine nachgestellte Kellerwolke: einrichten, anmelden, Schutz der Schnittstelle, Einstellungen
mit lesbaren Beschriftungen, leeres Verzeichnis."""

import json
from pathlib import Path

import httpx
import pytest

from app.main import app_bauen

BENUTZER = {"id": "1", "name": "probe", "rolle": "mitglied", "aktiv": True}


def kellerwolke(request: httpx.Request) -> httpx.Response:
    pfad = request.url.path
    if pfad == "/api/v1/ablage/ich":
        return httpx.Response(200, json={"app": "Transkription", "konto": "probe", "rechte": []})
    if pfad == "/api/v1/auth/login":
        if json.loads(request.content)["passwort"] != "geheim":
            return httpx.Response(401, json={"detail": "Anmeldung fehlgeschlagen"})
        return httpx.Response(200, json={"token": "t1", "benutzer": BENUTZER})
    if pfad == "/api/v1/auth/status":
        ok = request.headers.get("x-kellerwolke-sitzung") == "t1"
        return httpx.Response(200, json={"angemeldet": ok, "benutzer": BENUTZER if ok else None})
    return httpx.Response(404, json={"detail": "nicht da"})


@pytest.fixture
async def client(tmp_path: Path):
    app = app_bauen(tmp_path / "daten", transport=httpx.MockTransport(kellerwolke))
    await app.state.geruest.starten()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await app.state.geruest.stoppen()


async def test_einrichten_anmelden_und_schutz(client):
    assert (await client.get("/api/v1/app")).json()["einrichtung_noetig"]
    r = await client.post("/api/v1/einrichtung", json={"kellerwolke_adresse": "http://kw.test", "kellerwolke_schluessel": "kw_app_x"})
    assert r.json()["besitzer"] == "probe"
    h = {"X-Kellerwolke-Sitzung": (await client.post("/api/v1/anmeldung", json={"kennung": "probe", "passwort": "geheim"})).json()["token"]}
    for weg in ("/api/v1/transkripte", "/api/v1/aufnahmen", "/api/v1/sprecher",
                "/api/v1/inhalt/transkripte/00000000-0000-0000-0000-000000000000/ton"):
        assert (await client.get(weg)).status_code == 401, weg
    seite = (await client.get("/api/v1/transkripte", headers=h)).json()
    assert seite == {"gesamt": 0, "ab": 0, "anzahl": 20, "eintraege": []}
    felder = {f["name"]: f for f in (await client.get("/api/v1/einstellungen", headers=h)).json()}
    assert felder["sprache"]["beschriftungen"]["de"] == "Deutsch" and felder["sprecher_sicher"]["schritt"] == 5
    assert felder["sprecher_sicher"]["einheit"] == "% Ähnlichkeit" and felder["abschnitt_min"]["einheit"] == "Minuten"
    # was das System kennt, kommt als Auswahl: Dienste und Modell aus der Leitstelle, ffmpeg mit Fundort
    assert all(felder[n]["angebot"] for n in ("dienst_hoeren", "dienst_sprecher", "dienst_trennen", "ki_modell", "ffmpeg_ordner"))
    angebot = (await client.get("/api/v1/einstellungen/angebot/ffmpeg_ordner", headers=h)).json()
    assert angebot["stand"].startswith("gefunden: ") and angebot["optionen"][0]["titel"] == "Automatisch finden"
    hoeren = (await client.get("/api/v1/einstellungen/angebot/dienst_hoeren", headers=h)).json()
    assert hoeren["stand"].startswith("Leitstelle noch nicht eingerichtet")
    assert (await client.post("/api/v1/transkribieren", headers=h, json={"quelle_id": "x"})).status_code == 422
    assert (await client.get("/api/v1/aufnahmen", headers=h)).status_code == 404          # Schein kennt keine Ablage


def test_unterordner_sicher():
    from app.ablage import orte
    assert orte.unterordner("../Besprechungen//2026 ") == "Besprechungen/2026"
    assert orte.unterordner("a:b/./c") == "a b/c" and orte.unterordner("") == ""
    assert orte.unterordner_der_aufnahme("Apps/T", "Apps/T/Aufnahmen/x.wav") == ""
    assert orte.unterordner_der_aufnahme("Apps/T", "Apps/T/Aufnahmen/A/B/x.wav") == "A/B"
    assert orte.unterordner_der_aufnahme("Apps/T", "Freigabe/Musik/x.wav") == ""
