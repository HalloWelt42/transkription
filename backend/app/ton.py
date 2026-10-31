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
                      mindestens_s: float = 60.0, von: float = 0.0, bis: float | None = None) -> list[Abschnitt]:
    """Abschnitte von höchstens `hoechstens_s` Sekunden, geschnitten in Sprechpausen (siehe Modultext); mit `von` und
    `bis` nur über diesen Ausschnitt."""
    ende = dauer if bis is None else min(bis, dauer)
    if ende <= von:
        return []
    abschnitte: list[Abschnitt] = []
    start = von
    while ende - start > hoechstens_s:
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
    abschnitte.append(Abschnitt(len(abschnitte) + 1, round(start, 3), round(ende, 3)))
    return abschnitte


BEREICH_SPIELRAUM_S = 3.0


def bereich_einpassen(von: float, bis: float, pausen: list[Pause], dauer: float,
                      spielraum_s: float = BEREICH_SPIELRAUM_S) -> tuple[float, float]:
    """Ein gewünschter Ausschnitt mit beiden Grenzen in der Mitte der nächsten Sprechpause (höchstens `spielraum_s`
    entfernt, sonst bleibt die Grenze), damit kein Satz zerhackt wird; Anfang und Ende der Aufnahme gelten als Pause."""
    def einpassen(t: float) -> float:
        if t <= 0 or t >= dauer:
            return min(max(t, 0.0), dauer)
        nah = min(pausen, key=lambda p: abs(p.mitte - t), default=None)
        return round(nah.mitte, 3) if nah is not None and abs(nah.mitte - t) <= spielraum_s else t
    a, b = einpassen(von), einpassen(bis)
    if b - a < 1.0:
        raise ValueError(f"Ausschnitt zu kurz ({von:g} bis {bis:g} s)")
    return a, b
