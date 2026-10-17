"""Sprecherprofile (`Sprecher/profile.json` in der Kellerwolke): Name und gemittelter Stimmabdruck.

Ein Profil entsteht, wenn der Nutzer einem erkannten Sprecher einen Namen gibt; jede bestätigte Zuordnung mischt den
Abdruck dieses Sprechers in den Mittelwert (gewichtet mit der Zahl der Proben) und schärft so das Profil. Verglichen
wird mit der Kosinus-Ähnlichkeit.
"""

from __future__ import annotations

import math
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .transkript import jetzt

FORMAT = "sprecherprofile/1"


class Probe(BaseModel):
    """Woher ein Abdruck stammt (zum Anhören in der Oberfläche)."""

    model_config = ConfigDict(extra="allow")
    transkript_id: UUID
    start: float
    ende: float
    text: str = ""


class Profil(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    abdruck: list[float] = Field(default_factory=list, description="gemittelter Stimmabdruck")
    proben: int = Field(0, ge=0, description="Zahl der Abdrücke im Mittel")
    beispiele: list[Probe] = Field(default_factory=list, description="einige Stellen zum Anhören, neueste zuerst")
    erstellt_am: datetime = Field(default_factory=jetzt)
    geaendert_am: datetime = Field(default_factory=jetzt)

    def einmischen(self, abdruck: list[float], beispiel: Probe | None = None, *, beispiele_hoechstens: int = 5) -> None:
        if not abdruck:
            return
        if self.abdruck and len(self.abdruck) != len(abdruck):
            raise ValueError("Abdruck hat eine andere Länge als das Profil")
        if not self.abdruck:
            self.abdruck = list(abdruck)
        else:
            n = self.proben
            self.abdruck = [(a * n + b) / (n + 1) for a, b in zip(self.abdruck, abdruck, strict=True)]
        self.proben += 1
        if beispiel is not None:
            self.beispiele = [beispiel, *self.beispiele][:beispiele_hoechstens]
        self.geaendert_am = jetzt()


class Profile(BaseModel):
    model_config = ConfigDict(extra="allow")
    format: str = FORMAT
    profile: list[Profil] = Field(default_factory=list)

    def holen(self, profil_id: UUID) -> Profil | None:
        return next((p for p in self.profile if p.id == profil_id), None)

    def aehnlichstes(self, abdruck: list[float]) -> tuple[Profil, float] | None:
        """Das Profil mit der höchsten Ähnlichkeit (ohne Schwelle) oder None, wenn es keins gibt."""
        bestes: tuple[Profil, float] | None = None
        for p in self.profile:
            if not p.abdruck or len(p.abdruck) != len(abdruck):
                continue
            wert = kosinus(p.abdruck, abdruck)
            if bestes is None or wert > bestes[1]:
                bestes = (p, wert)
        return bestes

    def zusammenfuehren(self, ziel_id: UUID, quelle_id: UUID) -> Profil:
        """`quelle` geht in `ziel` auf (Abdrücke gewichtet gemittelt, Beispiele vereint); `quelle` verschwindet."""
        ziel, quelle = self.holen(ziel_id), self.holen(quelle_id)
        if ziel is None or quelle is None or ziel is quelle:
            raise ValueError("Zusammenführen braucht zwei verschiedene vorhandene Profile")
        if quelle.abdruck:
            if not ziel.abdruck:
                ziel.abdruck, ziel.proben = list(quelle.abdruck), quelle.proben
            else:
                n, m = ziel.proben, quelle.proben
                ziel.abdruck = [(a * n + b * m) / max(n + m, 1) for a, b in zip(ziel.abdruck, quelle.abdruck, strict=True)]
                ziel.proben = n + m
        ziel.beispiele = (ziel.beispiele + quelle.beispiele)[:5]
        ziel.geaendert_am = jetzt()
        self.profile = [p for p in self.profile if p.id != quelle_id]
        return ziel


def kosinus(a: list[float], b: list[float]) -> float:
    zaehler = sum(x * y for x, y in zip(a, b, strict=True))
    nenner = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return zaehler / nenner if nenner else 0.0
