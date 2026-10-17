"""Hörabschnitte planen: die Dienste der Leitstelle bekommen nie eine ganze lange Aufnahme am Stück, und ein
abgebrochener Auftrag setzt beim nächsten Abschnitt wieder an. Ein Abschnitt endet in der Mitte einer Sprechpause,
möglichst nah an der Höchstlänge und lieber an einer längeren Pause; gibt es im Fenster keine Pause, wird hart bei der
Höchstlänge geschnitten. Messen, Wandeln und Ausschneiden kommen aus dem Appkern (`appkern.ton`).
"""

from __future__ import annotations

from dataclasses import dataclass

from appkern.ton import Pause


@dataclass(frozen=True)
class Abschnitt:
    nummer: int
    start: float
    ende: float


def abschnitte_planen(dauer: float, pausen: list[Pause], *, hoechstens_s: float = 600.0,
                      mindestens_s: float = 60.0) -> list[Abschnitt]:
    """Abschnitte von höchstens `hoechstens_s` Sekunden, geschnitten in Sprechpausen (siehe Modultext)."""
    if dauer <= 0:
        return []
    abschnitte: list[Abschnitt] = []
    start = 0.0
    while dauer - start > hoechstens_s:
        grenze = start + hoechstens_s
        im_fenster = [p for p in pausen if start + mindestens_s <= p.mitte <= grenze]
        spaet = [p for p in im_fenster if p.mitte >= start + hoechstens_s * 0.6]
        if spaet:
            schnitt = max(spaet, key=lambda p: (round(p.laenge, 1), p.mitte)).mitte
        elif im_fenster:
            schnitt = im_fenster[-1].mitte
        else:
            schnitt = grenze
        abschnitte.append(Abschnitt(len(abschnitte) + 1, round(start, 3), round(schnitt, 3)))
        start = schnitt
    abschnitte.append(Abschnitt(len(abschnitte) + 1, round(start, 3), round(dauer, 3)))
    return abschnitte
