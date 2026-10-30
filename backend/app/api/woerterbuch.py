"""Fachwörter-Wörterbuch: einsehen, als Ganzes ändern (Seite Wörterbuch) und Wörter aufnehmen (Vorschlag nach einer
Korrektur im Bearbeiten, nur auf Bestätigung). Es geht dem Hördienst bei jedem Hören als Hinweis mit."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..modell.woerterbuch import Woerterbuch
from ..teile import Teile


class WoerterbuchAus(BaseModel):
    woerter: list[str]
    geaendert_am: datetime | None = Field(None, description="leer: noch nie gespeichert (Startinhalt)")


class WoerterEingabe(BaseModel):
    woerter: list[str] = Field(max_length=2000)


class Aufgenommen(WoerterbuchAus):
    neu: list[str] = Field(description="die wirklich neu aufgenommenen")


def router(teile: Teile) -> APIRouter:
    g = teile.geruest
    r = APIRouter(prefix="/api/v1/woerterbuch", tags=["woerterbuch"], dependencies=[g.pflicht])

    @r.get("", response_model=WoerterbuchAus)
    async def lesen() -> WoerterbuchAus:
        wb, stand = await teile.woerterbuch.lesen()
        return WoerterbuchAus(woerter=wb.woerter, geaendert_am=wb.geaendert_am if stand else None)

    @r.put("", response_model=WoerterbuchAus)
    async def setzen(e: WoerterEingabe) -> WoerterbuchAus:
        try:
            neu = Woerterbuch(woerter=e.woerter)
        except ValueError as f:
            raise HTTPException(422, str(f)) from f

        def ersetzen(wb: Woerterbuch) -> None:
            wb.woerter = neu.woerter
            wb.geaendert_am = neu.geaendert_am

        wb, _ = await teile.woerterbuch.aendern(ersetzen)
        return WoerterbuchAus(woerter=wb.woerter, geaendert_am=wb.geaendert_am)

    @r.post("/woerter", response_model=Aufgenommen)
    async def aufnehmen(e: WoerterEingabe) -> Aufgenommen:
        try:
            Woerterbuch(woerter=e.woerter)
        except ValueError as f:
            raise HTTPException(422, str(f)) from f
        wb, neu = await teile.woerterbuch.aendern(lambda wb: wb.dazu(e.woerter))
        return Aufgenommen(woerter=wb.woerter, geaendert_am=wb.geaendert_am, neu=neu)

    return r
