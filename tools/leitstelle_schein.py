"""Leitstelle zum Schein: Klangwerk (Hören, Stimmabdrücke) und Sprachmodell ohne echte Dienste, für den Verbundtest
und zum Entwickeln und Vorführen der Oberfläche ohne Leitstelle. Der Tondienst ist echt (`appkern.testen.Tondienst`,
rechnet dort, wo der Schein läuft), damit Wandeln, Pausen und Wellenform denselben Weg gehen wie im Betrieb. Die Sprechertrennung fehlt absichtlich (wie ein
Dienst ohne Zugang), damit der Ausweg übers Gruppieren mitgeprüft wird.

    backend/.venv/bin/python tools/leitstelle_schein.py --port 8698

Der Hördienst liefert je Abschnitt ein kurzes Gespräch zweier Stimmen, das Sprachmodell setzt Kommas und fasst
zusammen. Mit der Schnittstelle der echten Leitstelle (`/v1/dienste/<name>/...`, `/v1/chat/completions`)."""

from __future__ import annotations

import argparse
import json
import re

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response

SAETZE = [
    ("Hallo Welt wie geht es", 0.0, 2.6),
    ("Zweiter Satz mit Nebenkosten", 4.0, 6.6),
]
GESPRAECH = [
    "Guten Tag ich würde gern über die Abrechnung sprechen",
    "Gern die Nebenkosten sind dieses Jahr gestiegen",
    "Dürfen wir die Belege vor Ort ein sehen",
    "Selbstverständlich nach Absprache in unserem Büro",
    "Gut dann machen wir nächste Woche einen Termin aus",
    "Ich schicke Ihnen die Bescheide gern mit",
]
STIMMEN_GROESSE = 192


def _stimmen() -> list[list[float]]:
    import numpy as np

    rng = np.random.default_rng(3)
    return [list(rng.normal(size=STIMMEN_GROESSE)), list(rng.normal(size=STIMMEN_GROESSE))]


STIMMEN = _stimmen()


def _woerter(text: str, beginn: float) -> list[dict]:
    return [{"word": f" {w}", "start": round(beginn + i * 0.4, 2), "end": round(beginn + i * 0.4 + 0.3, 2)}
            for i, w in enumerate(text.split())]


def _segmente(saetze: list[tuple[str, float, float]]) -> list[dict]:
    return [{"start": a, "end": b, "text": f" {t}", "words": _woerter(t, a)} for t, a, b in saetze]


def antworten(request: httpx.Request, *, gespraech: bool = False) -> httpx.Response:
    """Die Antworten der Schein-Leitstelle. `gespraech`: längere, abwechslungsreiche Texte (Vorführen)."""
    pfad = request.url.path
    if pfad == "/v1/models":
        return httpx.Response(200, json={"data": [
            {"id": "klein", "x-leitstelle": {"name": "Kleines Sprachmodell (Schein)", "faehigkeiten": ["text"], "geladen": True}},
            {"id": "klangwerk-hoeren", "x-leitstelle": {"name": "Klangwerk Hören (Schein)", "faehigkeiten": ["hoeren"]}},
            {"id": "klangwerk-sprecher", "x-leitstelle": {"name": "Klangwerk Sprechermerkmal (Schein)", "faehigkeiten": ["sprecher_erkennen"]}},
            {"id": "klangwerk-trennen", "x-leitstelle": {"name": "Klangwerk Sprechertrennung (Schein)", "faehigkeiten": ["sprecher_trennen"]}},
            {"id": "klangwerk-ton", "x-leitstelle": {"name": "Klangwerk Ton", "faehigkeiten": ["ton"]}},
        ]})
    if pfad.endswith("/stt"):
        if gespraech:
            saetze = [(GESPRAECH[i % len(GESPRAECH)], i * 9.0, i * 9.0 + 7.5) for i in range(6)]
        else:
            saetze = SAETZE
        return httpx.Response(200, json={"language": "de", "model": "Schein", "segments": _segmente(saetze)})
    if pfad.endswith("/speaker/embed"):
        treffer = re.search(rb'name="segments"\r\n\r\n(.*?)\r\n', request.content, re.S)
        segmente = json.loads(treffer.group(1)) if treffer else []
        return httpx.Response(200, json={"embeddings": [STIMMEN[i % 2] for i in range(len(segmente))], "dim": STIMMEN_GROESSE})
    if pfad.endswith("/speaker/diarize"):
        return httpx.Response(503, json={"detail": "Modell ist nicht bereit (ohne_zugang)"})
    if pfad == "/v1/chat/completions":
        nachrichten = json.loads(request.content)["messages"]
        if "korrigierst" in nachrichten[0]["content"]:
            zeilen = re.findall(r"^\[(\d+)\] (.*)$", nachrichten[1]["content"], re.M)
            text = "\n".join(f"[{n}] {_korrigieren(t)}" for n, t in zeilen)
        else:
            text = "## Zusammenfassung\n\nEin Gespräch über die Nebenkosten; ein Termin zur Belegeinsicht wird vereinbart."
        return httpx.Response(200, json={"model": "klein", "choices": [{"message": {"content": text}, "finish_reason": "stop"}]})
    return httpx.Response(404, json={"detail": f"unbekannt: {pfad}"})


def _korrigieren(text: str) -> str:
    text = text.replace("Hallo Welt", "Hallo, Welt,").replace("ein sehen", "einsehen").replace("Gern die", "Gern. Die")
    return text if text.endswith((".", "?", "!")) else f"{text}."


def main() -> None:
    import uvicorn

    teile = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    teile.add_argument("--port", type=int, default=8698)
    werte = teile.parse_args()
    import tempfile
    from pathlib import Path

    from appkern.ton import TonHier
    from appkern.ton.gegenseite import routen

    app = FastAPI(title="Leitstelle zum Schein")
    app.include_router(routen(TonHier(), Path(tempfile.mkdtemp(prefix="schein-ton-"))), prefix="/v1/dienste/klangwerk-ton")

    @app.api_route("/{pfad:path}", methods=["GET", "POST"])
    async def alles(request: Request, pfad: str):
        inhalt = await request.body()
        anfrage = httpx.Request(request.method, str(request.url), headers=request.headers.raw, content=inhalt)
        a = antworten(anfrage, gespraech=True)
        return Response(a.content, status_code=a.status_code, media_type="application/json")

    uvicorn.run(app, host="127.0.0.1", port=werte.port, log_level="warning")


if __name__ == "__main__":
    main()
