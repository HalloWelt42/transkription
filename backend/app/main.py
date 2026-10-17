"""Transkription: macht aus Ton Text. Backend auf dem Gerüst des Appkerns.

    uvicorn app.main:app --port 8631

Daten (SQLite, Zwischendateien) liegen in `daten/`, zum Entwickeln mit `TRANSKRIPTION_DATEN` woanders.
"""

import os
from pathlib import Path

import httpx
from fastapi import FastAPI

from appkern.app import Geruest

from . import api
from .arten import arten
from .einstellungen import AppEinstellungen
from .fassung import FASSUNG, WURZEL
from .teile import Teile


def app_bauen(daten: Path, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """`transport` nur für Tests (Kellerwolke und Leitstelle nachgestellt)."""
    geruest = Geruest(name="Transkription", kennung="transkription", rolle="macht aus Ton Text", symbol="fa-closed-captioning",
                      fassung=FASSUNG, daten=daten, einstellungen=AppEinstellungen,
                      oberflaeche=WURZEL / "frontend" / "dist", transport=transport, gleichzeitig=2)
    teile = Teile(geruest)
    geruest.begleiter_anmelden(teile, teile.abgleich)
    geruest.auftraege.anmelden(*arten(teile))
    app = geruest.fastapi()
    app.state.geruest = geruest
    app.state.teile = teile
    api.einbinden(app, teile)
    geruest.oberflaeche_ausliefern(app)
    return app


app = app_bauen(Path(os.environ.get("TRANSKRIPTION_DATEN") or WURZEL / "daten"))
