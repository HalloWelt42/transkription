"""Transkripte als Dateien in der Kellerwolke: anlegen (eindeutiger Name, Herkunft zur Aufnahme), lesen mit Stand,
schreiben nur mit dem zuletzt gelesenen Stand, Versionen lesen und zurückholen, in den Papierkorb legen.

Der Stand ist der ETag der Datei in der Kellerwolke (er ist zugleich die Kennung der Version). Wer mit einem veralteten
Stand schreibt, bekommt `StandVeraltet` und muss neu lesen; so überschreibt niemand still die Arbeit eines anderen.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID

from appkern.kellerwolke import Kellerwolke, Knoten, StandVeraltet, Version

from ..modell.transkript import Aenderung, Transkript, jetzt
from . import orte

HERKUNFT = "transkript_zu"
FELD_ART = "art"
FELD_QUELLE = "quelle_id"


class KeineKellerwolke(Exception):
    """Die App ist noch nicht mit einer Kellerwolke verbunden."""


def zugang(liefern: Callable[[], Kellerwolke | None]) -> Kellerwolke:
    kw = liefern()
    if kw is None:
        raise KeineKellerwolke("Keine Kellerwolke eingerichtet")
    return kw


def _inhalt(t: Transkript) -> bytes:
    return t.model_dump_json(indent=1, exclude_none=True).encode("utf-8")


class Transkripte:
    def __init__(self, kellerwolke: Callable[[], Kellerwolke | None]) -> None:
        """`kellerwolke` liefert den aktuellen Zugang (er wird nach geänderten Einstellungen neu gebaut)."""
        self._kw = kellerwolke

    @property
    def kw(self) -> Kellerwolke:
        return zugang(self._kw)

    async def ordner(self) -> Knoten:
        kw = self.kw
        return await kw.ordner(orte.ort((await kw.ich()).zweig, orte.TRANSKRIPTE))

    async def anlegen(self, t: Transkript, quelle: Knoten | None = None) -> Knoten:
        """Neue Datei mit eindeutigem Namen; mit `quelle` auch die Herkunft und das Suchfeld zur Aufnahme."""
        kw = self.kw
        ordner = await self.ordner()
        zusatz = 0
        while True:
            zusatz += 1
            try:
                knoten = await kw.schreiben(orte.ort(ordner.pfad, orte.dateiname(t.name, zusatz)), _inhalt(t),
                                            nur_neu=True, inhaltstyp=orte.INHALTSTYP)
                break
            except StandVeraltet:
                if zusatz >= 500:
                    raise
        felder = {FELD_ART: "transkript"}
        if quelle is not None:
            await kw.herkunft_setzen(knoten.id, quelle.id, HERKUNFT)
            felder[FELD_QUELLE] = str(quelle.id)
        return await kw.felder_setzen(knoten.id, felder)

    async def lesen(self, transkript_id: UUID | str) -> tuple[Transkript, Knoten]:
        kw = self.kw
        knoten = await kw.knoten(transkript_id)
        return Transkript.model_validate_json(await kw.lesen_ganz(transkript_id)), knoten

    async def schreiben(self, transkript_id: UUID | str, t: Transkript, stand: str, aenderung: Aenderung) -> Knoten:
        """Neue Version mit dem zuletzt gelesenen Stand; sonst `StandVeraltet`."""
        t = t.model_copy(update={"geaendert_am": jetzt(), "aenderung": aenderung})
        return await self.kw.neue_version(transkript_id, _inhalt(t), stand=stand, inhaltstyp=orte.INHALTSTYP)

    async def versionen(self, transkript_id: UUID | str) -> list[Version]:
        return await self.kw.versionen(transkript_id)

    async def version(self, transkript_id: UUID | str, version_id: UUID | str) -> Transkript:
        return Transkript.model_validate_json(await self.kw.version_ganz(transkript_id, version_id))

    async def zurueckholen(self, transkript_id: UUID | str, version_id: UUID | str, stand: str, wer: str | None,
                           app: str | None = None) -> Knoten:
        alt = await self.version(transkript_id, version_id)
        was = f"Fassung vom {alt.geaendert_am:%d.%m.%Y %H:%M} zurückgeholt"
        return await self.schreiben(transkript_id, alt, stand, Aenderung(was=was, wer=wer, app=app))

    async def loeschen(self, transkript_id: UUID | str) -> None:
        """In den Papierkorb der Kellerwolke; die Aufnahme bleibt."""
        await self.kw.loeschen(transkript_id)

    async def zur_quelle(self, quelle_id: UUID | str) -> list[Knoten]:
        """Transkripte einer Aufnahme (über das Suchfeld, neueste zuerst)."""
        return await self.kw.suchen({FELD_ART: "transkript", FELD_QUELLE: str(quelle_id)}, anzahl=20)

    async def alle(self) -> AsyncIterator[Knoten]:
        kw = self.kw
        ordner = await self.ordner()
        async for k in kw.alle_kinder(ordner.id):
            if orte.ist_transkript(k):
                yield k
