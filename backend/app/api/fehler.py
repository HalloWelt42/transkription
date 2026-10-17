"""Fehler der Bausteine als HTTP-Antworten, an einer Stelle: Kellerwolke, Leitstelle, Ton, fehlende Verbindungen."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from appkern.kellerwolke import (
    Gesperrt, KeinRecht, KellerwolkeFehler, NichtErreichbar, NichtGefunden, SchluesselUngueltig, StandVeraltet, ZuGross,
)
from appkern.leitstelle import LeitstellenFehler

from ..ablage.transkripte import KeineKellerwolke, Unlesbar
from ..dienste import KeineLeitstelle
from ..ton import TonFehler


class Konflikt(Exception):
    """Der Stand ist veraltet: neu lesen, dann ändern."""


def _antwort(status: int, meldung: str, kopf: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": meldung}, status_code=status, headers=kopf)


def _kellerwolke(f: KellerwolkeFehler) -> JSONResponse:
    if isinstance(f, (StandVeraltet, Konflikt)):
        return _antwort(409, "Inzwischen geändert: bitte neu laden und dann ändern")
    if isinstance(f, NichtGefunden):
        return _antwort(404, f.meldung or "Nicht gefunden")
    if isinstance(f, KeinRecht):
        return _antwort(403, f.meldung)
    if isinstance(f, Gesperrt):
        return _antwort(423, f.meldung)
    if isinstance(f, ZuGross):
        return _antwort(413, f.meldung)
    if isinstance(f, SchluesselUngueltig):
        return _antwort(503, "Die Kellerwolke nimmt den App-Schlüssel nicht (Einstellungen prüfen)")
    if isinstance(f, NichtErreichbar):
        return _antwort(503, "Die Kellerwolke ist gerade nicht erreichbar")
    return _antwort(502, f"Kellerwolke: {f.meldung}")


def behandeln(app: FastAPI) -> None:
    @app.exception_handler(KellerwolkeFehler)
    async def kellerwolke(_: Request, f: KellerwolkeFehler):
        return _kellerwolke(f)

    @app.exception_handler(Konflikt)
    async def konflikt(_: Request, f: Konflikt):
        return _antwort(409, str(f) or "Inzwischen geändert: bitte neu laden und dann ändern")

    @app.exception_handler(LeitstellenFehler)
    async def leitstelle(_: Request, f: LeitstellenFehler):
        kopf = {"Retry-After": str(f.nochmal_in)} if f.nochmal_in else None
        return _antwort(503 if f.status in (0, 503) else 502, f"Leitstelle: {f.meldung}", kopf)

    @app.exception_handler(KeineKellerwolke)
    async def keine_kellerwolke(_: Request, f: KeineKellerwolke):
        return _antwort(503, str(f))

    @app.exception_handler(KeineLeitstelle)
    async def keine_leitstelle(_: Request, f: KeineLeitstelle):
        return _antwort(503, str(f))

    @app.exception_handler(Unlesbar)
    async def unlesbar(_: Request, f: Unlesbar):
        return _antwort(422, str(f))

    @app.exception_handler(TonFehler)
    async def ton(_: Request, f: TonFehler):
        return _antwort(422, str(f))
