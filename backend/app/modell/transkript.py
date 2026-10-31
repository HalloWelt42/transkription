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
    abdruck: list[float] | None = Field(None, description="gemittelter Stimmabdruck dieses Sprechers in der Aufnahme")


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
    hoeren_s: float | None = Field(None, ge=0, description="Rechenzeit des Hördienstes für die ganze Aufnahme (Tempo)")
    bereich: tuple[float, float] | None = Field(None, description="nur dieser Ausschnitt der Aufnahme (Sekunden, in "
                                                "Sprechpausen); ohne: die ganze Aufnahme")
    abschnitt_s: float | None = Field(None, gt=0, description="gewünschte Abschnittslänge des Hördienstes; ohne: seine Vorgabe")

    def art(self) -> tuple[str, bool]:
        """Wofür eine Fassung steht: je Hördienst höchstens eine ganze und eine Ausschnitt-Fassung."""
        return self.dienst, self.bereich is not None


class Hoerfassung(_Teil):
    """Dieselbe Aufnahme von einem anderen Hördienst gehört, zum Vergleich neben der Hauptfassung (den Feldern des
    Transkripts selbst). Je Hördienst höchstens eine; Bearbeiten, Suche und Export gelten der Hauptfassung."""

    id: UUID = Field(default_factory=uuid4)
    erzeugt_mit: ErzeugtMit
    erstellt_am: datetime = Field(default_factory=jetzt)
    sprache: str = Field("de", max_length=12)
    sprecher: list[Sprecher] = Field(default_factory=list)
    segmente: list[Segment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _stimmig(self) -> Hoerfassung:
        _sprecher_pruefen(self.sprecher, self.segmente)
        self.segmente.sort(key=lambda s: (s.start, s.ende))
        return self


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
    wellenform: list[int] | None = Field(None, description="Lautstärke 0 bis 100 in gleichen Abschnitten (Spieler)")
    fassungen: list[Hoerfassung] = Field(default_factory=list, description="weitere Hördienste zum Vergleich, je einer")

    @model_validator(mode="after")
    def _stimmig(self) -> Transkript:
        _sprecher_pruefen(self.sprecher, self.segmente)
        arten = [f.erzeugt_mit.art() for f in self.fassungen]
        if len(set(arten)) != len(arten):
            raise ValueError("Je Hördienst höchstens eine ganze Fassung und ein Ausschnitt")
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


def _sprecher_pruefen(sprecher: list[Sprecher], segmente: list[Segment]) -> None:
    kennungen = [s.kennung for s in sprecher]
    if len(set(kennungen)) != len(kennungen):
        raise ValueError("Sprecherkennungen doppelt")
    bekannt = set(kennungen)
    for seg in segmente:
        if seg.sprecher is not None and seg.sprecher not in bekannt:
            raise ValueError(f"Segment bei {seg.start:.2f} s nennt unbekannten Sprecher {seg.sprecher}")


# --- Fassungen je Hördienst -------------------------------------------------------------------------------------
# Die Hauptfassung sind die Felder des Transkripts (so lesen es auch andere Apps); weitere Hördienste stehen unter
# `fassungen`. Neu gehört ersetzt nur, was vom selben Hördienst stammt; jeder frühere Stand bleibt als Version der
# Kellerwolke erhalten.

_HAUPT = ("erzeugt_mit", "sprache", "sprecher", "segmente")


def als_fassung(t: Transkript) -> Hoerfassung:
    """Die Hauptfassung als Fassung (ohne Hördienst gilt sie als unbekannter Herkunft)."""
    return Hoerfassung(erzeugt_mit=t.erzeugt_mit or ErzeugtMit(dienst="unbekannt", app="unbekannt"),
                       erstellt_am=t.geaendert_am, sprache=t.sprache, sprecher=t.sprecher, segmente=t.segmente)


def gehoert_einfuegen(bisher: Transkript, neu: Transkript, hauptfassung: bool = False) -> tuple[Transkript, bool]:
    """Ein frisch gehörtes Transkript in das bisherige derselben Aufnahme. Vom Hördienst der Hauptfassung oder mit
    `hauptfassung`: es wird die Hauptfassung; eine bisherige eines anderen Hördienstes rückt unter die Fassungen.
    Sonst wird es die Fassung seines Hördienstes (ersetzt eine frühere desselben Dienstes) und die Hauptfassung
    bleibt. Liefert das Ergebnis und ob es die Hauptfassung ist."""
    dienst = neu.erzeugt_mit.dienst if neu.erzeugt_mit else None
    haupt_dienst = bisher.erzeugt_mit.dienst if bisher.erzeugt_mit else None
    if neu.erzeugt_mit and neu.erzeugt_mit.bereich is not None:
        # Ein Ausschnitt (Messung, Vergleich einer Stelle) wird nie Hauptfassung; er ersetzt nur den vorigen Ausschnitt
        # desselben Hördienstes
        if hauptfassung:
            raise ValueError("Ein Ausschnitt wird nie Hauptfassung")
        andere = [f for f in bisher.fassungen if f.erzeugt_mit.art() != neu.erzeugt_mit.art()]
        return bisher.model_copy(update={"fassungen": [*andere, als_fassung(neu)]}), False
    # Marker gehören zur Aufnahme: die gesetzten bleiben, auch wenn neu Gehörtes die Hauptfassung wird
    marker = [*neu.marker, *(m for m in bisher.marker if (m.zeit, m.titel) not in {(n.zeit, n.titel) for n in neu.marker})]
    if dienst is None or dienst == haupt_dienst:
        return neu.model_copy(update={"fassungen": bisher.fassungen, "marker": sorted(marker, key=lambda m: m.zeit)}), True
    andere = [f for f in bisher.fassungen if f.erzeugt_mit.bereich is not None or f.erzeugt_mit.dienst not in (dienst, haupt_dienst)]
    if hauptfassung:
        return neu.model_copy(update={"fassungen": [*andere, als_fassung(bisher)],
                                      "marker": sorted(marker, key=lambda m: m.zeit)}), True
    return bisher.model_copy(update={"fassungen": [*andere, als_fassung(neu)]}), False


def zur_hauptfassung(t: Transkript, fassung_id: UUID) -> Transkript:
    """Eine Fassung wird Hauptfassung (Bearbeiten, Suche, Export), die bisherige rückt an ihre Stelle unter die
    Fassungen. Marker, Name und Wellenform gehören zur Aufnahme und bleiben."""
    gewaehlt = next((f for f in t.fassungen if f.id == fassung_id), None)
    if gewaehlt is None:
        raise KeyError(f"Keine Fassung {fassung_id}")
    if gewaehlt.erzeugt_mit.bereich is not None:
        raise ValueError("Ein Ausschnitt kann nicht Hauptfassung werden")
    bisherige = als_fassung(t)
    fassungen = [bisherige if f.id == fassung_id else f for f in t.fassungen]
    return Transkript.model_validate({**t.model_dump(), **{k: getattr(gewaehlt, k) for k in _HAUPT},
                                      "erzeugt_mit": gewaehlt.erzeugt_mit, "fassungen": fassungen})


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
