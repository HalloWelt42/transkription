"""Sprecherprofile: Liste (ohne Abdrücke), umbenennen, zusammenführen, löschen. Ein Profil entsteht, wenn ein Sprecher
eines Transkripts einen Namen als Profil bekommt (siehe Transkripte)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..modell.sprecherprofil import Probe, Profile
from ..modell.transkript import jetzt
from ..teile import Teile


class ProfilAus(BaseModel):
    id: UUID
    name: str
    proben: int
    beispiele: list[Probe]
    transkripte: int = Field(description="Transkripte, in denen ein Sprecher dieses Namens vorkommt")
    erstellt_am: datetime
    geaendert_am: datetime


class NameEingabe(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ZusammenfuehrenEingabe(BaseModel):
    quelle_id: UUID = Field(description="dieses Profil geht im Ziel auf und verschwindet")


def router(teile: Teile) -> APIRouter:
    g = teile.geruest
    r = APIRouter(prefix="/api/v1/sprecher", tags=["sprecher"], dependencies=[g.pflicht])

    async def ausgeben(profile: Profile) -> list[ProfilAus]:
        zahlen = {z["name"].lower(): z["n"] for z in await g.db.zeilen(
            "SELECT name, count(*) AS n FROM transkript_sprecher GROUP BY name")}
        return [ProfilAus(id=p.id, name=p.name, proben=p.proben, beispiele=p.beispiele,
                          transkripte=zahlen.get(p.name.lower(), 0), erstellt_am=p.erstellt_am,
                          geaendert_am=p.geaendert_am)
                for p in sorted(profile.profile, key=lambda p: p.name.lower())]

    @r.get("", response_model=list[ProfilAus])
    async def liste() -> list[ProfilAus]:
        return await ausgeben((await teile.profile.lesen())[0])

    @r.patch("/{profil_id}", response_model=list[ProfilAus])
    async def umbenennen(profil_id: UUID, eingabe: NameEingabe) -> list[ProfilAus]:
        def aendern(profile: Profile) -> Profile:
            p = profile.holen(profil_id)
            if p is None:
                raise HTTPException(404, "Profil nicht gefunden")
            if any(x.id != profil_id and x.name.lower() == eingabe.name.lower() for x in profile.profile):
                raise HTTPException(409, f"Es gibt schon ein Profil {eingabe.name}; zusammenführen statt umbenennen")
            p.name, p.geaendert_am = eingabe.name, jetzt()
            return profile

        return await ausgeben(await teile.profile.aendern(aendern))

    @r.post("/{profil_id}/zusammenfuehren", response_model=list[ProfilAus])
    async def zusammenfuehren(profil_id: UUID, eingabe: ZusammenfuehrenEingabe) -> list[ProfilAus]:
        def aendern(profile: Profile) -> Profile:
            try:
                profile.zusammenfuehren(profil_id, eingabe.quelle_id)
            except ValueError as f:
                raise HTTPException(422, str(f)) from f
            return profile

        return await ausgeben(await teile.profile.aendern(aendern))

    @r.delete("/{profil_id}", response_model=list[ProfilAus])
    async def loeschen(profil_id: UUID) -> list[ProfilAus]:
        def aendern(profile: Profile) -> Profile:
            if profile.holen(profil_id) is None:
                raise HTTPException(404, "Profil nicht gefunden")
            profile.profile = [p for p in profile.profile if p.id != profil_id]
            return profile

        return await ausgeben(await teile.profile.aendern(aendern))

    return r
