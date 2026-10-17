"""Inhalte für `<audio>` und Downloads (auch mit dem Inhalts-Cookie, weil diese keinen Kopf senden): Ton einer
Aufnahme und eines Transkripts mit Bereichen, Export zum Herunterladen. Dazu kurzes Hören ohne Auftrag."""

from __future__ import annotations

import shutil
import uuid
from pathlib import PurePosixPath
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ..ablage import orte
from ..einstellungen import Sprache
from ..export import FORMATE, Format, erzeugen
from ..modell.transkript import Segment
from ..teile import Teile
from .gemeinsam import herunterladen_kopf, inhalt_reichen

HOEREN_HOECHSTENS_S = 120
HOEREN_HOECHSTENS_BYTES = 200 * 1024 * 1024


class Gehoert(BaseModel):
    text: str
    sprache: str | None
    dauer_s: float
    segmente: list[Segment]


def router(teile: Teile) -> APIRouter:
    g = teile.geruest
    r = APIRouter(prefix="/api/v1", tags=["inhalt"])

    @r.get("/inhalt/aufnahmen/{knoten_id}", dependencies=[g.lesen])
    async def aufnahme(knoten_id: UUID, request: Request, anfrage: UUID | None = None) -> Response:
        kw = teile.zugang(anfrage)
        knoten = await kw.knoten(knoten_id)
        if orte.art_der_aufnahme(knoten) is None:
            raise HTTPException(404, "Keine Aufnahme")
        return await inhalt_reichen(kw, knoten, request)

    @r.get("/inhalt/transkripte/{transkript_id}/ton", dependencies=[g.lesen])
    async def ton(transkript_id: UUID, anfrage: UUID | None = None) -> Response:
        """Die Abspielfassung der Aufnahme (PCM-WAV, samplegenau springbar, ohne Versatz zum Text); fehlt sie, entsteht
        sie jetzt."""
        t, _ = await teile.transkripte_fuer(anfrage).lesen(transkript_id)
        if t.quelle is None:
            raise HTTPException(404, "Das Transkript nennt keine Aufnahme")
        kw = teile.zugang(anfrage)
        datei = await teile.abspielen.holen(await kw.knoten(t.quelle.knoten_id), kw)
        return FileResponse(datei, media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})

    @r.get("/inhalt/aufnahmen/{knoten_id}/ton", dependencies=[g.lesen])
    async def aufnahme_ton(knoten_id: UUID, anfrage: UUID | None = None) -> Response:
        """Die Abspielfassung einer Aufnahme (wie beim Transkript), damit sie auch ohne Transkript samplegenau spielt."""
        kw = teile.zugang(anfrage)
        quelle = await kw.knoten(knoten_id)
        if orte.art_der_aufnahme(quelle) is None:
            raise HTTPException(422, f"{quelle.name} ist keine Ton- oder Videodatei")
        datei = await teile.abspielen.holen(quelle, kw)
        return FileResponse(datei, media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})

    @r.get("/inhalt/aufnahmen/{knoten_id}/wellenform", response_model=list[int], dependencies=[g.lesen])
    async def wellenform(knoten_id: UUID, anfrage: UUID | None = None) -> list[int]:
        """800 Werte von 0 bis 100 (Dezibel, fester Maßstab) aus der Abspielfassung; mit oder ohne Transkript gleich."""
        kw = teile.zugang(anfrage)
        quelle = await kw.knoten(knoten_id)
        if orte.art_der_aufnahme(quelle) is None:
            raise HTTPException(422, f"{quelle.name} ist keine Ton- oder Videodatei")
        return await teile.abspielen.wellenform(quelle, kw)

    @r.get("/inhalt/transkripte/{transkript_id}/export", dependencies=[g.lesen])
    async def herunterladen(transkript_id: UUID, format: Format = Query("txt"), anfrage: UUID | None = None) -> Response:
        t, _ = await teile.transkripte_fuer(anfrage).lesen(transkript_id)
        typ, endung = FORMATE[format]
        return Response(erzeugen(t, format), media_type=typ, headers=herunterladen_kopf(f"{t.name}{endung}"))

    @r.post("/hoeren", response_model=Gehoert, dependencies=[g.pflicht])
    async def hoeren(datei: UploadFile, sprache: Sprache | None = Query(None)) -> Gehoert:
        """Kurzer Ton (bis zwei Minuten) sofort zu Text, ohne Auftrag: Spracheingabe, Referenztexte."""
        ordner = teile.arbeit / f"hoeren-{uuid.uuid4().hex}"
        ordner.mkdir(parents=True, exist_ok=True)
        try:
            roh = ordner / f"roh{PurePosixPath(datei.filename or '').suffix.lower() or '.bin'}"
            groesse = 0
            with open(roh, "wb") as ziel:
                while daten := await datei.read(1024 * 1024):
                    groesse += len(daten)
                    if groesse > HOEREN_HOECHSTENS_BYTES:
                        raise HTTPException(413, "Zu groß für kurzes Hören; als Aufnahme transkribieren")
                    ziel.write(daten)
            wav = await teile.ton.wandeln(roh, ordner / "ton.wav")
            dauer = await teile.ton.dauer(wav)
            if dauer > HOEREN_HOECHSTENS_S:
                raise HTTPException(413, f"Höchstens {HOEREN_HOECHSTENS_S} s; Längeres als Aufnahme transkribieren")
            erg = await teile.klangwerk.hoeren(wav, sprache or teile.einstellungen.sprache, titel="Kurz hören",
                                               prioritaet="hoch")
            return Gehoert(text=" ".join(s.text for s in erg.segmente), sprache=erg.sprache, dauer_s=round(dauer, 3),
                           segmente=erg.segmente)
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    return r

