"""Aufnahmen: Ton- und Videodateien im Ordner Aufnahmen (ihre Transkripte liegen als Begleiter daneben) und in Ordnern,
die der Nutzer der App freigegeben hat; mit Stand (ohne Transkript, wartet, läuft, transkribiert). Hochladen gestreamt
nach Aufnahmen; Transkribieren als Auftrag, auch für Dateien aus der ganzen Kellerwolke (über eine Anfrage, nur für
diesen Auftrag). Dazu das Zusammenführen der früheren getrennten Ablage mit Vorschau."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from appkern.anmeldung import Konto
from appkern.anmeldung.api import KOPF
from appkern.auftraege import Auftrag
from appkern.kellerwolke import Kellerwolke, KellerwolkeFehler, Knoten

from .. import umzug
from ..ablage import orte
from ..arten import TranskribierenAnfrage, TranskribierenEingabe
from ..einstellungen import SprecherWeg
from ..sprachen import Sprache, SpracheEintrag
from ..mitlesen import Bisher
from ..teile import Teile
from .gemeinsam import von

AUFTRAGSARTEN = ["transkribieren", "aus_anfrage"]

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
    dauer_s: float | None = None
    geaendert_am: datetime
    stand: Stand
    transkripte: list[TranskriptVerweis]
    auftrag: AuftragKurz | None = None
    marker: list["MarkerEingabe"] = Field(default_factory=list, description="beim Aufnehmen oder Anhören gesetzt")


class AufnahmenSeite(BaseModel):
    ordner: Ordner
    unterordner: list[Ordner]
    gesamt: int
    zahlen: dict[str, int]
    eintraege: list[Aufnahme]


class MarkerEingabe(BaseModel):
    zeit: float = Field(ge=0)
    titel: str = Field(min_length=1, max_length=200)


class AusKellerwolke(BaseModel):
    """Dateien aus der ganzen Kellerwolke transkribieren (gewählt in der App); das Transkript kommt neben die Datei."""

    knoten_ids: list[UUID] = Field(min_length=1, max_length=50)
    sprache: Sprache | None = None
    sprecher: SprecherWeg | None = None
    anzahl: int | None = Field(None, ge=1, le=20)
    hoerdienst: str | None = Field(None, max_length=120, description="Hördienst der Leitstelle; leer: der eingestellte")


class Hoerdienst(BaseModel):
    """Ein Hördienst zur Wahl beim Transkribieren (was die Leitstelle dieser App mit der Fähigkeit hoeren anbietet)."""

    kennung: str
    name: str
    hinweis: str = ""
    vorgabe: bool = False


def _quelle_von(auftrag) -> str:
    """Die Aufnahme eines laufenden Auftrags (Transkribieren nennt quelle_id, eine Anfrage knoten_id)."""
    return str(auftrag.eingabe.get("quelle_id") or auftrag.eingabe.get("knoten_id"))


Aufnahme.model_rebuild()


def aufnahme_aus(k, verweise: list[TranskriptVerweis], auftrag, transkript_dauer: float | None) -> Aufnahme:
    """Ein Eintrag aus dem Knoten der Kellerwolke, gleich für Liste und Einzelansicht."""
    stand: Stand = ("laeuft" if auftrag.zustand == "laeuft" else "wartet") if auftrag else \
        ("transkribiert" if verweise else "ohne")
    marker = [MarkerEingabe.model_validate(m) for m in (k.felder.get(orte.FELD_MARKER) or [])]
    return Aufnahme(
        id=k.id, name=k.name, pfad=k.pfad, art=orte.art_der_aufnahme(k), groesse=k.groesse, inhaltstyp=k.inhaltstyp,
        dauer_s=k.felder.get(orte.FELD_DAUER) or transkript_dauer, geaendert_am=k.geaendert_am, stand=stand,
        transkripte=verweise, marker=marker,
        auftrag=AuftragKurz(id=auftrag.id, zustand=auftrag.zustand, fortschritt=auftrag.fortschritt, schritt=auftrag.schritt,
                            phase=auftrag.phase) if auftrag else None)


ORDNER_HOECHSTENS = 500          # so viele Ordner durchsucht die Namenssuche höchstens (Schutz vor riesigen Bäumen)


async def ordner_lesen(kw: Kellerwolke, ordner_id: UUID) -> tuple[list[Ordner], list[Knoten]]:
    """Unterordner und Aufnahmen direkt in einem Ordner."""
    unterordner, dateien = [], []
    async for k in kw.alle_kinder(ordner_id):
        if k.ist_ordner:
            unterordner.append(Ordner(id=k.id, name=k.name, pfad=k.pfad, recht=k.recht))
        elif orte.art_der_aufnahme(k):
            dateien.append(k)
    return unterordner, dateien


async def durchsuchen(kw: Kellerwolke, ort: Knoten, suche: str) -> tuple[list[Ordner], list[Knoten]]:
    """Ordner und Aufnahmen unter `ort` samt allen Unterordnern, deren Name den Suchtext enthält (Groß und Klein egal)."""
    gesucht = suche.casefold()
    ordner_treffer, dateien, offen, gesehen = [], [], [ort.id], 0
    while offen and gesehen < ORDNER_HOECHSTENS:
        aktuell = offen.pop(0)
        gesehen += 1
        unter, darin = await ordner_lesen(kw, aktuell)
        dateien += [k for k in darin if gesucht in k.name.casefold()]
        ordner_treffer += [o for o in unter if gesucht in o.name.casefold()]
        offen += [o.id for o in unter]
    return ordner_treffer, dateien


def router(teile: Teile) -> APIRouter:
    g = teile.geruest
    r = APIRouter(prefix="/api/v1", tags=["aufnahmen"], dependencies=[g.pflicht])

    async def eigener_ordner():
        return await teile.transkripte.ordner()

    async def laufende() -> dict[str, object]:
        laufend: dict[str, object] = {}
        for art in AUFTRAGSARTEN:
            for a in (await g.auftraege.liste(zustand=["wartet", "laeuft"], art=art, grenze=500)).eintraege:
                laufend.setdefault(_quelle_von(a), a)
        return laufend

    @r.get("/aufnahmen/ordner", response_model=list[Ordner])
    async def ordner_liste() -> list[Ordner]:
        """Der eigene Ordner Aufnahmen und die Ordner, die der Nutzer der App außerhalb von Apps freigegeben hat."""
        kw = teile.zugang()
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
        kw = teile.zugang()
        ort = await kw.knoten(ordner) if ordner else await eigener_ordner()
        unterordner, dateien = await (durchsuchen(kw, ort, suche) if suche else ordner_lesen(kw, ort.id))
        transkripte = await teile.index.zur_quelle([str(k.id) for k in dateien])
        laufend = await laufende()
        alle: list[Aufnahme] = []
        for k in sorted(dateien, key=lambda k: k.geaendert_am, reverse=True):
            eintraege = transkripte.get(str(k.id), [])
            alle.append(aufnahme_aus(k, [TranskriptVerweis(id=e.id, name=e.name) for e in eintraege], laufend.get(str(k.id)),
                                     next((e.dauer_s for e in eintraege if e.dauer_s), None)))
        zahlen = {"alle": len(alle), "ohne": sum(a.stand != "transkribiert" for a in alle),
                  "transkribiert": sum(a.stand == "transkribiert" for a in alle)}
        gefiltert = [a for a in alle if filter == "alle" or (filter == "ohne") == (a.stand != "transkribiert")]
        return AufnahmenSeite(ordner=Ordner(id=ort.id, name=ort.name, pfad=ort.pfad, recht=ort.recht),
                              unterordner=sorted(unterordner, key=lambda o: o.name.lower()), gesamt=len(gefiltert),
                              zahlen=zahlen, eintraege=gefiltert[ab:ab + anzahl])

    @r.post("/aufnahmen", status_code=201, response_model=Aufnahme)
    async def hochladen(request: Request, name: str = Query(min_length=1, max_length=200),
                        ordner: str = Query("", max_length=300, description="Unterordner von Aufnahmen, etwa Besprechungen")) -> Aufnahme:
        """Körper ist der Inhalt (roh, gestreamt) in den eigenen Ordner Aufnahmen (oder einen Unterordner davon, der bei
        Bedarf entsteht); ein belegter Name bekommt eine Zahl angehängt."""
        kw = teile.zugang()
        ort = await eigener_ordner()
        if unter := orte.unterordner(ordner):
            ort = await kw.ordner(orte.ort(ort.pfad, unter))
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

    @r.get("/aufnahmen/{knoten_id}", response_model=Aufnahme)
    async def aufnahme(knoten_id: UUID, anfrage: UUID | None = None) -> Aufnahme:
        """Eine Aufnahme mit Stand, Transkript und Markern (Ansicht zum Anhören, auch ohne Transkript); mit `anfrage`
        auch eine Datei aus der Kellerwolke (geöffnet über das Dateimenü oder die Dateiwahl)."""
        kw = teile.zugang(anfrage)
        k = await kw.knoten(knoten_id)
        if orte.art_der_aufnahme(k) is None:
            raise HTTPException(422, f"{k.name} ist keine Ton- oder Videodatei")
        transkript = await teile.transkripte_fuer(anfrage).zur_quelle(k.id)
        eintrag = await teile.index.eintrag(transkript.id) if transkript else None
        verweise = [TranskriptVerweis(id=transkript.id, name=eintrag.name if eintrag else orte.anzeigename(k.name))] \
            if transkript else []
        return aufnahme_aus(k, verweise, (await laufende()).get(str(k.id)), eintrag.dauer_s if eintrag else None)

    @r.delete("/aufnahmen/{knoten_id}", status_code=204)
    async def aufnahme_loeschen(knoten_id: UUID, mit_transkripten: bool = False, konto: Konto = g.pflicht) -> None:
        """In den Papierkorb der Kellerwolke (dort zurückholbar), mit ihren Begleitern (Transkript, Untertitel ...).
        Ohne `mit_transkripten` behält das Transkript seinen Text: es löst sich aus der Gruppe und bleibt im Ordner."""
        kw = teile.zugang()
        k = await kw.knoten(knoten_id)
        if orte.art_der_aufnahme(k) is None:
            raise HTTPException(422, f"{k.name} ist keine Ton- oder Videodatei")
        transkript = await teile.transkripte.zur_quelle(k.id)
        if transkript is not None and not mit_transkripten:
            await kw.begleiter_loesen(transkript.id)
        await kw.loeschen(k.id)
        if transkript is not None and mit_transkripten:
            await teile.index.entfernen(transkript.id)
            await teile.vorschlaege.entfernen(transkript.id)
        teile.abspielen.vergessen(k.id)
        await g.protokoll.eintragen("aufnahme.geloescht", f"{k.name} in den Papierkorb", bezug_art="aufnahme",
                                    bezug_name=von(konto))

    @r.put("/aufnahmen/{knoten_id}/marker", response_model=list[MarkerEingabe])
    async def marker_setzen(knoten_id: UUID, marker: list[MarkerEingabe]) -> list[MarkerEingabe]:
        """Marker, die beim Aufnehmen gesetzt wurden; sie hängen an der Aufnahme und kommen ins Transkript."""
        kw = teile.zugang()
        if orte.art_der_aufnahme(await kw.knoten(knoten_id)) is None:
            raise HTTPException(422, "Keine Ton- oder Videodatei")
        await kw.felder_setzen(knoten_id, {orte.FELD_MARKER: [m.model_dump() for m in sorted(marker, key=lambda m: m.zeit)]})
        return marker

    @r.post("/transkribieren", status_code=201, response_model=Auftrag)
    async def transkribieren(anfrage: TranskribierenAnfrage, konto: Konto = g.pflicht) -> Auftrag:
        if anfrage.anfrage_id is not None:
            raise HTTPException(422, "Dateien aus der Kellerwolke über /kellerwolke/transkribieren")
        if len(set(anfrage.reihe)) != len(anfrage.reihe):
            raise HTTPException(422, "Jeder Hördienst höchstens einmal in der Reihe")
        hoerdienst = anfrage.reihe[0] if anfrage.reihe else anfrage.hoerdienst
        for dienst in anfrage.reihe or [hoerdienst]:              # vor aller Arbeit: kann jeder Hördienst die Sprache?
            await teile.sprachen.pruefen(anfrage.sprache, dienst)
        kw = teile.zugang()
        quelle = await kw.knoten(anfrage.quelle_id)
        if orte.art_der_aufnahme(quelle) is None:
            raise HTTPException(422, f"{quelle.name} ist keine Ton- oder Videodatei")
        if anfrage.bereich and await teile.transkripte_fuer(None).zur_quelle(quelle.id) is None:
            raise HTTPException(422, "Ein Ausschnitt kommt nur neben ein vorhandenes Transkript der Aufnahme")
        reihe_kennung = uuid4().hex if anfrage.reihe else None
        eingabe = TranskribierenEingabe(**{**anfrage.model_dump(), "hoerdienst": hoerdienst}, reihe_kennung=reihe_kennung,
                                        von=von(konto))
        titel = anfrage.name or orte.anzeigename(quelle.name)
        if anfrage.reihe:
            titel = f"{titel}: 1 von {len(anfrage.reihe)} Hördiensten"
        return await g.auftraege.einreihen("transkribieren", eingabe, titel=titel, stapel=reihe_kennung)

    @r.get("/sprachen", response_model=list[SpracheEintrag])
    async def sprachen(dienst: str | None = None) -> list[SpracheEintrag]:
        """Zur Wahl beim Transkribieren: Erkennen und was der Hördienst (ohne Angabe der eingestellte) laut Steckbrief
        kann, mit deutschem Namen."""
        return await teile.sprachen.liste(dienst)

    @r.get("/hoerdienste", response_model=list[Hoerdienst])
    async def hoerdienste() -> list[Hoerdienst]:
        """Zur Wahl beim Transkribieren: die Hördienste, die die Leitstelle dieser App anbietet (eine Wahrheit mit der
        Einstellung "Dienst zum Hören"); der eingestellte ist die Vorgabe. Die Leitstelle entscheidet nur, ob und wann
        einer rechnet, nie welcher."""
        vorgabe = teile.einstellungen.dienst_hoeren
        angebot = await g.leitstelle_angebot("hoeren")()
        aus = [Hoerdienst(kennung=o.wert, name=o.titel, hinweis=o.hinweis or "", vorgabe=o.wert == vorgabe)
               for o in angebot.optionen]
        if not any(d.vorgabe for d in aus):          # die Leitstelle antwortet nicht: wenigstens der eingestellte
            aus.insert(0, Hoerdienst(kennung=vorgabe, name=vorgabe, hinweis=angebot.stand, vorgabe=True))
        return aus

    @r.get("/transkribieren/{auftrag_id}/bisher", response_model=Bisher)
    async def bisher(auftrag_id: str) -> Bisher:
        """Mitlesen: was ein Auftrag zum Transkribieren schon gehört hat (je fertigem Abschnitt) und wie lange er
        geschätzt noch braucht."""
        stand = await teile.mitlesen.bisher(auftrag_id)
        if stand is None:
            raise HTTPException(404, "Kein Auftrag zum Transkribieren")
        return stand

    @r.post("/kellerwolke/transkribieren", status_code=201, response_model=list[str])
    async def aus_kellerwolke(e: AusKellerwolke, request: Request, konto: Konto = g.mensch) -> list[str]:
        """In der App gewählte Dateien aus der ganzen Kellerwolke: je Datei eine Anfrage an diese App (Recht nur für
        diesen Auftrag), ausgeführt mit den gewählten Optionen; liefert die Aufträge."""
        await teile.sprachen.pruefen(e.sprache, e.hoerdienst)
        kw = teile.zugang()
        sitzung = request.headers.get(KOPF, "")
        auftraege: list[str] = []
        try:
            for knoten_id in e.knoten_ids:
                neu = await kw.waehlen(sitzung, knoten_id, "transkribieren")
                eingabe = TranskribierenEingabe(quelle_id=knoten_id, anfrage_id=neu.anfrage.id, sprache=e.sprache,
                                                sprecher=e.sprecher, anzahl=e.anzahl, hoerdienst=e.hoerdienst, von=von(konto))
                auftrag_id = await g.abholer.uebernehmen(neu.anfrage, kw, auftrag="transkribieren",
                                                         eingabe=eingabe.model_dump(mode="json"),
                                                         titel=orte.anzeigename(neu.anfrage.knoten_name))
                if auftrag_id:
                    auftraege.append(auftrag_id)
        except KellerwolkeFehler as f:
            raise HTTPException(f.status if f.status in (403, 404, 409, 422) else 502, f.meldung) from f
        return auftraege

    # --- Eine Ablage: die frühere getrennte Ablage zusammenführen ---------------------------------------------------

    @r.get("/ablage/zusammenfuehren", response_model=umzug.Plan)
    async def zusammenfuehren_plan() -> umzug.Plan:
        """Vorschau: was wohin kommt; es geschieht nichts."""
        return await umzug.planen(teile)

    @r.post("/ablage/zusammenfuehren", status_code=201, response_model=Auftrag)
    async def zusammenfuehren(konto: Konto = g.mensch) -> Auftrag:
        laufend = (await g.auftraege.liste(zustand=["wartet", "laeuft"], art="zusammenfuehren")).eintraege
        if laufend:
            return laufend[0]
        return await g.auftraege.einreihen("zusammenfuehren", {"von": von(konto)}, titel="Ablage zusammenführen")

    return r
