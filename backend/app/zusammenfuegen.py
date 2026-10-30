"""Beiträge an Satzenden: der Hördienst schneidet an Sprechpausen, oft mitten im Satz ("um das" / "zum Laufen zu
bringen"). Hier wird ein Beitrag mit dem folgenden zusammengefügt, solange er nicht mit einem Satzzeichen endet, beide
zum selben Sprecher gehören, die Pause kurz ist und der Beitrag nicht zu lang wird. Wortzeiten bleiben, wie sie sind.
"""

from __future__ import annotations

from .modell.transkript import Segment

SATZENDE = (".", "?", "!", "…", ":")
PAUSE_HOECHSTENS_S = 2.0       # längere Pause: neuer Beitrag, auch mitten im Satz
BEITRAG_HOECHSTENS_S = 40.0    # ohne Satzzeichen (etwa Kleinschrift) würde sonst alles ein Beitrag


def endet_mit_satz(text: str) -> bool:
    return text.rstrip().rstrip("\"'»«)").endswith(SATZENDE)


def an_satzenden(segmente: list[Segment], pause_s: float = PAUSE_HOECHSTENS_S,
                 hoechstens_s: float = BEITRAG_HOECHSTENS_S) -> list[Segment]:
    aus: list[Segment] = []
    for s in segmente:
        vorne = aus[-1] if aus else None
        if (vorne is not None and not endet_mit_satz(vorne.text) and vorne.sprecher == s.sprecher
                and s.start - vorne.ende <= pause_s and s.ende - vorne.start <= hoechstens_s):
            aus[-1] = vorne.model_copy(update={"ende": max(vorne.ende, s.ende), "text": f"{vorne.text.rstrip()} {s.text.lstrip()}",
                                               "woerter": [*vorne.woerter, *s.woerter]})
        else:
            aus.append(s)
    return aus
