"""Ein Gespräch in Teilen (HELF-154): geht ein Gespräch weiter, wird die neue Aufnahme Teil 2, 3 ... derselben
Aufnahme (Begleiter mit der Rolle `teil-<n>`, siehe ablage/orte.py). Nur der neue Teil wird gehört; hier kommt sein
Ergebnis unten an das bestehende Transkript: Zeiten laufen weiter (Versatz = bisherige Dauer), Sprecher des Teils
werden den bisherigen zugeordnet (gleiches Profil oder ähnlicher Stimmabdruck), sonst kommen sie neu dazu.
Korrekturen am bisherigen Text bleiben, weil nur angehängt wird.

Abspielen: Die Abspielfassungen haben alle dasselbe Format (PCM, eine Spur), darum werden sie für das Gespräch einfach
aneinandergehängt; die Zeit im Spieler ist die Zeit im Transkript."""

from __future__ import annotations

import hashlib
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from .modell.transkript import Marker, Segment, Sprecher, TeilAufnahme, Transkript, Wort
from .sprechererkennung import Schwellen, _normiert


def _verschoben(s: Segment, versatz: float, kennung: str | None) -> Segment:
    return s.model_copy(update={
        "start": round(s.start + versatz, 3), "ende": round(s.ende + versatz, 3), "sprecher": kennung,
        "woerter": [Wort(wort=w.wort, start=round(w.start + versatz, 3), ende=round(w.ende + versatz, 3), sicherheit=w.sicherheit)
                    for w in s.woerter]})


def sprecher_zuordnen(bisher: list[Sprecher], neu: list[Sprecher], schwellen: Schwellen) -> tuple[dict[str, str], list[Sprecher]]:
    """Kennungen des Teils auf die des Gesprächs: gleiches bestätigtes Profil, sonst der ähnlichste Stimmabdruck ab der
    Schwelle zum Zusammenlegen (jeder bisherige höchstens einmal); übrige bekommen die nächste freie Kennung. Liefert die
    Abbildung und die Sprecher des ganzen Gesprächs."""
    abbildung: dict[str, str] = {}
    vergeben: set[str] = set()
    for n in neu:
        gleich = next((b for b in bisher if n.profil_id and b.profil_id == n.profil_id and b.kennung not in vergeben), None)
        if gleich is not None:
            abbildung[n.kennung] = gleich.kennung
            vergeben.add(gleich.kennung)
    paare = sorted(((float(_normiert(np.array(n.abdruck)) @ _normiert(np.array(b.abdruck))), n.kennung, b.kennung)
                    for n in neu if n.kennung not in abbildung and n.abdruck
                    for b in bisher if b.kennung not in vergeben and b.abdruck and len(b.abdruck) == len(n.abdruck)),
                   key=lambda t: -t[0])
    for wert, nk, bk in paare:
        if wert < schwellen.zusammenlegen or nk in abbildung or bk in vergeben:
            continue
        abbildung[nk] = bk
        vergeben.add(bk)
    alle = list(bisher)
    naechste = max((int(s.kennung[1:]) for s in bisher), default=0)
    for n in neu:
        if n.kennung in abbildung:
            continue
        naechste += 1
        kennung = f"s{naechste}"
        abbildung[n.kennung] = kennung
        name = n.name if n.profil_id else f"Sprecher {naechste}"
        alle.append(n.model_copy(update={"kennung": kennung, "name": name}))
    return abbildung, alle


def wellenform_anhaengen(bisher: list[int] | None, bisher_s: float, teil: list[int] | None, teil_s: float) -> list[int] | None:
    """Beide Wellenformen nach ihrer Dauer auf so viele Punkte wie bisher (sonst wie der Teil) verteilt."""
    if not bisher and not teil:
        return None
    punkte = len(bisher or teil or [])
    gesamt = bisher_s + teil_s
    if gesamt <= 0:
        return list(bisher or teil or [])
    aus = []
    for i in range(punkte):
        t = (i + 0.5) / punkte * gesamt
        quelle, dauer, versatz = (bisher, bisher_s, 0.0) if t < bisher_s else (teil, teil_s, bisher_s)
        if not quelle or dauer <= 0:
            aus.append(0)
            continue
        aus.append(int(quelle[min(len(quelle) - 1, int((t - versatz) / dauer * len(quelle)))]))
    return aus


def anhaengen(bisher: Transkript, teil: TeilAufnahme, segmente: list[Segment], sprecher: list[Sprecher],
              marker: list[Marker], wellenform: list[int] | None, schwellen: Schwellen) -> Transkript:
    """Das Ergebnis eines Teils unten an das Transkript; `teil.beginn_s` ist der Versatz in der durchgehenden Zeit,
    die Zeiten in `segmente` und `marker` zählen ab dem Beginn des Teils."""
    abbildung, alle = sprecher_zuordnen(bisher.sprecher, sprecher, schwellen)
    versatz = teil.beginn_s
    neu = [_verschoben(s, versatz, abbildung.get(s.sprecher) if s.sprecher else None) for s in segmente]
    verschoben = [m.model_copy(update={"zeit": round(m.zeit + versatz, 3)}) for m in marker]
    return bisher.model_copy(update={
        "segmente": [*bisher.segmente, *neu],
        "sprecher": alle,
        "marker": [*bisher.marker, *verschoben],
        "dauer_s": round(versatz + teil.dauer_s, 3),
        "teile": [*bisher.teile, teil],
        "wellenform": wellenform_anhaengen(bisher.wellenform, versatz, wellenform, teil.dauer_s),
    })


def naechster_teil(t: Transkript) -> int:
    """Nummer des nächsten Teils: die Aufnahme ist Teil 1."""
    return len(t.teile) + 2


def teil_eintrag(knoten_id, dauer_s: float, t: Transkript, aufgenommen_am: datetime | None) -> TeilAufnahme:
    return TeilAufnahme(knoten_id=knoten_id, nummer=naechster_teil(t), beginn_s=round(t.dauer_s, 3),
                        dauer_s=round(dauer_s, 3), aufgenommen_am=aufgenommen_am)


# --- Abspielen ------------------------------------------------------------------------------------------------------

def fassung_name(transkript_id, schluessel: list[str]) -> str:
    """Name der zusammengehängten Abspielfassung; ändert sich mit jedem Teil und jeder neuen Fassung eines Teils."""
    return f"gespraech-{transkript_id}-{hashlib.sha1('|'.join(schluessel).encode()).hexdigest()[:16]}.wav"


def aneinanderhaengen(teile: list[Path], ziel: Path) -> Path:
    """WAV-Dateien gleichen Formats (Abspielfassungen) hintereinander in eine; erst fertig, dann an ihren Platz."""
    zwischen = ziel.with_suffix(".teil.wav")
    with wave.open(str(zwischen), "wb") as aus:
        for n, p in enumerate(teile):
            with wave.open(str(p), "rb") as ein:
                if n == 0:
                    aus.setparams(ein.getparams())
                while daten := ein.readframes(1 << 16):
                    aus.writeframes(daten)
    zwischen.replace(ziel)
    return ziel


def sprecher_wie_bisher(t: Transkript) -> tuple[str, str | None]:
    """Sprecherweg und Trenndienst für einen weiteren Teil, so wie das Gespräch entstand."""
    e = t.erzeugt_mit
    aus = e.sprecher_aus if e else None
    if aus in (None, "unbekannt"):
        return ("stimmen" if t.sprecher else "ohne"), None
    if aus in ("ohne", "stimmen"):
        return aus, None
    return "trennung", (None if e and aus == e.dienst else aus)
