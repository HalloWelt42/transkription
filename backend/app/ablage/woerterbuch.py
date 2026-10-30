"""Das Fachwörter-Wörterbuch als eine Datei in der Kellerwolke (`Fachwörter.json` im Zweig der App). Ändern heißt
lesen, ändern, mit dem Stand schreiben; trifft ein anderer Schreiber dazwischen, beginnt die Änderung neu."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from appkern.kellerwolke import Kellerwolke, NichtGefunden, StandVeraltet

from ..modell.woerterbuch import START, Woerterbuch
from . import orte
from .transkripte import zugang

T = TypeVar("T")
_VERSUCHE = 5


class Fachwoerter:
    def __init__(self, kellerwolke: Callable[[], Kellerwolke | None]) -> None:
        self._kw = kellerwolke

    async def _pfad(self, kw: Kellerwolke) -> str:
        return orte.ort((await kw.ich()).zweig, orte.WOERTERBUCH)

    async def lesen(self) -> tuple[Woerterbuch, str | None]:
        """Wörterbuch und Stand (None, solange es die Datei nicht gibt: dann der Startinhalt)."""
        kw = zugang(self._kw)
        try:
            knoten = await kw.pfad(await self._pfad(kw))
        except NichtGefunden:
            return Woerterbuch(woerter=START), None
        return Woerterbuch.model_validate_json(await kw.lesen_ganz(knoten.id)), knoten.etag

    async def aendern(self, aenderung: Callable[[Woerterbuch], T]) -> tuple[Woerterbuch, T]:
        """`aenderung` ändert das Wörterbuch an Ort und Stelle (ohne Nebenwirkungen, sie kann wiederholt werden)."""
        kw = zugang(self._kw)
        pfad = await self._pfad(kw)
        for versuch in range(_VERSUCHE):
            wb, stand = await self.lesen()
            ergebnis = aenderung(wb)
            inhalt = wb.model_dump_json(indent=1).encode("utf-8")
            try:
                if stand is None:
                    await kw.schreiben(pfad, inhalt, nur_neu=True, inhaltstyp=orte.INHALTSTYP)
                else:
                    await kw.schreiben(pfad, inhalt, stand=stand, inhaltstyp=orte.INHALTSTYP)
                return wb, ergebnis
            except StandVeraltet:
                if versuch == _VERSUCHE - 1:
                    raise
        raise AssertionError("unerreichbar")
