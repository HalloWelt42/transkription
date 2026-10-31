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
class Wechsel:
    """Ein Abschnitt eines Sprechers aus der Sprechertrennung (Kennung des Dienstes, etwa SPEAKER_00)."""

    start: float
    ende: float
    sprecher: str


@dataclass(frozen=True)
class HoerErgebnis:
    segmente: list[Segment]
    sprache: str | None
    modell: str | None
    wechsel: list[Wechsel]       # Sprecher, die der Hördienst selbst nennt (etwa MOSS-Transcribe-Diarize), sonst leer


def _typ(datei: Path) -> str:
    return INHALTSTYPEN.get(datei.suffix.lower(), "application/octet-stream")


def wechsel_aus(roh: list[dict], versatz: float = 0.0, vorsilbe: str = "") -> list[Wechsel]:
    """Sprecher, die der Hördienst je Segment nennt (`speaker`), als Wechsel wie aus der Sprechertrennung; `vorsilbe` hält
    Kennungen verschiedener Aufrufe auseinander (jeder Aufruf zählt von S01). Ein Segment ohne Sprecher (etwa ein
    Formatfehler des Modells in einem kurzen Stück) ist eine Lücke wie bei der Trennung, kein Grund, alle zu verwerfen
    (HELF-90: ein Stück von 0,4 s ohne Marken kostete sonst die Sprecher der ganzen Aufnahme)."""
    return [Wechsel(round(float(s["start"]) + versatz, 3), round(float(s["end"]) + versatz, 3), f"{vorsilbe}{s['speaker']}")
            for s in roh if (s.get("text") or "").strip() and s.get("speaker")]


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
        """`namen` liefert die Kennungen von Hören, Sprechermerkmal und Sprechertrennung (aus den Einstellungen); den
        Hördienst kann ein Auftrag selbst wählen."""
        self._ls = leitstelle
        self._namen = namen

    def _leitstelle(self) -> Leitstelle:
        ls = self._ls()
        if ls is None:
            raise KeineLeitstelle("Keine Leitstelle eingerichtet")
        return ls

    async def hoeren(self, datei: Path, sprache: str, *, versatz: float = 0.0, titel: str = "", hinweis: str = "",
                     prioritaet=None, dienst: str | None = None, vorsilbe: str = "",
                     abschnitt_s: int | None = None) -> HoerErgebnis:
        """`hinweis`: Stilsatz und Fachwörter, die der Hördienst jedem Fenster mitgibt (siehe Klangwerk); `dienst`: der
        Hördienst dieses Auftrags (sonst der eingestellte); `vorsilbe` für die Sprecher, die der Hördienst nennt;
        `abschnitt_s`: Abschnittslänge, mit der der Hördienst am Stück hört (leer: seine Vorgabe)."""
        name = dienst or self._namen()[0]
        daten = {"language": sprache, "diarize": "false", **({"prompt": hinweis} if hinweis else {}),
                 **({"abschnitt_s": str(abschnitt_s)} if abschnitt_s else {})}
        with open(datei, "rb") as inhalt:          # gestreamt, nie am Stück im Speicher
            antwort = await self._leitstelle().dienst(name).json(
                "POST", "/stt", titel=titel, prioritaet=prioritaet, data=daten,
                files={"file": (datei.name, inhalt, _typ(datei))})
        roh = antwort.get("segments") or []
        return HoerErgebnis(segmente=segmente_aus(roh, versatz), sprache=antwort.get("language"), modell=antwort.get("model"),
                            wechsel=wechsel_aus(roh, versatz, vorsilbe))

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
                      prioritaet=None, dienst: str | None = None, sprache: str | None = None) -> list[Wechsel]:
        """Wer spricht wann (`POST /speaker/diarize`, gleiche Schnittstelle bei pyannote und MOSS); `dienst`: der Dienst
        der Sprechertrennung dieses Auftrags (sonst der eingestellte), `sprache` hilft einem Dienst, der dabei hört."""
        name = dienst or self._namen()[2]
        daten: dict[str, str] = {"hf_token": zugang} if zugang else {}
        if anzahl:
            daten["num_speakers"] = str(anzahl)
        if sprache:
            daten["language"] = sprache
        with open(datei, "rb") as inhalt:
            antwort = await self._leitstelle().dienst(name).json(
                "POST", "/speaker/diarize", titel=titel, prioritaet=prioritaet, data=daten,
                files={"file": (datei.name, inhalt, _typ(datei))})
        return [Wechsel(float(t["start"]), float(t["end"]), str(t["speaker"])) for t in antwort.get("turns") or []]
