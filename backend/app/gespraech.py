"""Ein Gespräch fortsetzen (HELF-154): Wer weiterspricht, nimmt an dieselbe Aufnahme an. Der neue Ton wird an die
Tondatei angehängt (auf dem Tondienst zusammengefügt, im Format der Aufnahme) und als neue Fassung desselben Knotens
gespeichert; die alte Fassung bleibt in der Kellerwolke zurückholbar. Gibt es ein Transkript, wird danach nur der neue
Bereich gehört (ab der alten Dauer) und sein Text unten angehängt: Zeiten laufen weiter, Sprecher werden den bisherigen
zugeordnet (gleiches Profil oder ähnlicher Stimmabdruck), Korrekturen am bisherigen Text bleiben. Eine Marke zeigt,
wo weiter aufgenommen wurde."""

from __future__ import annotations

from datetime import datetime

import numpy as np

from .modell.transkript import Marker, Quelle, Segment, Sprecher, Transkript
from .sprechererkennung import Schwellen, _normiert

# Kodierung, wie ffprobe sie nennt, und der Kodierer von ffmpeg, der sie wieder schreibt
KODIERER = {"opus": "libopus", "vorbis": "libvorbis", "mp3": "libmp3lame", "aac": "aac", "flac": "flac",
            "alac": "alac", "pcm_s16le": "pcm_s16le", "pcm_s24le": "pcm_s24le", "pcm_f32le": "pcm_f32le"}
# ohne Angabe der Aufnahme: was zur Endung passt (der Behälter folgt aus ihr)
NACH_ENDUNG = {".webm": "libopus", ".ogg": "libopus", ".oga": "libopus", ".opus": "libopus", ".mp3": "libmp3lame",
               ".m4a": "aac", ".aac": "aac", ".flac": "flac", ".wav": "pcm_s16le"}


def kodierer(kodierung: str | None, endung: str) -> str:
    """Der Kodierer für die zusammengefügte Datei: wie die Aufnahme, sonst passend zur Endung."""
    if kodierung and kodierung in KODIERER:
        return KODIERER[kodierung]
    if endung.lower() in NACH_ENDUNG:
        return NACH_ENDUNG[endung.lower()]
    raise ValueError(f"Diese Tonart ({kodierung or endung}) lässt sich nicht verlängern")


def marke(wann: datetime) -> str:
    return f"Weiter aufgenommen am {wann.astimezone():%d.%m.%Y, %H:%M}"


def sprecher_zuordnen(bisher: list[Sprecher], neu: list[Sprecher], schwellen: Schwellen) -> tuple[dict[str, str], list[Sprecher]]:
    """Kennungen des neuen Bereichs auf die des Gesprächs: gleiches bestätigtes Profil, sonst der ähnlichste Stimmabdruck
    ab der Schwelle zum Zusammenlegen (jeder bisherige höchstens einmal); übrige bekommen die nächste freie Kennung.
    Liefert die Abbildung und die Sprecher des ganzen Gesprächs."""
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
        abbildung[n.kennung] = f"s{naechste}"
        alle.append(n.model_copy(update={"kennung": f"s{naechste}", "name": n.name if n.profil_id else f"Sprecher {naechste}"}))
    return abbildung, alle


def anhaengen(bisher: Transkript, ab_s: float, segmente: list[Segment], sprecher: list[Sprecher], marker: list[Marker],
              dauer_s: float, wellenform: list[int] | None, quelle: Quelle, wann: datetime, schwellen: Schwellen) -> Transkript:
    """Der Text des neuen Bereichs (Zeiten schon in der Zeit der ganzen Aufnahme, ab `ab_s`) unten an das Transkript;
    `marker` sind die Marker der Aufnahme, davon kommen die im neuen Bereich dazu, dazu die Marke der Fortsetzung."""
    abbildung, alle = sprecher_zuordnen(bisher.sprecher, sprecher, schwellen)
    neu = [s.model_copy(update={"sprecher": abbildung.get(s.sprecher) if s.sprecher else None}) for s in segmente if s.start >= ab_s - 0.05]
    dazu = [m for m in marker if m.zeit >= ab_s and not any(abs(b.zeit - m.zeit) < 0.05 and b.titel == m.titel for b in bisher.marker)]
    return bisher.model_copy(update={
        "segmente": [*bisher.segmente, *neu],
        "sprecher": alle,
        "marker": [*bisher.marker, Marker(zeit=round(ab_s, 3), titel=marke(wann), farbe="blau"), *dazu],
        "dauer_s": round(dauer_s, 3),
        "wellenform": wellenform or bisher.wellenform,
        "quelle": quelle,
    })


def sprecher_wie_bisher(t: Transkript) -> tuple[str, str | None]:
    """Sprecherweg und Trenndienst für den neuen Bereich, so wie das Gespräch entstand."""
    e = t.erzeugt_mit
    aus = e.sprecher_aus if e else None
    if aus in (None, "unbekannt"):
        return ("stimmen" if t.sprecher else "ohne"), None
    if aus in ("ohne", "stimmen"):
        return aus, None
    return "trennung", (None if e and aus == e.dienst else aus)
