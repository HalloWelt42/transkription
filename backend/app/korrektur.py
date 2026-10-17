"""KI-Korrektur über die Leitstelle: Vorschläge je Segment, übernommen wird nur, was der Nutzer bestätigt.

Je Anfrage gehen drei Segmente mit, dazu je ein Segment davor und danach als Zusammenhang (nicht zu korrigieren). Die
Antwort hat eine nummerierte Zeile je Segment; fehlt eine Zeile oder weicht die Länge stark ab (unter der Hälfte oder
über das Doppelte), gibt es für dieses Segment keinen Vorschlag. Die Wortzeiten gleicht später `woerter_angleichen` an.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from appkern.leitstelle import Nachricht

from .modell.transkript import Segment

FENSTER = 3
_ZEILE = re.compile(r"^\s*\[(\d+)\]\s?(.*)$")

SYSTEM = (
    "Du korrigierst Abschriften gesprochener Sprache. Korrigiere nur Rechtschreibung, Zeichensetzung sowie Groß- und "
    "Kleinschreibung, schreibe getrennt erkannte zusammengesetzte Wörter zusammen und behebe Hörfehler nur, wenn der "
    "Zusammenhang eindeutig ist. Füllwörter am Satzanfang darfst du streichen, wenn sie nichts bedeuten. Ändere nichts "
    "am Inhalt, ergänze nichts, fasse nichts zusammen, übersetze nichts. Antworte nur mit den nummerierten Zeilen in der "
    "Form [n] Text, genau eine Zeile je Nummer, in derselben Reihenfolge, ohne weitere Worte."
)


class Vorschlag(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    start: float = Field(description="Beginn des Segments, auf das er sich bezieht")
    alt: str = Field(description="Text des Segments beim Vorschlagen (ändert er sich, gilt der Vorschlag nicht mehr)")
    neu: str


def fenster(anzahl: int, groesse: int = FENSTER) -> list[range]:
    return [range(i, min(i + groesse, anzahl)) for i in range(0, anzahl, groesse)]


def anfrage(segmente: list[Segment], bereich: range) -> list[Nachricht]:
    teile = []
    if bereich.start > 0:
        teile.append(f"Zusammenhang davor (nicht korrigieren): {segmente[bereich.start - 1].text}")
    teile.append("Zu korrigieren:\n" + "\n".join(f"[{n + 1}] {segmente[i].text}" for n, i in enumerate(bereich)))
    if bereich.stop < len(segmente):
        teile.append(f"Zusammenhang danach (nicht korrigieren): {segmente[bereich.stop].text}")
    return [Nachricht.system(SYSTEM), Nachricht.nutzer("\n\n".join(teile))]


def antwort_lesen(antwort: str, alte: list[str]) -> list[str | None]:
    """Je altem Text der neue (oder None: kein Vorschlag)."""
    gefunden: dict[int, str] = {}
    for zeile in antwort.splitlines():
        if (m := _ZEILE.match(zeile)) is not None:
            gefunden.setdefault(int(m.group(1)), m.group(2).strip())
    aus: list[str | None] = []
    for n, alt in enumerate(alte, start=1):
        neu = gefunden.get(n)
        if not neu or neu == alt.strip() or not 0.5 * len(alt) <= len(neu) <= 2 * len(alt) + 2:
            aus.append(None)
        else:
            aus.append(neu)
    return aus


def vorschlaege(segmente: list[Segment], bereich: range, antwort: str) -> list[Vorschlag]:
    alte = [segmente[i].text for i in bereich]
    return [Vorschlag(start=segmente[i].start, alt=alt, neu=neu)
            for i, alt, neu in zip(bereich, alte, antwort_lesen(antwort, alte), strict=True) if neu is not None]
