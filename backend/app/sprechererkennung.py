"""Sprechererkennung aus Stimmabdrücken (je Segment einer) und, wenn verfügbar, der Sprechertrennung.

1. Mit Trennung: jedes Segment bekommt den Sprecher mit der größten Überlappung. Ohne Trennung (Dienst fehlt oder
   scheitert): Gruppieren der Abdrücke (agglomerativ, mittlere Kosinus-Ähnlichkeit), kleine Gruppen (unter 3 Segmenten
   und unter 8 s) gehen in die ähnlichste große. Ist die Zahl der Sprecher bekannt, wird genau auf sie gruppiert.
2. Gruppen mit sehr ähnlichem Mittel werden zusammengelegt (die Trennung teilt manche Stimme zu fein).
3. Segmente ohne Abdruck oder Überlappung erben den Sprecher des Vorgängers (am Anfang den des Nachfolgers).
4. Abgleich mit den Profilen: gierig nach höchster Ähnlichkeit, jedes Profil höchstens einmal je Aufnahme. Ab der
   Schwelle "sicher" trägt der Sprecher Namen und Profil, ab "Vorschlag" nur einen Vorschlag zum Bestätigen. Profile
   ändern sich hier nie, erst wenn der Nutzer eine Zuordnung bestätigt.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dienste import Wechsel
from .modell.sprecherprofil import Profile
from .modell.transkript import Segment, Sprecher

KLEIN_SEGMENTE = 3
KLEIN_SEKUNDEN = 8.0


@dataclass(frozen=True)
class Schwellen:
    gruppieren: float = 0.60     # mittlere Ähnlichkeit, ab der Gruppen ohne Trennung verschmelzen
    zusammenlegen: float = 0.60  # Ähnlichkeit der Mittel, ab der zwei Sprecher einer sind
    sicher: float = 0.70         # Profil wird zugeordnet
    vorschlag: float = 0.50      # Profil wird vorgeschlagen


def _normiert(v: np.ndarray) -> np.ndarray:
    laenge = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(laenge == 0, 1, laenge)


def nach_trennung(segmente: list[Segment], wechsel: list[Wechsel]) -> list[str | None]:
    """Je Segment der Sprecher der Trennung mit der größten Überlappung (oder None)."""
    aus: list[str | None] = []
    for seg in segmente:
        summe: dict[str, float] = {}
        for w in wechsel:
            ueber = min(seg.ende, w.ende) - max(seg.start, w.start)
            if ueber > 0:
                summe[w.sprecher] = summe.get(w.sprecher, 0.0) + ueber
        aus.append(max(summe, key=summe.get) if summe else None)
    return aus


def gruppieren(abdruecke: list[list[float] | None], segmente: list[Segment], schwelle: float,
               anzahl: int | None = None) -> list[str | None]:
    """Agglomerativ mit mittlerer Verknüpfung über die Kosinus-Ähnlichkeit (siehe Modultext)."""
    da = [i for i, a in enumerate(abdruecke) if a]
    labels: list[str | None] = [None] * len(abdruecke)
    if not da:
        return labels
    x = _normiert(np.array([abdruecke[i] for i in da], dtype=np.float64))
    gruppen: list[list[int]] = [[i] for i in range(len(da))]
    aehnlich = x @ x.T
    summe = aehnlich.copy()                    # Summe der Ähnlichkeiten zwischen Gruppen
    np.fill_diagonal(summe, -np.inf)
    groesse = np.ones(len(da))
    aktiv = np.ones(len(da), dtype=bool)
    ziel = max(1, anzahl) if anzahl else None
    while aktiv.sum() > 1:
        mittel = summe / np.outer(groesse, groesse)
        mittel[~aktiv, :] = -np.inf
        mittel[:, ~aktiv] = -np.inf
        a, b = np.unravel_index(np.argmax(mittel), mittel.shape)
        if ziel is None and mittel[a, b] < schwelle:
            break
        if ziel is not None and aktiv.sum() <= ziel:
            break
        summe[a, :] += summe[b, :]
        summe[:, a] += summe[:, b]
        summe[a, a] = -np.inf
        groesse[a] += groesse[b]
        aktiv[b] = False
        gruppen[a].extend(gruppen[b])
        gruppen[b] = []
    gruppen = [g for g in gruppen if g]
    if ziel is None and len(gruppen) > 1:
        gruppen = _kleine_einfuegen(gruppen, x, [segmente[i] for i in da])
    for n, g in enumerate(sorted(gruppen, key=min)):
        for i in g:
            labels[da[i]] = f"G{n}"
    return labels


def _kleine_einfuegen(gruppen: list[list[int]], x: np.ndarray, segmente: list[Segment]) -> list[list[int]]:
    def klein(g: list[int]) -> bool:
        return len(g) < KLEIN_SEGMENTE and sum(segmente[i].ende - segmente[i].start for i in g) < KLEIN_SEKUNDEN

    grosse = [g for g in gruppen if not klein(g)]
    if not grosse:
        return gruppen
    mittel = _normiert(np.array([x[g].mean(axis=0) for g in grosse]))
    for g in gruppen:
        if klein(g):
            ziel = int(np.argmax(mittel @ _normiert(x[g].mean(axis=0))))
            grosse[ziel] = grosse[ziel] + g
    return grosse


def zentroide(labels: list[str | None], abdruecke: list[list[float] | None]) -> dict[str, np.ndarray]:
    sammel: dict[str, list[list[float]]] = {}
    for label, a in zip(labels, abdruecke, strict=True):
        if label is not None and a:
            sammel.setdefault(label, []).append(a)
    return {k: _normiert(np.mean(np.array(v, dtype=np.float64), axis=0)) for k, v in sammel.items()}


def zusammenlegen(labels: list[str | None], abdruecke: list[list[float] | None], schwelle: float) -> list[str | None]:
    """Sprecher mit sehr ähnlichem Mittel werden einer (der mit mehr Segmenten bleibt)."""
    labels = list(labels)
    while True:
        z = zentroide(labels, abdruecke)
        namen = sorted(z, key=lambda k: -labels.count(k))
        paar = max(((a, b, float(z[a] @ z[b])) for i, a in enumerate(namen) for b in namen[i + 1:]),
                   key=lambda t: t[2], default=None)
        if paar is None or paar[2] < schwelle:
            return labels
        labels = [paar[0] if lab == paar[1] else lab for lab in labels]


def erben(labels: list[str | None]) -> list[str | None]:
    aus = list(labels)
    for i in range(1, len(aus)):
        if aus[i] is None:
            aus[i] = aus[i - 1]
    erstes = next((lab for lab in aus if lab is not None), None)
    return [erstes if lab is None else lab for lab in aus]


def sprecher_bilden(segmente: list[Segment], labels: list[str | None], abdruecke: list[list[float] | None],
                    profile: Profile, schwellen: Schwellen) -> tuple[list[Segment], list[Sprecher]]:
    """Kennungen s1, s2 ... in der Reihenfolge des ersten Auftretens, Namen und Vorschläge aus den Profilen."""
    reihenfolge = list(dict.fromkeys(lab for lab in labels if lab is not None))
    kennung = {lab: f"s{n + 1}" for n, lab in enumerate(reihenfolge)}
    z = zentroide(labels, abdruecke)
    paare = sorted(((float(z[lab] @ _normiert(np.array(p.abdruck))), lab, p) for lab in reihenfolge if lab in z
                    for p in profile.profile if p.abdruck and len(p.abdruck) == len(z[lab])),
                   key=lambda t: -t[0])
    vergeben_lab: set[str] = set()
    vergeben_profil: set = set()
    treffer: dict[str, tuple[float, object]] = {}
    for wert, lab, p in paare:
        if lab in vergeben_lab or p.id in vergeben_profil or wert < schwellen.vorschlag:
            continue
        vergeben_lab.add(lab)
        vergeben_profil.add(p.id)
        treffer[lab] = (wert, p)
    sprecher = []
    for n, lab in enumerate(reihenfolge):
        wert, p = treffer.get(lab, (None, None))
        sicher = wert is not None and wert >= schwellen.sicher
        sprecher.append(Sprecher(
            kennung=kennung[lab], name=p.name if sicher else f"Sprecher {n + 1}",
            profil_id=p.id if sicher else None, aehnlichkeit=round(wert, 3) if sicher else None,
            vorschlag_id=p.id if p is not None and not sicher else None,
            vorschlag_aehnlichkeit=round(wert, 3) if p is not None and not sicher else None,
            abdruck=[round(float(v), 5) for v in z[lab]] if lab in z else None))
    neu = [s.model_copy(update={"sprecher": kennung[lab] if lab is not None else None})
           for s, lab in zip(segmente, labels, strict=True)]
    return neu, sprecher


def erkennen(segmente: list[Segment], abdruecke: list[list[float] | None], wechsel: list[Wechsel] | None,
             profile: Profile, schwellen: Schwellen, anzahl: int | None = None) -> tuple[list[Segment], list[Sprecher]]:
    """Alles zusammen (siehe Modultext); `wechsel` None heißt: ohne Sprechertrennung."""
    if wechsel:
        labels = nach_trennung(segmente, wechsel)
    else:
        labels = gruppieren(abdruecke, segmente, schwellen.gruppieren, anzahl)
    if not anzahl:
        labels = zusammenlegen(labels, abdruecke, schwellen.zusammenlegen)
    labels = erben(labels)
    return sprecher_bilden(segmente, labels, abdruecke, profile, schwellen)
