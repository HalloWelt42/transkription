"""Aufnahmen: Ton- und Videodateien im Ordner Aufnahmen und in Ordnern, die der Nutzer der App freigegeben hat; mit
Stand (ohne Transkript, wartet, läuft, transkribiert). Hochladen gestreamt nach Aufnahmen; Transkribieren als Auftrag."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from appkern.anmeldung import Konto
from appkern.auftraege import Auftrag

from ..ablage import orte
from ..ablage.transkripte import zugang
from ..arten import TranskribierenAnfrage, TranskribierenEingabe
from ..teile import Teile
from .gemeinsam import von

Stand = Literal["ohne", "wartet", "laeuft", "transkribiert"]
Filter = Literal["alle", "ohne", "transkribiert"]


class Ordner(BaseModel):
    id: UUID
    name: str
    pfad: str
    recht: str
    eigen: bool = False


class TranskriptVerweis(BaseModel):
    id: UUID
    name: str


class AuftragKurz(BaseModel):
    id: str
    zustand: str
    fortschritt: float | None
    schritt: str
    phase: str | None


class Aufnahme(BaseModel):
    id: UUID
    name: str
    pfad: str
    art: Literal["ton", "video"]
    groesse: int | None
    inhaltstyp: str | None
    geaendert_am: datetime
    stand: Stand
    transkripte: list[TranskriptVerweis]
    auftrag: AuftragKurz | None = None


class AufnahmenSeite(BaseModel):
    ordner: Ordner
    unterordner: list[Ordner]
    gesamt: int
    zahlen: dict[str, int]
    eintraege: list[Aufnahme]


class MarkerEingabe(BaseModel):
    zeit: float = Field(ge=0)
    titel: str = Field(min_length=1, max_length=200)


def router(teile: Teile) -> APIRouter:
    g = teile.geruest
    r = APIRouter(prefix="/api/v1", tags=["aufnahmen"], dependencies=[g.pflicht])

    async def eigener_ordner():
        kw = zugang(lambda: g.kellerwolke)
        return await kw.ordner(orte.ort((await kw.ich()).zweig, orte.AUFNAHMEN))

    @r.get("/aufnahmen/ordner", response_model=list[Ordner])
    async def ordner_liste() -> list[Ordner]:
        """Der eigene Ordner Aufnahmen und die Ordner, die der Nutzer der App außerhalb von Apps freigegeben hat."""
        kw = zugang(lambda: g.kellerwolke)
        ich = await kw.ich()
        eigen = await eigener_ordner()
        aus = [Ordner(id=eigen.id, name=eigen.name, pfad=eigen.pfad, recht=eigen.recht, eigen=True)]
        for recht in ich.rechte:
            if recht.pfad == "Apps" or recht.pfad.startswith("Apps/"):
                continue
            aus.append(Ordner(id=recht.knoten_id, name=recht.pfad.rsplit("/", 1)[-1], pfad=recht.pfad, recht=recht.recht))
        return aus

    @r.get("/aufnahmen", response_model=AufnahmenSeite)
    async def aufnahmen(ordner: UUID | None = None, filter: Filter = "alle", suche: str = "",
                        ab: int = Query(0, ge=0), anzahl: int = Query(50, ge=1, le=200)) -> AufnahmenSeite:
        kw = zugang(lambda: g.kellerwolke)
        ort = await kw.knoten(ordner) if ordner else await eigener_ordner()
        unterordner, dateien = [], []
        async for k in kw.alle_kinder(ort.id):
            if k.ist_ordner:
                unterordner.append(Ordner(id=k.id, name=k.name, pfad=k.pfad, recht=k.recht))
            elif orte.art_der_aufnahme(k) and (not suche or suche.lower() in k.name.lower()):
                dateien.append(k)
        transkripte = await teile.index.zur_quelle([str(k.id) for k in dateien])
        laufend = {}
        for a in (await g.auftraege.liste(zustand=["wartet", "laeuft"], art="transkribieren", grenze=500)).eintraege:
            laufend.setdefault(str(a.eingabe.get("quelle_id")), a)
        alle: list[Aufnahme] = []
        for k in sorted(dateien, key=lambda k: k.geaendert_am, reverse=True):
            verweise = [TranskriptVerweis(id=e.id, name=e.name) for e in transkripte.get(str(k.id), [])]
            auftrag = laufend.get(str(k.id))
            stand: Stand = ("laeuft" if auftrag.zustand == "laeuft" else "wartet") if auftrag else \
                ("transkribiert" if verweise else "ohne")
            alle.append(Aufnahme(
                id=k.id, name=k.name, pfad=k.pfad, art=orte.art_der_aufnahme(k), groesse=k.groesse,
                inhaltstyp=k.inhaltstyp, geaendert_am=k.geaendert_am, stand=stand, transkripte=verweise,
                auftrag=AuftragKurz(id=auftrag.id, zustand=auftrag.zustand, fortschritt=auftrag.fortschritt,
                                    schritt=auftrag.schritt, phase=auftrag.phase) if auftrag else None))
        zahlen = {"alle": len(alle), "ohne": sum(a.stand != "transkribiert" for a in alle),
                  "transkribiert": sum(a.stand == "transkribiert" for a in alle)}
        gefiltert = [a for a in alle if filter == "alle" or (filter == "ohne") == (a.stand != "transkribiert")]
        return AufnahmenSeite(ordner=Ordner(id=ort.id, name=ort.name, pfad=ort.pfad, recht=ort.recht),
                              unterordner=sorted(unterordner, key=lambda o: o.name.lower()), gesamt=len(gefiltert),
                              zahlen=zahlen, eintraege=gefiltert[ab:ab + anzahl])

    @r.post("/aufnahmen", status_code=201, response_model=Aufnahme)
    async def hochladen(request: Request, name: str = Query(min_length=1, max_length=200)) -> Aufnahme:
        """Körper ist der Inhalt (roh, gestreamt) in den eigenen Ordner Aufnahmen; ein belegter Name bekommt eine
        Zahl angehängt."""
        kw = zugang(lambda: g.kellerwolke)
        ort = await eigener_ordner()
        sauber = orte.dateiname(name).removesuffix(orte.ENDUNG)
        stamm, punkt, endung = sauber.rpartition(".")
        stamm, endung = (stamm, f".{endung}") if punkt else (sauber, "")
        if orte.art_der_aufnahme_name(sauber) is None and not (request.headers.get("content-type") or "").startswith(("audio/", "video/")):
            raise HTTPException(422, "Keine Ton- oder Videodatei")
        typ = request.headers.get("content-type") or None
        n = 1
        while await kw.finden(orte.ort(ort.pfad, f"{stamm}{f' ({n})' if n > 1 else ''}{endung}")) is not None:
            n += 1
        ziel = f"{stamm}{f' ({n})' if n > 1 else ''}{endung}"
        k = await kw.schreiben(orte.ort(ort.pfad, ziel), request.stream(), nur_neu=True, inhaltstyp=typ)
        art = orte.art_der_aufnahme(k) or "ton"
        await g.protokoll.eintragen("aufnahme.hochgeladen", k.name, bezug_art="aufnahme", bezug_name=k.name)
        return Aufnahme(id=k.id, name=k.name, pfad=k.pfad, art=art, groesse=k.groesse, inhaltstyp=k.inhaltstyp,
                        geaendert_am=k.geaendert_am, stand="ohne", transkripte=[])

    @r.put("/aufnahmen/{knoten_id}/marker", response_model=list[MarkerEingabe])
    async def marker_setzen(knoten_id: UUID, marker: list[MarkerEingabe]) -> list[MarkerEingabe]:
        """Marker, die beim Aufnehmen gesetzt wurden; sie hängen an der Aufnahme und kommen ins Transkript."""
        kw = zugang(lambda: g.kellerwolke)
        if orte.art_der_aufnahme(await kw.knoten(knoten_id)) is None:
            raise HTTPException(422, "Keine Ton- oder Videodatei")
        await kw.felder_setzen(knoten_id, {orte.FELD_MARKER: [m.model_dump() for m in sorted(marker, key=lambda m: m.zeit)]})
        return marker

    @r.post("/transkribieren", status_code=201, response_model=Auftrag)
    async def transkribieren(anfrage: TranskribierenAnfrage, konto: Konto = g.pflicht) -> Auftrag:
        kw = zugang(lambda: g.kellerwolke)
        quelle = await kw.knoten(anfrage.quelle_id)
        if orte.art_der_aufnahme(quelle) is None:
            raise HTTPException(422, f"{quelle.name} ist keine Ton- oder Videodatei")
        eingabe = TranskribierenEingabe(**anfrage.model_dump(), von=von(konto))
        return await g.auftraege.einreihen("transkribieren", eingabe, titel=anfrage.name or orte.anzeigename(quelle.name))

    return r
