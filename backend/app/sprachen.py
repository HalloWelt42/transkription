"""Sprachen der Transkription: welche es gibt, sagt allein der Hördienst. Er nennt sie in seinem Steckbrief bei der
Leitstelle (Selbstauskunft, ISO 639-1); die App führt keine eigene Liste. Dazu kommt "auto" (der Hördienst erkennt sie).

Die Namen kommen aus den Sprachdaten von Babel (deutsch, "ru" ist "Russisch"); was Babel nicht kennt, steht als Kürzel
da. Nennt der Hördienst keine Sprachen oder ist die Leitstelle nicht erreichbar, prüft die App nichts weiter als die
Form des Kürzels; ob der Dienst die Sprache kann, sagt er dann selbst.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated

from babel import Locale
from pydantic import BaseModel, StringConstraints

from appkern.einstellungen import Angebot, Option
from appkern.leitstelle import Leitstelle, LeitstellenFehler

AUTO = "auto"
#: ISO 639-1 (zwei Kleinbuchstaben) oder "auto"; ob der Hördienst sie kann, sagt sein Steckbrief
Sprache = Annotated[str, StringConstraints(pattern=r"^([a-z]{2}|auto)$")]
GUELTIG_S = 300                      # so lange gilt die gelesene Liste, dann fragt die App die Leitstelle neu
_NAMEN = Locale("de").languages


class UnbekannteSprache(ValueError):
    """Der Hördienst nennt diese Sprache nicht."""


class SpracheEintrag(BaseModel):
    code: str
    name: str


def name(code: str) -> str:
    return "Erkennen" if code == AUTO else _NAMEN.get(code) or code.upper()


class Sprachen:
    def __init__(self, leitstelle: Callable[[], Leitstelle | None], dienst: Callable[[], str],
                 vorgabe: Callable[[], str]) -> None:
        """`dienst`: Kennung des gewählten Hördienstes, `vorgabe`: die eingestellte Sprache (beide aus den Einstellungen)."""
        self._leitstelle = leitstelle
        self._dienst = dienst
        self._vorgabe = vorgabe
        self._merk: dict[str, tuple[float, list[str] | None]] = {}

    async def des_dienstes(self, dienst: str | None = None) -> list[str] | None:
        """Was der Hördienst (ohne Angabe der eingestellte) laut Steckbrief kann; None, wenn er nichts nennt oder die
        Leitstelle nicht antwortet."""
        dienst = dienst or self._dienst()
        if (merk := self._merk.get(dienst)) and time.monotonic() - merk[0] < GUELTIG_S:
            return merk[1]
        ls = self._leitstelle()
        if ls is None:
            return None
        try:
            modelle = await ls.steckbriefe(faehigkeit="hoeren")
        except LeitstellenFehler:
            return None
        brief = next((m.steckbrief for m in modelle if m.id == dienst), None)
        liste = list(brief.sprachen) if brief and brief.sprachen else None
        self._merk[dienst] = (time.monotonic(), liste)
        return liste

    async def liste(self, dienst: str | None = None) -> list[SpracheEintrag]:
        """Zur Wahl: Erkennen, dann die Sprachen des Hördienstes nach Namen; nennt er keine, die eingestellte."""
        bekannt = await self.des_dienstes(dienst)
        vorgabe = self._vorgabe()
        codes = sorted(bekannt if bekannt is not None else ([] if vorgabe == AUTO else [vorgabe]), key=lambda c: name(c).casefold())
        return [SpracheEintrag(code=c, name=name(c)) for c in [AUTO, *codes]]

    async def pruefen(self, code: str | None, dienst: str | None = None) -> None:
        """Lässt nur durch, was der Hördienst nennt (oder "auto", oder alles, wenn er nichts nennt)."""
        if not code or code == AUTO:
            return
        bekannt = await self.des_dienstes(dienst)
        if bekannt is not None and code not in bekannt:
            raise UnbekannteSprache(f"Der Hördienst {dienst or self._dienst()} kann die Sprache {name(code)} ({code}) nicht; "
                                    "Erkennen wählen oder eine Sprache aus seiner Liste")

    async def angebot(self) -> Angebot:
        """Für die Einstellung Sprache: dieselbe Liste wie in der Oberfläche."""
        eintraege = await self.liste()
        stand = "" if await self.des_dienstes() else "Der Hördienst nennt keine Sprachen (oder die Leitstelle antwortet nicht)"
        return Angebot(optionen=[Option(wert=e.code, titel=e.name) for e in eintraege], stand=stand)
