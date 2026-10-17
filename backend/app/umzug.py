"""Eine Ablage (Entscheidung 17.10.2026): die frühere getrennte Ablage zusammenführen.

Früher lagen Transkripte unter `Transkripte/<Unterordner>/`, getrennt von den Aufnahmen. Jetzt ist das Transkript ein
Begleiter neben seiner Aufnahme. Der Plan zeigt vorher, was wohin kommt (Vorschau, nichts geschieht); der Auftrag
`zusammenfuehren` führt ihn aus und setzt nach einem Abbruch fort. Gelöscht wird nichts:

- je Aufnahme wird das neueste Transkript ihr Begleiter (die Kellerwolke vergibt den Namen neben ihr);
- weitere Transkripte derselben Aufnahme (früher entstand bei jedem Transkribieren ein neues) kommen als eigene
  Dateien neben die Aufnahme;
- Transkripte ohne lebende Aufnahme kommen in den gleichen Unterordner unter Aufnahmen;
- der dann leere Ordner Transkripte geht in den Papierkorb der Kellerwolke; liegen dort noch andere Dateien, bleibt er.

Nötig ist das Zusammenführen, solange dort Transkripte liegen oder der Ordner leer im Weg steht.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ValidationError

from appkern.auftraege import Kontext
from appkern.kellerwolke import Kellerwolke, KellerwolkeFehler, Knoten, NichtGefunden

from .ablage import orte
from .modell.transkript import Transkript
from .teile import Teile

Art = Literal["begleiter", "daneben", "ohne_aufnahme", "ordner"]


class Schritt(BaseModel):
    art: Art
    knoten_id: UUID                    # das Transkript (bei "ordner" der Ordner Transkripte)
    von: str                           # Pfad jetzt
    nach: str                          # Pfad danach (vorhergesagt; belegte Namen bekommen einen Zusatz)
    aufnahme_id: UUID | None = None


class Plan(BaseModel):
    noetig: bool
    schritte: list[Schritt]
    zahlen: dict[str, int]


async def _dateien(kw: Kellerwolke, ordner: Knoten) -> AsyncIterator[Knoten]:
    offen = [ordner.id]
    while offen:
        async for k in kw.alle_kinder(offen.pop()):
            if k.ist_ordner:
                offen.append(k.id)
            else:
                yield k


async def _quelle(teile: Teile, kw: Kellerwolke, t: Knoten) -> UUID | None:
    """Die Aufnahme eines Transkripts: aus dem Verzeichnis, sonst aus der Datei selbst."""
    eintrag = await teile.index.eintrag(t.id)
    if eintrag is not None and eintrag.quelle_id:
        return UUID(str(eintrag.quelle_id))
    try:
        inhalt = Transkript.model_validate_json(await kw.lesen_ganz(t.id))
    except (ValidationError, KellerwolkeFehler):
        return None
    return inhalt.quelle.knoten_id if inhalt.quelle else None


async def _aufnahme(kw: Kellerwolke, quelle_id: UUID | None) -> Knoten | None:
    if quelle_id is None:
        return None
    try:
        k = await kw.knoten(quelle_id)
    except NichtGefunden:
        return None
    return k if orte.art_der_aufnahme(k) else None


def _unter(alt: Knoten, pfad: str) -> str:
    """Unterordner einer Datei unter dem früheren Ordner Transkripte ("" direkt dort)."""
    rest = pfad[len(alt.pfad) + 1:] if pfad.startswith(alt.pfad + "/") else PurePosixPath(pfad).name
    return str(PurePosixPath(rest).parent).strip(".")


async def planen(teile: Teile) -> Plan:
    kw = teile.zugang()
    zweig = (await kw.ich()).zweig
    alt = await kw.finden(orte.ort(zweig, orte.ALT_TRANSKRIPTE))
    if alt is None:
        return Plan(noetig=False, schritte=[], zahlen={})
    aufnahmen = await teile.transkripte.ordner()
    je_aufnahme: dict[UUID, list[tuple[Knoten, Knoten]]] = {}
    ohne: list[Knoten] = []
    andere = 0                                         # Dateien dort, die keine Transkripte sind: bleiben, Ordner auch
    async for t in _dateien(kw, alt):
        if not orte.ist_transkript(t):
            andere += 1
            continue
        a = await _aufnahme(kw, await _quelle(teile, kw, t))
        if a is None:
            ohne.append(t)
        else:
            je_aufnahme.setdefault(a.id, []).append((t, a))
    schritte: list[Schritt] = []
    for liste in je_aufnahme.values():
        liste.sort(key=lambda x: x[0].geaendert_am, reverse=True)
        for n, (t, a) in enumerate(liste):
            ordner = str(PurePosixPath(a.pfad).parent)
            if n == 0 and not await teile.transkripte.fuer(kw).zur_quelle(a.id):
                stamm = PurePosixPath(a.name).stem
                schritte.append(Schritt(art="begleiter", knoten_id=t.id, von=t.pfad, nach=f"{ordner}/{stamm}{orte.ENDUNG}",
                                        aufnahme_id=a.id))
            else:
                schritte.append(Schritt(art="daneben", knoten_id=t.id, von=t.pfad, nach=f"{ordner}/{t.name}",
                                        aufnahme_id=a.id))
    for t in ohne:
        unter = _unter(alt, t.pfad)
        schritte.append(Schritt(art="ohne_aufnahme", knoten_id=t.id, von=t.pfad,
                                nach=orte.ort(aufnahmen.pfad, *([unter] if unter else []), t.name)))
    if not andere:
        schritte.append(Schritt(art="ordner", knoten_id=alt.id, von=alt.pfad, nach="Papierkorb"))
    zahlen = {art: sum(s.art == art for s in schritte) for art in ("begleiter", "daneben", "ohne_aufnahme")}
    return Plan(noetig=bool(schritte), schritte=schritte, zahlen=zahlen)


async def _frei(kw: Kellerwolke, ordner_pfad: str, name: str) -> str:
    """Ein freier Name im Ordner: der eigene oder mit Zahl ("Runde (2).transkript.json")."""
    stamm, endung = (name[: -len(orte.ENDUNG)], orte.ENDUNG) if name.endswith(orte.ENDUNG) else \
        (PurePosixPath(name).stem, PurePosixPath(name).suffix)
    n = 1
    while await kw.finden(orte.ort(ordner_pfad, f"{stamm}{f' ({n})' if n > 1 else ''}{endung}")) is not None:
        n += 1
    return f"{stamm}{f' ({n})' if n > 1 else ''}{endung}"


async def ausfuehren(teile: Teile, k: Kontext) -> dict:
    """Den Plan Schritt für Schritt; erledigte Schritte merkt der Auftrag, ein Neustart setzt fort."""
    kw = teile.zugang()
    plan = await planen(teile)
    erledigt = set(k.zwischenstand.get("erledigt", []))
    zahl = 0
    for n, s in enumerate(plan.schritte):
        await k.pruefen()
        if str(s.knoten_id) in erledigt:
            continue
        await k.fortschritt(n / max(len(plan.schritte), 1), f"{PurePosixPath(s.von).name}")
        if s.art == "begleiter" and s.aufnahme_id:
            await kw.begleiter_anhaengen(s.aufnahme_id, orte.ROLLE, s.knoten_id, orte.ENDUNG)
        elif s.art in ("daneben", "ohne_aufnahme"):
            ziel_pfad = str(PurePosixPath(s.nach).parent)
            ziel = await kw.ordner(ziel_pfad)
            await kw.umziehen(s.knoten_id, ziel.id, await _frei(kw, ziel_pfad, PurePosixPath(s.von).name))
        elif s.art == "ordner":
            alt = await kw.knoten(s.knoten_id)
            if not [d async for d in _dateien(kw, alt)]:
                await kw.loeschen(alt.id)
        zahl += s.art != "ordner"
        erledigt.add(str(s.knoten_id))
        await k.merken(erledigt=sorted(erledigt))
    await teile.abgleich.vollstaendig()
    await teile.geruest.protokoll.eintragen("ablage.zusammengefuehrt", f"{zahl} Transkripte neben ihre Aufnahmen",
                                            bezug_art="ablage")
    return {"verschoben": zahl}
