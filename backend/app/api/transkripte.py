"""Transkripte: Verzeichnis mit Suche, Lesen, Ändern nur mit dem zuletzt gelesenen Stand, Versionen und Zurückholen,
Export als Datei neben dem Transkript, Vorschläge der KI-Korrektur, Sprecher einem Profil zuordnen, Aufträge."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from appkern.anmeldung import Konto
from appkern.auftraege import Auftrag
from appkern.kellerwolke import Knoten, StandVeraltet

from .. import auswertung, export
from ..ablage import orte
from ..arten import AuswertenEingabe, KorrigierenEingabe, SprecherEingabe
from ..modell.sprecherprofil import Probe, Profil
from ..modell.transkript import Aenderung, Marker, Quelle, Segment, Sprecher, Transkript, woerter_angleichen
from ..suchindex import Notiz, Seite
from ..teile import Teile
from ..vorschlaege import Entscheidung, OffenerVorschlag
from .fehler import Konflikt
from .gemeinsam import von


class TranskriptAntwort(BaseModel):
    id: UUID
    pfad: str
    stand: str
    transkript: Transkript


class SprecherAenderung(BaseModel):
    """Ein Sprecher, wie die Oberfläche ihn ändert (Stimmabdruck und Profil bleiben aus der Datei)."""

    kennung: str
    name: str = Field(min_length=1, max_length=120)


class Aenderungen(BaseModel):
    stand: str = Field(description="zuletzt gelesener Stand; sonst 409")
    name: str | None = Field(None, min_length=1, max_length=200)
    segmente: list[Segment] | None = None
    sprecher: list[SprecherAenderung] | None = None
    marker: list[Marker] | None = None
    was: str | None = Field(None, max_length=300, description="Notiz zur Version; leer: wird beschrieben")
    vorschlaege: list[Entscheidung] = Field(default_factory=list, description="übernommene und verworfene Vorschläge")


class LiveStueck(BaseModel):
    start: float = Field(ge=0)
    ende: float = Field(ge=0)
    text: str = Field(min_length=1)


class AusMitschrift(BaseModel):
    """Ein Transkript aus der Live-Mitschrift einer Aufnahme (ohne Sprecher; genauer wird es mit Transkribieren)."""

    quelle_id: UUID
    name: str = Field(min_length=1, max_length=200)
    sprache: str = "de"
    stuecke: list[LiveStueck] = Field(min_length=1)


class StandEingabe(BaseModel):
    stand: str


class ProfilZuordnung(BaseModel):
    stand: str
    profil_id: UUID | None = Field(None, description="vorhandenes Profil; sonst entsteht eins mit `name`")
    name: str | None = Field(None, min_length=1, max_length=120)


class Version(BaseModel):
    id: UUID
    groesse: int
    erstellt_am: datetime
    aktuell: bool
    notiz: Notiz | None = None


class ExportEingabe(BaseModel):
    format: export.Format


class ErkennenEingabe(BaseModel):
    weg: Literal["stimmen", "trennung"] = Field("stimmen", description="Stimmen gruppieren oder erst die Sprechertrennung fragen")
    anzahl: int | None = Field(None, ge=1, le=20, description="bekannte Zahl der Sprecher")


class VorlageEingabe(BaseModel):
    vorlage: auswertung.Vorlage = "protokoll"


def _ohne_abdruck(t: Transkript) -> Transkript:
    return t.model_copy(update={"sprecher": [s.model_copy(update={"abdruck": None}) for s in t.sprecher]})


def _antwort(t: Transkript, knoten: Knoten) -> TranskriptAntwort:
    return TranskriptAntwort(id=knoten.id, pfad=knoten.pfad, stand=knoten.etag or "", transkript=_ohne_abdruck(t))


def _beschreiben(alt: Transkript, a: Aenderungen) -> str:
    teile = []
    if a.name is not None and a.name != alt.name:
        teile.append(f"Name: {a.name}")
    if a.segmente is not None:
        alte = {(s.start, s.text) for s in alt.segmente}
        n = sum((s.start, s.text) not in alte for s in a.segmente)
        if len(a.segmente) != len(alt.segmente):
            teile.append(f"{len(a.segmente)} statt {len(alt.segmente)} Segmente")
        elif n:
            teile.append(f"Text in {n} Segment{'en' if n != 1 else ''}")
    if a.sprecher is not None:
        alte_namen = {s.kennung: s.name for s in alt.sprecher}
        for s in a.sprecher:
            if alte_namen.get(s.kennung) not in (None, s.name):
                teile.append(f"{alte_namen[s.kennung]} heißt {s.name}")
    if a.marker is not None and [(m.zeit, m.titel) for m in a.marker] != [(m.zeit, m.titel) for m in alt.marker]:
        teile.append("Marker")
    if a.vorschlaege:
        n = sum(e.zustand == "uebernommen" for e in a.vorschlaege)
        if n:
            teile.append(f"{n} Vorschl{'äge' if n != 1 else 'ag'} der KI übernommen")
    return ", ".join(teile)[:300] or "geändert"


def router(teile: Teile) -> APIRouter:
    g = teile.geruest
    r = APIRouter(prefix="/api/v1/transkripte", tags=["transkripte"], dependencies=[g.pflicht])

    async def lesen(transkript_id: UUID) -> tuple[Transkript, Knoten]:
        return await teile.transkripte.lesen(transkript_id)

    async def schreiben(transkript_id: UUID, t: Transkript, stand: str, aenderung: Aenderung) -> TranskriptAntwort:
        try:
            neu, knoten = await teile.transkripte.schreiben(transkript_id, t, stand, aenderung)
        except StandVeraltet as f:
            raise Konflikt("Inzwischen geändert: bitte neu laden und dann ändern") from f
        await teile.index.eintragen(neu, knoten)
        return _antwort(neu, knoten)

    @r.get("", response_model=Seite)
    async def liste(suche: str = "", sprache: str | None = None, sprecher: list[str] = Query(default_factory=list),
                    ab: int = Query(0, ge=0), anzahl: int = Query(20, ge=1, le=100)) -> Seite:
        return await teile.index.seite(suche=suche.strip(), sprache=sprache or None, sprecher=sprecher, ab=ab,
                                       anzahl=anzahl)

    @r.post("", status_code=201, response_model=TranskriptAntwort)
    async def aus_mitschrift(e: AusMitschrift, konto: Konto = g.pflicht) -> TranskriptAntwort:
        """Legt ein Transkript aus der Live-Mitschrift an; die Wortzeiten werden über jedes Stück verteilt."""
        kw = teile.transkripte.kw
        quelle = await kw.knoten(e.quelle_id)
        if orte.art_der_aufnahme(quelle) is None:
            raise HTTPException(422, f"{quelle.name} ist keine Ton- oder Videodatei")
        segmente = [woerter_angleichen(Segment(start=x.start, ende=max(x.ende, x.start), text=x.text.strip())) for x in e.stuecke]
        marker = [Marker(zeit=m["zeit"], titel=m["titel"]) for m in quelle.felder.get(orte.FELD_MARKER) or []
                  if isinstance(m, dict) and "zeit" in m and m.get("titel")]
        t = Transkript(name=e.name, quelle=Quelle(knoten_id=quelle.id, pfad=quelle.pfad, etag=quelle.etag), sprache=e.sprache,
                       dauer_s=round(max(x.ende for x in e.stuecke), 3), segmente=segmente, marker=marker,
                       aenderung=Aenderung(was="aus der Live-Mitschrift", wer=konto.name, app=konto.app))
        knoten = await teile.transkripte.anlegen(t, quelle)
        neu, knoten = await lesen(knoten.id)
        await teile.index.eintragen(neu, knoten)
        return _antwort(neu, knoten)

    @r.get("/sprecher-namen", response_model=list[str])
    async def sprecher_namen() -> list[str]:
        return await teile.index.sprecher_namen()

    @r.get("/{transkript_id}", response_model=TranskriptAntwort)
    async def holen(transkript_id: UUID) -> TranskriptAntwort:
        return _antwort(*await lesen(transkript_id))

    @r.patch("/{transkript_id}", response_model=TranskriptAntwort)
    async def aendern(transkript_id: UUID, a: Aenderungen, konto: Konto = g.pflicht) -> TranskriptAntwort:
        alt, knoten = await lesen(transkript_id)
        if knoten.etag != a.stand:
            raise Konflikt("Inzwischen geändert: bitte neu laden und dann ändern")
        daten = alt.model_dump()
        if a.name is not None:
            daten["name"] = a.name
        if a.segmente is not None:
            daten["segmente"] = [woerter_angleichen(s).model_dump() for s in a.segmente]
        if a.sprecher is not None:
            bisher = {s.kennung: s for s in alt.sprecher}
            daten["sprecher"] = [(bisher[s.kennung].model_copy(update={"name": s.name}) if s.kennung in bisher
                                  else Sprecher(kennung=s.kennung, name=s.name)).model_dump() for s in a.sprecher]
        if a.marker is not None:
            daten["marker"] = [m.model_dump() for m in a.marker]
        try:
            neu = Transkript.model_validate(daten)
        except ValueError as f:
            raise HTTPException(422, str(f)) from f
        antwort = await schreiben(transkript_id, neu, a.stand,
                                  Aenderung(was=a.was or _beschreiben(alt, a), wer=konto.name, app=konto.app))
        if a.vorschlaege:
            await teile.vorschlaege.entscheiden(transkript_id, a.vorschlaege)
        return antwort

    @r.delete("/{transkript_id}", status_code=204)
    async def loeschen(transkript_id: UUID, konto: Konto = g.pflicht) -> None:
        eintrag = await teile.index.eintrag(transkript_id)
        await teile.transkripte.loeschen(transkript_id)
        await teile.index.entfernen(transkript_id)
        await teile.vorschlaege.entfernen(transkript_id)
        await g.protokoll.eintragen("transkript.geloescht", f"{eintrag.name if eintrag else transkript_id} in den Papierkorb",
                                    bezug_art="transkript", bezug_name=von(konto))

    # --- Versionen ------------------------------------------------------------------------------------------------

    @r.get("/{transkript_id}/versionen", response_model=list[Version])
    async def versionen(transkript_id: UUID) -> list[Version]:
        notizen = await teile.index.notizen(transkript_id)
        return [Version(id=v.id, groesse=v.groesse, erstellt_am=v.erstellt_am, aktuell=v.aktuell,
                        notiz=notizen.get(str(v.id))) for v in await teile.transkripte.versionen(transkript_id)]

    @r.get("/{transkript_id}/versionen/{version_id}", response_model=Transkript)
    async def version(transkript_id: UUID, version_id: UUID) -> Transkript:
        return _ohne_abdruck(await teile.transkripte.version(transkript_id, version_id))

    @r.post("/{transkript_id}/versionen/{version_id}/zurueck", response_model=TranskriptAntwort)
    async def zurueckholen(transkript_id: UUID, version_id: UUID, eingabe: StandEingabe,
                           konto: Konto = g.pflicht) -> TranskriptAntwort:
        try:
            neu, knoten = await teile.transkripte.zurueckholen(transkript_id, version_id, eingabe.stand, konto.name,
                                                               konto.app)
        except StandVeraltet as f:
            raise Konflikt("Inzwischen geändert: bitte neu laden") from f
        await teile.index.eintragen(neu, knoten)
        return _antwort(neu, knoten)

    # --- Export als Datei, Vorschläge -----------------------------------------------------------------------------

    @r.post("/{transkript_id}/export", status_code=201)
    async def ablegen(transkript_id: UUID, eingabe: ExportEingabe) -> dict:
        """Export als Datei neben das Transkript (der Download liegt unter /api/v1/inhalt)."""
        t, knoten = await lesen(transkript_id)
        kw = teile.transkripte.kw
        typ, endung = export.FORMATE[eingabe.format]
        ordner = knoten.pfad.rsplit("/", 1)[0]
        n = 1
        while await kw.finden(orte.ort(ordner, f"{t.name}{f' ({n})' if n > 1 else ''}{endung}")) is not None:
            n += 1
        datei = await kw.schreiben(orte.ort(ordner, f"{t.name}{f' ({n})' if n > 1 else ''}{endung}"),
                                   export.erzeugen(t, eingabe.format), nur_neu=True, inhaltstyp=typ)
        await kw.herkunft_setzen(datei.id, knoten.id, "abgeleitet_von")
        return {"id": str(datei.id), "pfad": datei.pfad, "name": datei.name}

    @r.get("/{transkript_id}/vorschlaege", response_model=list[OffenerVorschlag])
    async def vorschlaege(transkript_id: UUID) -> list[OffenerVorschlag]:
        return await teile.vorschlaege.offene(transkript_id)

    # --- Sprecher einem Profil zuordnen ---------------------------------------------------------------------------

    @r.post("/{transkript_id}/sprecher/{kennung}/profil", response_model=TranskriptAntwort)
    async def profil_zuordnen(transkript_id: UUID, kennung: str, z: ProfilZuordnung,
                              konto: Konto = g.pflicht) -> TranskriptAntwort:
        """Bestätigt die Stimme eines Sprechers als Profil (vorhanden oder neu mit `name`): der Sprecher trägt danach
        Namen und Profil, sein Abdruck schärft das Profil."""
        t, knoten = await lesen(transkript_id)
        if knoten.etag != z.stand:
            raise Konflikt("Inzwischen geändert: bitte neu laden und dann ändern")
        sprecher = next((s for s in t.sprecher if s.kennung == kennung), None)
        if sprecher is None:
            raise HTTPException(404, f"Sprecher {kennung} gibt es in diesem Transkript nicht")
        if z.profil_id is None and not z.name:
            raise HTTPException(422, "Profil oder Name angeben")
        beispiel = next((s for s in t.segmente if s.sprecher == kennung and s.ende - s.start >= 2), None)
        probe = Probe(transkript_id=transkript_id, start=beispiel.start, ende=beispiel.ende,
                      text=beispiel.text[:120]) if beispiel else None

        def zuordnen(profile) -> Profil:
            profil = profile.holen(z.profil_id) if z.profil_id else next(
                (p for p in profile.profile if p.name.lower() == (z.name or "").lower()), None)
            if profil is None:
                if z.profil_id:
                    raise HTTPException(404, "Profil nicht gefunden")
                profil = Profil(name=z.name)
                profile.profile.append(profil)
            if sprecher.abdruck:
                profil.einmischen(sprecher.abdruck, probe)
            return profil

        profil = await teile.profile.aendern(zuordnen)
        neu = t.model_copy(update={"sprecher": [s.model_copy(update={
            "name": profil.name, "profil_id": profil.id, "vorschlag_id": None, "vorschlag_aehnlichkeit": None})
            if s.kennung == kennung else s for s in t.sprecher]})
        return await schreiben(transkript_id, neu, z.stand,
                               Aenderung(was=f"{sprecher.name} ist {profil.name}", wer=konto.name, app=konto.app))

    # --- Aufträge -------------------------------------------------------------------------------------------------

    @r.post("/{transkript_id}/sprecher-erkennen", status_code=201, response_model=Auftrag)
    async def sprecher_erkennen(transkript_id: UUID, eingabe: ErkennenEingabe, konto: Konto = g.pflicht) -> Auftrag:
        """Nur auf ausdrücklichen Wunsch; ersetzt die Zuordnung (der alte Stand bleibt als Version)."""
        t, _ = await lesen(transkript_id)
        return await g.auftraege.einreihen("sprecher_erkennen", SprecherEingabe(
            transkript_id=transkript_id, weg=eingabe.weg, anzahl=eingabe.anzahl, von=von(konto)), titel=f"{t.name}: Sprecher")

    @r.post("/{transkript_id}/korrigieren", status_code=201, response_model=Auftrag)
    async def korrigieren(transkript_id: UUID, konto: Konto = g.pflicht) -> Auftrag:
        t, _ = await lesen(transkript_id)
        return await g.auftraege.einreihen("korrigieren", KorrigierenEingabe(transkript_id=transkript_id, von=von(konto)),
                                           titel=f"{t.name}: Korrektur")

    @r.post("/{transkript_id}/auswerten", status_code=201, response_model=Auftrag)
    async def auswerten(transkript_id: UUID, eingabe: VorlageEingabe, konto: Konto = g.pflicht) -> Auftrag:
        t, _ = await lesen(transkript_id)
        return await g.auftraege.einreihen("auswerten", AuswertenEingabe(
            transkript_id=transkript_id, vorlage=eingabe.vorlage, von=von(konto)),
            titel=f"{t.name}: {auswertung.titel(eingabe.vorlage)}")

    return r

