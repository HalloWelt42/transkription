"""Das Transkript als Datei (Format `transkript/1`): eine Datei je Aufnahme in der Kellerwolke, versioniert von ihr.

Die Datei ist die einzige Wahrheit; die Datenbank der App ist nur Verzeichnis und Suchindex. Unbekannte Felder bleiben
beim Lesen und Schreiben erhalten (eine neuere Fassung der App bricht ältere nicht und umgekehrt).

Zeiten sind Sekunden ab Beginn der Aufnahme. Ein Segment ist ein Beitrag eines Sprechers mit Text und Wortzeiten; die
Wortzeiten tragen das Mitlesen. Wird Text geändert, gleicht `woerter_angleichen` die Wörter an: Unverändertes behält
seine Zeit, Neues bekommt eine Zeit zwischen den Nachbarn.
"""

from __future__ import annotations

import difflib
import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMAT = "transkript/1"
MarkerFarbe = Literal["gelb", "rot", "gruen", "blau", "lila"]


def jetzt() -> datetime:
    return datetime.now(UTC)


class _Teil(BaseModel):
    model_config = ConfigDict(extra="allow")


class Wort(_Teil):
    wort: str
    start: float = Field(ge=0)
    ende: float = Field(ge=0)
    sicherheit: float | None = Field(None, ge=0, le=1, description="wie sicher das Hörmodell war (falls bekannt)")


class Segment(_Teil):
    start: float = Field(ge=0)
    ende: float = Field(ge=0)
    sprecher: str | None = Field(None, description="Kennung aus `sprecher`, etwa s1")
    text: str
    woerter: list[Wort] = Field(default_factory=list)

    @model_validator(mode="after")
    def _zeiten(self) -> Segment:
        if self.ende < self.start:
            raise ValueError(f"Segment endet ({self.ende}) vor seinem Beginn ({self.start})")
        return self


class Sprecher(_Teil):
    kennung: str = Field(pattern=r"^s[0-9]{1,3}$")
    name: str = Field(min_length=1, max_length=120)
    profil_id: UUID | None = Field(None, description="bestätigtes Sprecherprofil")
    aehnlichkeit: float | None = Field(None, description="Ähnlichkeit zum bestätigten Profil")
    vorschlag_id: UUID | None = Field(None, description="Profil, das ähnlich klingt, aber noch nicht bestätigt ist")
    vorschlag_aehnlichkeit: float | None = None


class Marker(_Teil):
    id: UUID = Field(default_factory=uuid4)
    zeit: float = Field(ge=0)
    titel: str = Field(min_length=1, max_length=200)
    farbe: MarkerFarbe = "gelb"


class Quelle(_Teil):
    knoten_id: UUID
    pfad: str
    etag: str | None = None


class ErzeugtMit(_Teil):
    dienst: str
    modell: str | None = None
    app: str


class Aenderung(_Teil):
    """Wie die vorliegende Fassung entstand (je Version eine; die Kellerwolke hält die früheren)."""

    was: str = Field(max_length=300)
    wer: str | None = None
    app: str | None = Field(None, description="andere App, die geändert hat")
    zeit: datetime = Field(default_factory=jetzt)


class Transkript(_Teil):
    format: Literal["transkript/1"] = FORMAT
    name: str = Field(min_length=1, max_length=200)
    quelle: Quelle | None = None
    sprache: str = Field("de", max_length=12)
    dauer_s: float = Field(0.0, ge=0)
    erstellt_am: datetime = Field(default_factory=jetzt)
    geaendert_am: datetime = Field(default_factory=jetzt)
    sprecher: list[Sprecher] = Field(default_factory=list)
    segmente: list[Segment] = Field(default_factory=list)
    marker: list[Marker] = Field(default_factory=list)
    erzeugt_mit: ErzeugtMit | None = None
    aenderung: Aenderung | None = None

    @model_validator(mode="after")
    def _stimmig(self) -> Transkript:
        kennungen = [s.kennung for s in self.sprecher]
        if len(set(kennungen)) != len(kennungen):
            raise ValueError("Sprecherkennungen doppelt")
        bekannt = set(kennungen)
        for seg in self.segmente:
            if seg.sprecher is not None and seg.sprecher not in bekannt:
                raise ValueError(f"Segment bei {seg.start:.2f} s nennt unbekannten Sprecher {seg.sprecher}")
        self.segmente.sort(key=lambda s: (s.start, s.ende))
        self.marker.sort(key=lambda m: m.zeit)
        return self

    # --- Ableitungen ------------------------------------------------------------------------------------------

    def sprecher_name(self, kennung: str | None) -> str | None:
        return next((s.name for s in self.sprecher if s.kennung == kennung), None)

    def anteile(self) -> dict[str, float]:
        """Sprechzeit je Sprecher als Anteil (0 bis 1) der Zeit mit Sprecher."""
        summe: dict[str, float] = {}
        for seg in self.segmente:
            if seg.sprecher:
                summe[seg.sprecher] = summe.get(seg.sprecher, 0.0) + (seg.ende - seg.start)
        gesamt = sum(summe.values())
        return {k: (v / gesamt if gesamt else 0.0) for k, v in summe.items()}

    def text(self) -> str:
        return "\n".join(s.text for s in self.segmente)

    def neue_sprecherkennung(self) -> str:
        belegt = {s.kennung for s in self.sprecher}
        n = 1
        while f"s{n}" in belegt:
            n += 1
        return f"s{n}"


# --- Wortangleichung -------------------------------------------------------------------------------------------

_TOKEN = re.compile(r"\S+")


def _schluessel(wort: str) -> str:
    """Vergleichsform eines Worts: ohne Satzzeichen am Rand, klein."""
    return wort.strip(".,;:!?\"'()[]{}-").lower()


def woerter_angleichen(segment: Segment) -> Segment:
    """Wörter passend zum (geänderten) Text. Gleiche Wörter behalten ihre Zeit (auch mit anderem Satzzeichen), neue
    bekommen gleichmäßig verteilte Zeiten zwischen den Nachbarn; ohne Anker wird die Segmentzeit verteilt."""
    tokens = _TOKEN.findall(segment.text)
    alt = segment.woerter
    if [w.wort for w in alt] == tokens:
        return segment
    neu: list[Wort | None] = [None] * len(tokens)
    passer = difflib.SequenceMatcher(a=[_schluessel(w.wort) for w in alt], b=[_schluessel(t) for t in tokens],
                                     autojunk=False)
    for block in passer.get_matching_blocks():
        for i in range(block.size):
            w = alt[block.a + i]
            neu[block.b + i] = Wort(wort=tokens[block.b + i], start=w.start, ende=w.ende, sicherheit=w.sicherheit)
    # Lücken zwischen Ankern füllen
    i = 0
    while i < len(neu):
        if neu[i] is not None:
            i += 1
            continue
        j = i
        while j < len(neu) and neu[j] is None:
            j += 1
        von = neu[i - 1].ende if i > 0 else segment.start
        bis = neu[j].start if j < len(neu) else segment.ende
        bis = max(bis, von)
        schritt = (bis - von) / (j - i)
        for k in range(i, j):
            a = von + (k - i) * schritt
            neu[k] = Wort(wort=tokens[k], start=round(a, 3), ende=round(a + schritt, 3))
        i = j
    return segment.model_copy(update={"woerter": [w for w in neu if w is not None]})
