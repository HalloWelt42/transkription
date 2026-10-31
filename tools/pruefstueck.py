"""Prüfstück für die Ansichtsprüfung (HELF-91): legt in der Entwicklungsinstanz eine Aufnahme von zehn Minuten mit einem
Transkript aus kurzen und sehr langen Beiträgen an, dazu eine zweite Fassung mit abweichenden Wörtern. So müssen Mitlesen,
Suche und Sprünge zu Abweichungen weit rollen, auch unter dem festen Kopf des Vergleichs; die Seite "mitlesen" in
frontend/ansicht.json prüft, dass die Marke danach ganz sichtbar ist.

    backend/.venv/bin/python tools/pruefstueck.py [adresse]      Vorgabe: die Entwicklungsinstanz http://127.0.0.1:8632

Angemeldet wird mit dem Testzugang aus backend/.env.test; die zweite Fassung schreibt das Werkzeug mit dem Zugang der
Entwicklungsinstanz (TRANSKRIPTION_DATEN, sonst daten-entwicklung/) direkt in die Kellerwolke. Gibt es das Prüfstück
schon, bekommt es nur die zweite Fassung neu.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from appkern.kellerwolke import Kellerwolke

WURZEL = Path(__file__).resolve().parent.parent
NAME = "Prüfstück Mitlesen"
DAUER_S = 600
# Wörter je Beitrag: kurze im Wechsel mit sehr langen, die höher als ein Telefonschirm sind
LAENGEN = [12, 30, 8, 240, 20, 15, 400, 10, 25, 60, 18, 320, 12, 40, 9, 260, 30, 14, 22, 500, 16, 35, 11, 280]
SEKUNDEN_JE_WORT = 0.22
WOERTER = ("die Aufnahme läuft weiter und wir sprechen über den Plan für die nächste Woche mit allen Beteiligten "
           "damit jeder weiß was zu tun ist und wann die Ergebnisse vorliegen sollen").split()


def testzugang() -> tuple[str, str]:
    zeilen = (WURZEL / "backend/.env.test").read_text(encoding="utf-8").splitlines()
    w = dict(z.split("=", 1) for z in zeilen if "=" in z and not z.lstrip().startswith("#"))
    return w["KELLERWOLKE_KENNUNG"].strip(), w["KELLERWOLKE_PASSWORT"].strip()


def instanz_zugang() -> Kellerwolke:
    daten = Path(os.environ.get("TRANSKRIPTION_DATEN") or WURZEL / "daten-entwicklung")
    db = sqlite3.connect(daten / "transkription.sqlite")
    wert = lambda k: json.loads(db.execute("select wert from einstellung where schluessel = ?", (k,)).fetchone()[0])
    return Kellerwolke(wert("kellerwolke_adresse"), wert("kellerwolke_schluessel"))


def ton() -> bytes:
    """Zehn Minuten leiser Ton (Stille würde der Tondienst womöglich kürzen)."""
    with tempfile.TemporaryDirectory() as ordner:
        ziel = Path(ordner) / "pruefstueck.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={DAUER_S}",
                        "-af", "volume=0.02", "-ar", "16000", "-ac", "1", str(ziel)], check=True)
        return ziel.read_bytes()


def beitraege() -> list[dict]:
    zufall = random.Random(91)
    aus, t = [], 0.0
    for n in LAENGEN:
        dauer = n * SEKUNDEN_JE_WORT
        aus.append({"start": round(t, 2), "ende": round(t + dauer, 2),
                    "text": " ".join(zufall.choice(WOERTER) for _ in range(n)).capitalize() + "."})
        t += dauer + 0.6
    assert t < DAUER_S, f"Beiträge länger als die Aufnahme ({t:.0f} s)"
    return aus


def zweite_fassung(segmente: list[dict]) -> list[dict]:
    """Dieselben Wörter, je zwei Beiträge zu einem zusammengefasst (wie ein Hördienst mit langen Abschnitten; am Telefon
    stehen die beiden Fassungen einer Zeile dann weit auseinander), jedes siebte Wort anders (mal andere Schreibweise,
    mal ein anderes Wort) und hin und wieder ein Wort mehr (eine Abweichung, die es nur auf dieser Seite gibt)."""
    neu = []
    for paar in (segmente[i:i + 2] for i in range(0, len(segmente), 2)):
        woerter = []
        for k, w in enumerate(w for s in paar for w in s["woerter"]):
            woerter.append({**w, "wort": (w["wort"].upper() if k % 2 else "anders") if k % 7 == 3 else w["wort"]})
            if k % 23 == 11:
                woerter.append({**w, "wort": "zusätzlich"})
        neu.append({"start": paar[0]["start"], "ende": paar[-1]["ende"], "text": " ".join(w["wort"] for w in woerter),
                    "woerter": woerter})
    return neu


async def main(basis: str) -> None:
    kennung, passwort = testzugang()
    async with httpx.AsyncClient(base_url=basis, timeout=120) as c:
        r = await c.post("/api/v1/anmeldung", json={"kennung": kennung, "passwort": passwort})
        r.raise_for_status()
        h = {"X-Kellerwolke-Sitzung": r.json()["token"]}
        vorhanden = (await c.get("/api/v1/transkripte", params={"suche": NAME, "anzahl": 1}, headers=h)).json()["eintraege"]
        if vorhanden and vorhanden[0]["name"] == NAME:
            tid = vorhanden[0]["id"]
        else:
            r = await c.post("/api/v1/aufnahmen", params={"name": f"{NAME}.wav"}, content=ton(),
                             headers={**h, "content-type": "audio/wav"})
            r.raise_for_status()
            r = await c.post("/api/v1/transkripte", headers=h,
                             json={"quelle_id": r.json()["id"], "name": NAME, "stuecke": beitraege()})
            r.raise_for_status()
            tid = r.json()["id"]
    kw = instanz_zugang()
    knoten = await kw.knoten(tid)
    daten = json.loads(await kw.lesen_ganz(tid))
    daten["fassungen"] = [{"erzeugt_mit": {"dienst": "pruefdienst", "modell": "Prüfdienst", "app": "transkription"},
                           "sprache": "de", "segmente": zweite_fassung(daten["segmente"])}]
    await kw.neue_version(tid, json.dumps(daten, ensure_ascii=False).encode("utf-8"), stand=knoten.etag,
                          inhaltstyp="application/json")
    print(f"{NAME} bereit: {tid}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8632"))
