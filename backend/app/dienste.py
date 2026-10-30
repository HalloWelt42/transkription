"""Die Sprachdienste des Klangwerks, erreicht über die Leitstelle (`/v1/dienste/<name>/...`): Hören (Ton zu Text mit
Wortzeiten), Sprechermerkmal (Stimmabdruck je Stelle) und Sprechertrennung (wer spricht wann). Hier wird nur
übersetzt: Felder der Dienste in das Modell der App, Zeiten eines Abschnitts in Zeiten der ganzen Aufnahme.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from appkern.leitstelle import Leitstelle

from .modell.transkript import Segment, Wort

INHALTSTYPEN = {".wav": "audio/wav", ".flac": "audio/flac"}


class KeineLeitstelle(Exception):
    """Die App ist noch nicht mit einer Leitstelle verbunden."""


class KeinSprachmodell(Exception):
    """Für Korrektur und Auswertung ist kein Sprachmodell gewählt (die App wählt es, nie die Leitstelle)."""

    def __init__(self) -> None:
        super().__init__("Kein Sprachmodell gewählt: unter Einstellungen, KI, Sprachmodell eines wählen")


@dataclass(frozen=True)
class HoerErgebnis:
    segmente: list[Segment]
    sprache: str | None
    modell: str | None


@dataclass(frozen=True)
class Wechsel:
    """Ein Abschnitt eines Sprechers aus der Sprechertrennung (Kennung des Dienstes, etwa SPEAKER_00)."""

    start: float
    ende: float
    sprecher: str


def _typ(datei: Path) -> str:
    return INHALTSTYPEN.get(datei.suffix.lower(), "application/octet-stream")


def segmente_aus(roh: list[dict], versatz: float = 0.0) -> list[Segment]:
    """Segmente des Hördienstes (start, end, text, words mit word, start, end), verschoben um `versatz`."""
    aus = []
    for s in roh:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        woerter = [Wort(wort=w["word"].strip(), start=round(float(w["start"]) + versatz, 3),
                        ende=round(float(w["end"]) + versatz, 3))
                   for w in s.get("words") or [] if (w.get("word") or "").strip()]
        start, ende = round(float(s["start"]) + versatz, 3), round(float(s["end"]) + versatz, 3)
        aus.append(Segment(start=start, ende=max(ende, start), text=text, woerter=woerter))
    return aus


class Klangwerk:
    def __init__(self, leitstelle: Callable[[], Leitstelle | None], namen: Callable[[], tuple[str, str, str]]) -> None:
        """`namen` liefert die Kennungen von Hören, Sprechermerkmal und Sprechertrennung (aus den Einstellungen)."""
        self._ls = leitstelle
        self._namen = namen

    def _leitstelle(self) -> Leitstelle:
        ls = self._ls()
        if ls is None:
            raise KeineLeitstelle("Keine Leitstelle eingerichtet")
        return ls

    async def hoeren(self, datei: Path, sprache: str, *, versatz: float = 0.0, titel: str = "",
                     prioritaet=None) -> HoerErgebnis:
        name = self._namen()[0]
        with open(datei, "rb") as inhalt:          # gestreamt, nie am Stück im Speicher
            antwort = await self._leitstelle().dienst(name).json(
                "POST", "/stt", titel=titel, prioritaet=prioritaet, data={"language": sprache, "diarize": "false"},
                files={"file": (datei.name, inhalt, _typ(datei))})
        return HoerErgebnis(segmente=segmente_aus(antwort.get("segments") or [], versatz),
                            sprache=antwort.get("language"), modell=antwort.get("model"))

    async def abdruecke(self, datei: Path, zeiten: list[tuple[float, float]], *, titel: str = "",
                        prioritaet=None) -> list[list[float] | None]:
        """Ein Stimmabdruck je Stelle (Zeiten relativ zur Datei); unter einer Sekunde None."""
        if not zeiten:
            return []
        name = self._namen()[1]
        with open(datei, "rb") as inhalt:
            antwort = await self._leitstelle().dienst(name).json(
                "POST", "/speaker/embed", titel=titel, prioritaet=prioritaet,
                data={"segments": json.dumps([{"start": a, "end": b} for a, b in zeiten])},
                files={"file": (datei.name, inhalt, _typ(datei))})
        abdruecke = antwort.get("embeddings") or []
        if len(abdruecke) != len(zeiten):
            raise ValueError(f"Sprechermerkmal lieferte {len(abdruecke)} statt {len(zeiten)} Abdrücke")
        return abdruecke

    async def trennen(self, datei: Path, *, anzahl: int | None = None, zugang: str = "", titel: str = "",
                      prioritaet=None) -> list[Wechsel]:
        name = self._namen()[2]
        daten: dict[str, str] = {"hf_token": zugang} if zugang else {}
        if anzahl:
            daten["num_speakers"] = str(anzahl)
        with open(datei, "rb") as inhalt:
            antwort = await self._leitstelle().dienst(name).json(
                "POST", "/speaker/diarize", titel=titel, prioritaet=prioritaet, data=daten,
                files={"file": (datei.name, inhalt, _typ(datei))})
        return [Wechsel(float(t["start"]), float(t["end"]), str(t["speaker"])) for t in antwort.get("turns") or []]
