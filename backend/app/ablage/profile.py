"""Sprecherprofile als eine Datei in der Kellerwolke (`Sprecher/profile.json`). Ändern heißt lesen, ändern, mit dem
Stand schreiben; trifft ein anderer Schreiber dazwischen, beginnt die Änderung mit dem neuen Stand noch einmal."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from appkern.kellerwolke import Kellerwolke, NichtGefunden, StandVeraltet

from ..modell.sprecherprofil import Profile
from . import orte
from .transkripte import zugang

T = TypeVar("T")
_VERSUCHE = 5


class Sprecherprofile:
    def __init__(self, kellerwolke: Callable[[], Kellerwolke | None]) -> None:
        self._kw = kellerwolke

    async def _pfad(self, kw: Kellerwolke) -> str:
        return orte.ort((await kw.ich()).zweig, orte.SPRECHER, orte.PROFILE)

    async def lesen(self) -> tuple[Profile, str | None]:
        """Profile und Stand (None, solange es die Datei nicht gibt)."""
        kw = zugang(self._kw)
        try:
            knoten = await kw.pfad(await self._pfad(kw))
        except NichtGefunden:
            return Profile(), None
        return Profile.model_validate_json(await kw.lesen_ganz(knoten.id)), knoten.etag

    async def aendern(self, aenderung: Callable[[Profile], T]) -> T:
        """`aenderung` ändert die Profile an Ort und Stelle und liefert ein Ergebnis; bei einem gleichzeitigen
        Schreiber wird sie mit dem neuen Stand wiederholt (darum ohne Nebenwirkungen außerhalb der Profile)."""
        kw = zugang(self._kw)
        pfad = await self._pfad(kw)
        for versuch in range(_VERSUCHE):
            profile, stand = await self.lesen()
            ergebnis = aenderung(profile)
            inhalt = profile.model_dump_json(indent=1).encode("utf-8")
            try:
                if stand is None:
                    await kw.ordner(pfad.rsplit("/", 1)[0])
                    await kw.schreiben(pfad, inhalt, nur_neu=True, inhaltstyp=orte.INHALTSTYP)
                else:
                    await kw.schreiben(pfad, inhalt, stand=stand, inhaltstyp=orte.INHALTSTYP)
                return ergebnis
            except StandVeraltet:
                if versuch == _VERSUCHE - 1:
                    raise
        raise AssertionError("unerreichbar")
