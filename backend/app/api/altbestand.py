"""Altbestand der alten App (Entwurf 1d): die eigenen Aufnahmen mit ihren Ständen und ob sie schon übernommen sind;
Übernahme einer Aufnahme als Auftrag. Übernommen wird nur, was der Nutzer wählt."""

from __future__ import annotations

from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from appkern.anmeldung import Konto
from appkern.auftraege import Auftrag

from .. import altbestand
from ..ablage.transkripte import zugang
from ..arten import UebernehmenAnfrage, UebernehmenEingabe
from ..teile import Teile
from .gemeinsam import von


class Uebernommen(BaseModel):
    aufnahme_id: UUID
    pfad: str


class AltEintrag(altbestand.AltAufnahme):
    uebernommen: Uebernommen | None = None
    unvollstaendig: Uebernommen | None = None   # angefangen, aber nicht fertig: eine neue Übernahme setzt dort fort
    auftrag_id: str | None = None          # Übernahme läuft oder wartet


class AltbestandSeite(BaseModel):
    adresse: str
    eintraege: list[AltEintrag]


def router(teile: Teile) -> APIRouter:
    g = teile.geruest
    r = APIRouter(prefix="/api/v1/altbestand", tags=["altbestand"], dependencies=[g.pflicht])

    @r.get("", response_model=AltbestandSeite)
    async def liste() -> AltbestandSeite:
        adresse = teile.einstellungen.altbestand_adresse
        if not adresse:
            raise HTTPException(404, "Keine alte App eingetragen (Einstellungen, Altbestand)")
        async with httpx.AsyncClient() as client:
            try:
                aufnahmen = await altbestand.AlteApp(adresse, client).aufnahmen()
            except altbestand.AltFehler as f:
                raise HTTPException(503, str(f)) from f
        kw = zugang(lambda: g.kellerwolke)
        laufend = {str(a.eingabe.get("schluessel")): a.id for a in
                   (await g.auftraege.liste(zustand=["wartet", "laeuft"], art="uebernehmen", grenze=200)).eintraege}
        eintraege = []
        for a in aufnahmen:
            schon = await kw.suchen({altbestand.FELD_ALTBESTAND: a.quelle}, 1)
            teil = [] if schon else await kw.suchen({altbestand.FELD_ALTBESTAND_TEIL: a.quelle}, 1)
            eintraege.append(AltEintrag(**a.model_dump(), auftrag_id=laufend.get(a.schluessel),
                                        uebernommen=Uebernommen(aufnahme_id=schon[0].id, pfad=schon[0].pfad) if schon else None,
                                        unvollstaendig=Uebernommen(aufnahme_id=teil[0].id, pfad=teil[0].pfad) if teil else None))
        return AltbestandSeite(adresse=adresse, eintraege=eintraege)

    @r.post("/uebernehmen", status_code=201, response_model=Auftrag)
    async def uebernehmen(anfrage: UebernehmenAnfrage, konto: Konto = g.pflicht) -> Auftrag:
        if not teile.einstellungen.altbestand_adresse:
            raise HTTPException(404, "Keine alte App eingetragen (Einstellungen, Altbestand)")
        return await g.auftraege.einreihen("uebernehmen", UebernehmenEingabe(**anfrage.model_dump(), von=von(konto)),
                                           titel=f"{anfrage.name}: übernehmen")

    return r
