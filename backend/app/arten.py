"""Arten von Aufträgen der Transkription.

transkribieren      Vorbereiten (Ton holen, wandeln, Abschnitte an Sprechpausen planen), Hören (je Abschnitt Text mit
                    Wortzeiten und Stimmabdrücke; nach Abbruch oder Neustart geht es beim nächsten Abschnitt weiter),
                    Sprecher (Trennung oder Gruppieren, Abgleich mit den Profilen), Speichern (Begleiter der Aufnahme,
                    neu oder als neue Version; Index).
aus_anfrage         Transkribieren auf Anfrage aus der Kellerwolke (Dateimenü): die Aufnahme liegt außerhalb der App,
                    gelesen und geschrieben wird nur mit dem Recht der Anfrage.
sprecher_erkennen   für ein vorhandenes Transkript neu, auf Wunsch mit bekannter Sprecherzahl.
korrigieren         KI-Korrektur in Fenstern von drei Segmenten; Ergebnis sind Vorschläge, nichts wird überschrieben.
auswerten           KI-Auswertung nach Vorlage als Markdown-Datei neben dem Transkript.

Wartet die Leitstelle (Halt, Modell lädt, Speicher knapp), steht das als Schritt im Auftrag und es wird nach der
genannten Zeit erneut versucht, so lange, wie die Einstellung "Geduld bei Ausfall" sagt; schläft der Mac, ohne Grenze,
bis er wach ist. Gesperrte oder abgelehnte Aufträge gehen ohne Wiederholung an den Menschen.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, model_validator

from appkern.anfragen import AnfrageEingabe, Angebot
from appkern.auftraege import Art, AuftragAbgebrochen, Kontext, Phase
from appkern.kellerwolke import Aktion, Kellerwolke, KellerwolkeFehler, StandVeraltet
from appkern.leitstelle import WARTEN_BEI, DienstFehler, DienstWeg, Halt, NichtErreichbar, NichtGefunden
from appkern.leitstelle import geduldig as leitstelle_geduldig

from . import altbestand, auswertung, export, korrektur, umzug
from .ablage import orte
from .ablage.transkripte import aufnahme_id, begleiter_ablegen
from .dienste import KeineLeitstelle, Wechsel
from .einstellungen import SprecherWeg
from .sprachen import Sprache
from .zusammenfuegen import an_satzenden
from .mitlesen import takt as mitlesen_takt
from .fassung import FASSUNG
from .modell.transkript import Aenderung, ErzeugtMit, Marker, Quelle, Segment, Transkript
from .sprechererkennung import an_wechseln_teilen, erkennen
from .teile import Teile
from appkern.ton import ABSPIELEN, HOEREN, Aufbereiten, Ausgabe, Messen, Pause, PausenWahl
from appkern.ton.wav import ausschnitt, dauer as wav_dauer

from .ton import Abschnitt, abschnitte_planen, bereich_einpassen

T = TypeVar("T")
TAKT_S = 5                       # so oft meldet ein Abschnitt beim Hören seinen geschätzten Fortschritt


def ungefaehr(sekunden: float) -> str:
    return "unter 1 min" if sekunden < 60 else f"{round(sekunden / 60)} min"


async def mit_schaetzung(k: Kontext, a: Abschnitt, plan: list[Abschnitt], fertig: dict, sekunde_je_ton: float | None,
                         aufruf: Callable[[], Awaitable[T]]) -> T:
    """Während ein Abschnitt gehört wird, meldet der Auftrag alle `TAKT_S` Sekunden einen geschätzten Fortschritt und die
    Restzeit, aus der Länge des Tons und dem gemessenen Tempo des Hördienstes (Rechenzeit je Sekunde Ton). Der Hördienst
    selbst meldet nichts zwischendurch; ohne Tempo bleibt es bei "Abschnitt n von m". Höchstens 95 Prozent je Abschnitt,
    bis er wirklich fertig ist."""
    if not sekunde_je_ton:
        return await aufruf()
    beginn = time.monotonic()
    erwartet = (a.ende - a.start) * sekunde_je_ton
    spaeter = sum(x.ende - x.start for x in plan if str(x.nummer) not in fertig and x.nummer != a.nummer) * sekunde_je_ton

    async def ticken() -> None:
        while True:
            await asyncio.sleep(TAKT_S)
            vergangen = time.monotonic() - beginn
            anteil = min(0.95, vergangen / erwartet) if erwartet > 0 else 0.95
            rest = max(erwartet - vergangen, erwartet * 0.05) + spaeter
            try:
                await k.fortschritt((len(fertig) + anteil) / len(plan),
                                    f"Abschnitt {a.nummer} von {len(plan)}, noch etwa {ungefaehr(rest)}")
            except Exception:  # noqa: BLE001 - die Schätzung darf das Hören nie stören
                return

    aufgabe = asyncio.create_task(ticken())
    try:
        return await aufruf()
    finally:
        aufgabe.cancel()


class TranskribierenAnfrage(BaseModel):
    quelle_id: UUID = Field(description="Knoten der Aufnahme in der Kellerwolke")
    name: str | None = Field(None, max_length=200, description="Name des Transkripts; leer: Name der Aufnahme")
    sprache: Sprache | None = Field(None, description="leer: Vorgabe aus den Einstellungen")
    sprecher: SprecherWeg | None = Field(None, description="ohne, Stimmen gruppieren oder mit Sprechertrennung; leer: Vorgabe "
                                                            "aus den Einstellungen (ab Werk ohne)")
    anzahl: int | None = Field(None, ge=1, le=20, description="bekannte Zahl der Sprecher")
    hoerdienst: str | None = Field(None, max_length=120, description="Hördienst der Leitstelle für diesen Auftrag (GET "
                                   "/hoerdienste); leer: der eingestellte. Gibt es schon ein Transkript, wird es die "
                                   "Fassung dieses Hördienstes daneben (vom Hördienst der Hauptfassung: neue Hauptfassung)")
    hauptfassung: bool = Field(False, description="das Ergebnis wird Hauptfassung, auch von einem anderen Hördienst; die "
                                                  "bisherige rückt dann unter die Fassungen")
    reihe: list[str] = Field(default_factory=list, max_length=20,
                             description="mehrere Hördienste nacheinander, je einer ein Auftrag desselben Stapels: dieser hört "
                                         "mit dem ersten, nach seinem Ende kommt der nächste dran (auch wenn einer scheitert, "
                                         "nicht nach Abbruch)")
    anfrage_id: UUID | None = Field(None, description="Anfrage der Kellerwolke: die Aufnahme liegt außerhalb der App, die "
                                                      "App darf sie nur für diesen Auftrag lesen")
    abschnitt_s: int | None = Field(None, ge=5, le=600, description="Abschnittslänge höchstens, mit der der Hördienst am "
                                    "Stück hört (er schneidet in Sprechpausen); leer: seine Vorgabe. Für Messungen und "
                                    "Vergleiche")
    bereich: tuple[float, float] | None = Field(None, description="nur dieser Ausschnitt der Aufnahme (von, bis in "
                                                "Sekunden; die Grenzen rücken in die nächste Sprechpause). Das Ergebnis "
                                                "kommt als Ausschnitt-Fassung neben ein vorhandenes Transkript, nie als "
                                                "Hauptfassung")

    @model_validator(mode="after")
    def _bereich_pruefen(self):
        if self.bereich is not None:
            von, bis = self.bereich
            if von < 0 or bis - von < 1:
                raise ValueError("bereich: von ab 0, bis mindestens 1 s danach")
            if self.hauptfassung:
                raise ValueError("Ein Ausschnitt wird nie Hauptfassung")
        return self


class TranskribierenEingabe(TranskribierenAnfrage):
    von: str | None = Field(None, description="wer den Auftrag gab (Konto, bei anderen Apps auch die App)")
    reihe_kennung: str | None = Field(None, description="Stapel der Aufträge einer Reihe (vergibt die App)")

    def stelle(self) -> int | None:
        """Platz dieses Auftrags in seiner Reihe (ab 1), ohne Reihe None."""
        return self.reihe.index(self.hoerdienst) + 1 if self.reihe and self.hoerdienst in self.reihe else None


class AnfrageOptionen(BaseModel):
    """Was eine andere App beim Weitergeben einer Anfrage mitgeben darf (etwa die Vertonung die Sprache des Tons).
    Andere Namen gelten nicht; ein ungültiger Wert lässt den Auftrag mit klarer Meldung scheitern."""

    sprache: Sprache | None = None
    sprecher: SprecherWeg | None = None
    anzahl: int | None = Field(None, ge=1, le=20)
    hoerdienst: str | None = Field(None, max_length=120)


def eingabe_aus_anfrage(e: AnfrageEingabe) -> TranskribierenEingabe:
    optionen = AnfrageOptionen.model_validate(e.optionen).model_dump(exclude_none=True)
    return TranskribierenEingabe(quelle_id=e.knoten_id, anfrage_id=e.anfrage_id, von="Kellerwolke", **optionen)


class UebernehmenAnfrage(BaseModel):
    schluessel: str = Field(min_length=8, max_length=64, description="Eintrag des Altbestands (aus GET /altbestand)")
    zielordner: str = Field("", max_length=300, description="Unterordner von Aufnahmen, entsteht bei Bedarf; leer: direkt dort")
    name: str = Field(min_length=1, max_length=200, description="Name der Aufnahme ohne Endung (und ihres Transkripts)")
    neu_transkribieren: bool = Field(False, description="danach neu transkribieren; das wird die jüngste Version")
    sprache: Sprache | None = None
    sprecher: SprecherWeg | None = None
    anzahl: int | None = Field(None, ge=1, le=20)


class UebernehmenEingabe(UebernehmenAnfrage):
    von: str | None = None


class ProfileUebernehmenEingabe(BaseModel):
    profile: list[altbestand.AltesProfil] = Field(min_length=1, max_length=200)
    von: str | None = None


class SprecherEingabe(BaseModel):
    transkript_id: UUID
    anfrage_id: UUID | None = Field(None, description="Anfrage der Kellerwolke, wenn das Transkript außerhalb der App liegt")
    weg: Literal["stimmen", "trennung"] = Field("stimmen", description="Stimmen gruppieren oder erst die Sprechertrennung fragen")
    anzahl: int | None = Field(None, ge=1, le=20)
    von: str | None = None


class KorrigierenEingabe(BaseModel):
    transkript_id: UUID
    anfrage_id: UUID | None = Field(None, description="Anfrage der Kellerwolke, wenn das Transkript außerhalb der App liegt")
    von: str | None = None


class AuswertenEingabe(BaseModel):
    transkript_id: UUID
    anfrage_id: UUID | None = Field(None, description="Anfrage der Kellerwolke, wenn das Transkript außerhalb der App liegt")
    vorlage: auswertung.Vorlage = "protokoll"
    von: str | None = None


async def geduldig(k: Kontext, aufruf: Callable[[], Awaitable[T]], was: str,
                   warten_bei: tuple[type[Exception], ...] = WARTEN_BEI) -> T:
    """Ruft die Leitstelle geduldig (`appkern.leitstelle.geduldig`): wartet sie (Halt, Dienst lädt oder ist noch nicht
    gemeldet, nicht erreichbar, der Mac schläft), steht das als Schritt im Auftrag und es wird nach ihrer Angabe erneut
    versucht, so lange, wie die Einstellung "Geduld bei Ausfall" sagt (den Schlaf ohne Grenze); abbrechen geht auch
    während des Wartens. Wo es einen Ausweg gibt (die Sprechertrennung), wird nur bei Halt und Schlaf gewartet."""
    async def melden(text: str) -> None:
        await k.fortschritt(None, text)
    return await leitstelle_geduldig(aufruf, was=was, warten_bei=warten_bei, melden=melden, pruefen=k.pruefen)


@dataclass(frozen=True)
class Vorbereitet:
    """Was der Tondienst aus einer Aufnahme macht: der Ton für Hören, Trennung und Abschnitte (16 kHz mono PCM, auf dem
    Pi nur noch byteweise geschnitten), seine Dauer, die Sprechpausen und die Wellenform."""

    wav: Path
    dauer: float
    pausen: list[Pause]
    wellenform: list[int]


async def ausschneiden(wav: Path, beginn: float, ende: float, ziel: Path) -> Path:
    """Ein Abschnitt als Bytekopie (Datenarbeit, kein Rechnen)."""
    return await asyncio.to_thread(ausschnitt, wav, beginn, ende, ziel)


def _segmente(roh: list[dict]) -> list[Segment]:
    return [Segment.model_validate(s) for s in roh]


def arten(teile: Teile) -> list[Art]:
    g = teile.geruest

    async def ton_holen(k: Kontext, quelle_id: UUID | str, ordner: Path, kw: Kellerwolke) -> Vorbereitet:
        """Original holen und vom Tondienst in einem Aufruf aufbereiten lassen: Ton für den Hördienst (16 kHz mono),
        die Abspielfassung (fehlt sie noch), Sprechpausen und Wellenform. Beides aus derselben Quelle mit demselben
        Dekoder, damit Wortzeiten und Wiedergabe gleich laufen."""
        quelle = await kw.knoten(quelle_id)
        roh = ordner / f"quelle{PurePosixPath(quelle.name).suffix.lower() or '.bin'}"
        await k.fortschritt(None, f"Ton holen ({quelle.name})")
        await kw.herunterladen(quelle.id, roh)
        await k.fortschritt(None, "Ton wandeln (Tondienst)")
        wav, fassung = ordner / "ton.wav", ordner / "abspielen.wav"
        mit_fassung = teile.abspielen.vorhanden(quelle) is None
        auftrag = Aufbereiten(ausgaben=[Ausgabe(format=HOEREN), *([Ausgabe(format=ABSPIELEN)] if mit_fassung else [])],
                              messen=Messen(pausen=PausenWahl(), wellenform=800))
        erg = await geduldig(k, lambda: teile.ton.aufbereiten(roh, auftrag, [wav, fassung][:len(auftrag.ausgaben)],
                                                              titel=f"{quelle.name}, wandeln", prioritaet="hintergrund"),
                             "Ton wandeln")
        if mit_fassung:
            await teile.abspielen.uebernehmen(quelle, fassung, erg.messwerte.wellenform)
        roh.unlink(missing_ok=True)
        return Vorbereitet(wav=wav, dauer=wav_dauer(wav), pausen=erg.messwerte.pausen or [],
                           wellenform=erg.messwerte.wellenform or [])

    async def abschnitte(k: Kontext, v: Vorbereitet) -> list[Abschnitt]:
        """Plan aus dem Zwischenstand (beim Fortsetzen derselbe), sonst neu an den Sprechpausen."""
        if "abschnitte" in k.zwischenstand:
            return [Abschnitt(*a) for a in k.zwischenstand["abschnitte"]]
        e: TranskribierenEingabe = k.eingabe
        von, bis = (bereich_einpassen(*e.bereich, v.pausen, v.dauer) if getattr(e, "bereich", None) else (0.0, None))
        plan = abschnitte_planen(v.dauer, v.pausen, hoechstens_s=teile.einstellungen.abschnitt_min * 60, von=von, bis=bis)
        await k.merken(abschnitte=[[a.nummer, a.start, a.ende] for a in plan], dauer=v.dauer)
        return plan

    async def abdruecke_fuer(k: Kontext, wav: Path, ordner: Path, segmente: list[Segment], plan: list[Abschnitt],
                             titel: str) -> list[list[float] | None]:
        """Stimmabdrücke für (geteilte) Segmente, je Abschnitt der Aufnahme ein Aufruf; Reihenfolge wie `segmente`."""
        aus: list[list[float] | None] = []
        for a in plan:
            darin = [s for s in segmente if a.start <= s.start < a.ende]
            if not darin:
                continue
            stueck = await ausschneiden(wav, a.start, a.ende, ordner / f"abdruck-{a.nummer}.wav")
            zeiten = [(round(s.start - a.start, 3), round(s.ende - a.start, 3)) for s in darin]
            aus += await geduldig(k, lambda: teile.klangwerk.abdruecke(stueck, zeiten, titel=titel, prioritaet="hintergrund"),
                                  "Stimmabdrücke")
            stueck.unlink(missing_ok=True)
        return aus

    async def sprecher_bestimmen(k: Kontext, wav: Path, ordner: Path, segmente: list[Segment],
                                 abdruecke: list[list[float] | None], anzahl: int | None, titel: str, trennung: bool,
                                 plan: list[Abschnitt], vom_hoerdienst: list[Wechsel] | None = None):
        """Nur auf ausdrücklichen Wunsch: mit `trennung` fragt sie erst die Sprechertrennung (scheitert die, wird
        gruppiert), sonst gruppiert sie die Stimmabdrücke. Mit Trennung werden die Segmente an den Sprecherwechseln
        geteilt und ihre Abdrücke neu bestimmt (sonst mischen lange Segmente zwei Stimmen). Nennt der Hördienst die
        Sprecher selbst (`vom_hoerdienst`), gelten sie als Trennung; gleiche Stimmen über Abschnitte hinweg legen die
        Abdrücke zusammen."""
        e = teile.einstellungen
        wechsel: list[Wechsel] | None = vom_hoerdienst or None
        if wechsel:
            await k.fortschritt(None, "Sprecher aus dem Hördienst", phase="sprecher")
        elif trennung:
            await k.fortschritt(None, "Sprechertrennung", phase="sprecher")
            try:
                wechsel = await geduldig(k, lambda: teile.klangwerk.trennen(
                    wav, anzahl=anzahl, zugang=e.trennen_zugang.get_secret_value(), titel=titel,
                    prioritaet="hintergrund"), "Sprechertrennung", warten_bei=(Halt,))
            except (DienstWeg, DienstFehler, NichtGefunden, NichtErreichbar) as f:
                await g.protokoll.eintragen("sprecher.ohne_trennung", f"{titel}: {f.meldung}", stufe="warnung",
                                            bezug_art="auftrag", bezug_name=titel)
                await k.fortschritt(None, "Sprechertrennung nicht verfügbar; gruppiere nach Stimmen")
        if wechsel:
            geteilt = an_wechseln_teilen(segmente, wechsel)
            if len(geteilt) != len(segmente):
                await k.fortschritt(None, f"An Sprecherwechseln geteilt: {len(segmente)} zu {len(geteilt)} Segmenten",
                                    phase="sprecher")
                segmente, abdruecke = geteilt, await abdruecke_fuer(k, wav, ordner, geteilt, plan, titel)
        await k.fortschritt(None, "Sprecher zuordnen", phase="sprecher")
        profile, _ = await teile.profile.lesen()
        return erkennen(segmente, abdruecke, wechsel, profile, teile.schwellen, anzahl)

    # --- transkribieren -------------------------------------------------------------------------------------------

    async def transkribieren(k: Kontext) -> dict:
        e: TranskribierenEingabe = k.eingabe
        einst = teile.einstellungen
        sprache = e.sprache or einst.sprache
        hoerdienst = e.hoerdienst or einst.dienst_hoeren
        await teile.sprachen.pruefen(sprache, hoerdienst)          # vor aller Arbeit: kann der Hördienst sie?
        weg = e.sprecher or einst.sprecher_weg
        mit_sprechern = weg != "ohne"
        if "transkript_id" in k.zwischenstand:          # schon gespeichert, nur der Abschluss fehlte
            return {"transkript_id": k.zwischenstand["transkript_id"], "ergebnis_id": k.zwischenstand["transkript_id"]}
        kw = teile.zugang(e.anfrage_id)
        transkripte = teile.transkripte_fuer(e.anfrage_id)
        quelle = await kw.knoten(e.quelle_id)
        if e.bereich and await transkripte.zur_quelle(quelle.id) is None:
            raise ValueError("Ein Ausschnitt kommt nur neben ein vorhandenes Transkript der Aufnahme")
        name = e.name or orte.anzeigename(quelle.name)
        ordner = teile.arbeit / k.auftrag_id
        ordner.mkdir(parents=True, exist_ok=True)
        try:
            await k.fortschritt(0.0, "Vorbereiten", phase="vorbereiten")
            v = await ton_holen(k, quelle.id, ordner, kw)
            wav, dauer, wellenform = v.wav, v.dauer, v.wellenform
            plan = await abschnitte(k, v)
            if quelle.felder.get(orte.FELD_DAUER) is None:
                try:          # für die Liste der Aufnahmen; in nur lesbaren Ordnern geht es nicht, das ist kein Fehler
                    await kw.felder_setzen(quelle.id, {orte.FELD_DAUER: round(dauer, 1)})
                except KellerwolkeFehler:
                    pass

            hinweis = await teile.hoer_hinweis()
            fertig: dict[str, dict] = dict(k.zwischenstand.get("hoeren", {}))

            async def tempo() -> float | None:
                """Rechenzeit je Sekunde Ton: aus den fertigen Abschnitten, vorher aus früheren Aufträgen des Hördienstes."""
                rechnen, ton = mitlesen_takt({"abschnitte": [[x.nummer, x.start, x.ende] for x in plan], "hoeren": fertig})
                if not ton:
                    rechnen, ton = await teile.mitlesen.frueher(hoerdienst)
                return rechnen / ton if ton else None

            await k.fortschritt(len(fertig) / max(len(plan), 1), "Hören", phase="hoeren")
            for a in plan:
                if str(a.nummer) in fertig:
                    continue
                await k.pruefen()
                await k.fortschritt(len(fertig) / len(plan), f"Abschnitt {a.nummer} von {len(plan)}")
                # Beginn und Rechenzeit je Abschnitt: daraus schätzt das Mitlesen, wie lange es noch dauert
                await k.merken(abschnitt_beginn=datetime.now(UTC).isoformat())
                beginn = time.monotonic()
                stueck = await ausschneiden(wav, a.start, a.ende, ordner / f"abschnitt-{a.nummer}.wav")
                titel = f"{name}, Abschnitt {a.nummer} von {len(plan)}"
                hoer_beginn = time.monotonic()
                erg = await mit_schaetzung(k, a, plan, fertig, await tempo(), lambda: geduldig(
                    k, lambda: teile.klangwerk.hoeren(stueck, sprache, versatz=a.start, titel=titel, hinweis=hinweis,
                                                      prioritaet="hintergrund", dienst=hoerdienst, vorsilbe=f"A{a.nummer}:",
                                                      abschnitt_s=e.abschnitt_s),
                    "Hören"))
                hoeren_s = round(time.monotonic() - hoer_beginn, 1)
                abdruecke: list = []
                if mit_sprechern and erg.segmente:
                    zeiten = [(round(s.start - a.start, 3), round(s.ende - a.start, 3)) for s in erg.segmente]
                    abdruecke = await geduldig(k, lambda: teile.klangwerk.abdruecke(stueck, zeiten, titel=titel,
                                                                                     prioritaet="hintergrund"),
                                               "Stimmabdrücke")
                stueck.unlink(missing_ok=True)
                fertig[str(a.nummer)] = {"segmente": [s.model_dump(mode="json") for s in erg.segmente],
                                         "abdruecke": abdruecke, "sprache": erg.sprache, "modell": erg.modell,
                                         "wechsel": [[w.start, w.ende, w.sprecher] for w in erg.wechsel],
                                         "hoeren_s": hoeren_s, "gerechnet_s": round(time.monotonic() - beginn, 1)}
                await k.merken(hoeren=fertig)
                await k.fortschritt(len(fertig) / len(plan), f"Abschnitt {a.nummer} von {len(plan)} fertig")

            segmente: list[Segment] = []
            abdruecke_alle: list[list[float] | None] = []
            for a in plan:
                teil = fertig[str(a.nummer)]
                segs = _segmente(teil["segmente"])
                segmente += segs
                abdruecke_alle += teil["abdruecke"] or [None] * len(segs)
            erkannt = next((t["sprache"] for t in fertig.values() if t.get("sprache")), None)
            modell = next((t["modell"] for t in fertig.values() if t.get("modell")), None)
            hoeren_s = round(sum(t.get("hoeren_s") or 0.0 for t in fertig.values()), 1)
            # Sprecher des Hördienstes zählen nur, wenn er sie in jedem Abschnitt mit Text nennt
            mit_text = [t for t in fertig.values() if t["segmente"]]
            vom_hoerdienst = ([Wechsel(*w) for t in mit_text for w in t.get("wechsel") or []]
                              if mit_text and all(t.get("wechsel") for t in mit_text) else None)

            sprecher = []
            if mit_sprechern and segmente:
                segmente, sprecher = await sprecher_bestimmen(k, wav, ordner, segmente, abdruecke_alle, e.anzahl, name,
                                                              trennung=weg == "trennung", plan=plan,
                                                              vom_hoerdienst=vom_hoerdienst)

            segmente = an_satzenden(segmente)       # Beiträge enden an Satzenden, nicht an jeder Sprechpause
            await k.pruefen()
            await k.fortschritt(None, "Speichern", phase="speichern")
            marker = [Marker(zeit=m["zeit"], titel=m["titel"]) for m in quelle.felder.get(orte.FELD_MARKER) or []
                      if isinstance(m, dict) and "zeit" in m and m.get("titel")]
            t = Transkript(name=name, quelle=Quelle(knoten_id=quelle.id, pfad=quelle.pfad, etag=quelle.etag), marker=marker,
                           sprache=(erkannt if sprache == "auto" and erkannt else sprache), dauer_s=round(dauer, 3),
                           sprecher=sprecher, segmente=segmente, wellenform=wellenform,
                           erzeugt_mit=ErzeugtMit(dienst=hoerdienst, modell=modell, app=FASSUNG, hoeren_s=hoeren_s,
                                                  bereich=(plan[0].start, plan[-1].ende) if e.bereich and plan else None,
                                                  abschnitt_s=e.abschnitt_s),
                           aenderung=Aenderung(was="erzeugt", wer=e.von))
            t, knoten = await transkripte.speichern(t, quelle, Aenderung(was="erzeugt", wer=e.von),
                                                    erneut=Aenderung(was="neu transkribiert", wer=e.von),
                                                    hauptfassung=e.hauptfassung)
            await k.merken(transkript_id=str(knoten.id))
            await teile.geschrieben(t, knoten, e.anfrage_id)
            return {"transkript_id": str(knoten.id), "ergebnis_id": str(knoten.id), "name": t.name, "pfad": knoten.pfad,
                    "segmente": len(segmente), "sprecher": len(sprecher), "dauer_s": t.dauer_s}
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    async def naechster_in_reihe(k: Kontext) -> None:
        """Nach dem Ende eines Auftrags einer Reihe: den nächsten Hördienst einreihen, genau einmal (auch bei Wiederholung
        oder Fortsetzen nicht doppelt)."""
        e: TranskribierenEingabe = k.eingabe
        stelle = e.stelle()
        if stelle is None or stelle >= len(e.reihe) or k.zwischenstand.get("naechster"):
            return
        await k.merken(naechster=True)
        weiter = e.model_copy(update={"hoerdienst": e.reihe[stelle]})
        titel = f"{e.name or 'Neu hören'}: {stelle + 1} von {len(e.reihe)} Hördiensten"
        await g.auftraege.einreihen("transkribieren", weiter, titel=titel, stapel=e.reihe_kennung, von=e.von or "")

    async def transkribieren_in_reihe(k: Kontext) -> dict:
        """Transkribieren; gehört der Auftrag zu einer Reihe, kommt danach der nächste Hördienst dran, auch wenn dieser
        scheitert (ein Modell soll die übrigen nicht aufhalten), aber nicht nach einem Abbruch."""
        try:
            ergebnis = await transkribieren(k)
        except AuftragAbgebrochen:
            raise
        except Exception:
            await naechster_in_reihe(k)
            raise
        await naechster_in_reihe(k)
        return ergebnis

    async def aus_anfrage(k: Kontext) -> dict:
        """Transkribieren auf Anfrage aus dem Dateimenü der Kellerwolke oder einer anderen App; was die Anfrage nicht
        mitgibt, kommt aus den Einstellungen."""
        k.eingabe = eingabe_aus_anfrage(k.eingabe)
        return await transkribieren(k)

    # --- uebernehmen (Altbestand der alten App) -------------------------------------------------------------------

    async def uebernehmen(k: Kontext) -> dict:
        """Original mit Prüfsumme holen, in Aufnahmen (Unterordner) ablegen, die alten Stände als Versionen eines
        Transkripts im selben Unterordner, auf Wunsch neu transkribieren (jüngste Version). Fortsetzbar: hochgeladen
        wird höchstens einmal, kein Stand doppelt."""
        e: UebernehmenEingabe = k.eingabe
        adresse = teile.einstellungen.altbestand_adresse
        if not adresse:
            raise ValueError("Keine alte App eingetragen (Einstellungen, Altbestand)")
        kw = teile.zugang()
        ordner = teile.arbeit / k.auftrag_id
        ordner.mkdir(parents=True, exist_ok=True)
        try:
            async with httpx.AsyncClient() as client:
                alte = altbestand.AlteApp(adresse, client)
                await k.fortschritt(None, "Altbestand lesen", phase="lesen")
                eintrag = next((a for a in await alte.aufnahmen() if a.schluessel == e.schluessel), None)
                if eintrag is None:
                    raise ValueError("Diese Aufnahme gibt es in der alten App nicht (mehr)")
                if "aufnahme_id" not in k.zwischenstand:
                    if schon := await kw.suchen({altbestand.FELD_ALTBESTAND: eintrag.quelle}, 1):
                        raise ValueError(f"Schon übernommen: {schon[0].pfad}")
                    if teil := await kw.suchen({altbestand.FELD_ALTBESTAND_TEIL: eintrag.quelle}, 1):
                        # eine abgebrochene Übernahme: die Aufnahme liegt schon da, vorhandene Stände zählen
                        vorhanden = (await teile.index.zur_quelle([str(teil[0].id)])).get(str(teil[0].id), [])
                        merken: dict = {"aufnahme_id": str(teil[0].id)}
                        if vorhanden:
                            merken |= {"transkript_id": str(vorhanden[0].id),
                                       "staende_fertig": len(await teile.transkripte.versionen(vorhanden[0].id))}
                        await k.merken(**merken)
                if "aufnahme_id" in k.zwischenstand:
                    quelle = await kw.knoten(k.zwischenstand["aufnahme_id"])
                else:
                    await k.fortschritt(None, f"Original laden ({eintrag.name})", phase="laden")
                    roh = ordner / f"original{eintrag.endung}"
                    await alte.original(eintrag.staende[-1].id, roh)
                    dauer = await geduldig(k, lambda: teile.ton.dauer(roh, titel=f"{eintrag.name}, Dauer"), "Dauer messen")
                    await k.pruefen()
                    await k.fortschritt(None, "In der Kellerwolke ablegen", phase="ablegen")
                    zweig = (await kw.ich()).zweig
                    unter = orte.unterordner(e.zielordner)
                    ziel = await kw.ordner(orte.ort(zweig, orte.AUFNAHMEN, *([unter] if unter else [])))
                    stamm = orte.dateiname(e.name).removesuffix(orte.ENDUNG)
                    n = 1
                    while await kw.finden(orte.ort(ziel.pfad, f"{stamm}{f' ({n})' if n > 1 else ''}{eintrag.endung}")) is not None:
                        n += 1
                    quelle = await kw.schreiben(orte.ort(ziel.pfad, f"{stamm}{f' ({n})' if n > 1 else ''}{eintrag.endung}"), roh,
                                                nur_neu=True)
                    quelle = await kw.felder_setzen(quelle.id, {altbestand.FELD_ALTBESTAND_TEIL: eintrag.quelle,
                                                                orte.FELD_DAUER: round(dauer, 3)})
                    roh.unlink(missing_ok=True)
                    await k.merken(aufnahme_id=str(quelle.id))
                tid: str | None = k.zwischenstand.get("transkript_id")
                fertig = int(k.zwischenstand.get("staende_fertig", 0))
                t = knoten = None
                for nummer, stand in enumerate(eintrag.staende):
                    if nummer < fertig:
                        continue
                    await k.fortschritt(nummer / len(eintrag.staende), f"Stand {nummer + 1} von {len(eintrag.staende)} übernehmen",
                                        phase="staende")
                    t = altbestand.in_transkript(await alte.transkript(stand.id), e.name,
                                                 Quelle(knoten_id=quelle.id, pfad=quelle.pfad, etag=quelle.etag),
                                                 float(quelle.felder.get(orte.FELD_DAUER) or eintrag.dauer_s))
                    if tid is None:
                        t, knoten = await teile.transkripte.speichern(t, quelle, t.aenderung)
                        tid = str(knoten.id)
                    else:
                        _, bisher = await teile.transkripte.lesen(tid)
                        t, knoten = await teile.transkripte.schreiben(tid, t, bisher.etag or "", t.aenderung)
                    await teile.index.notiz_merken(t, knoten)    # jeder Stand sagt, woher er kommt (nicht erst der Abgleich)
                    await k.merken(transkript_id=tid, staende_fertig=nummer + 1)
                if t is not None and knoten is not None:
                    await teile.index.eintragen(t, knoten)
                quelle = await kw.felder_setzen(quelle.id, {altbestand.FELD_ALTBESTAND: eintrag.quelle})   # erst jetzt fertig
            await g.protokoll.eintragen("altbestand.uebernommen", f"{eintrag.name} nach {quelle.pfad} ({len(eintrag.staende)} Stände)",
                                        bezug_art="aufnahme", bezug_name=e.von)
            folge = None
            if e.neu_transkribieren and tid:
                folge = await g.auftraege.einreihen("transkribieren", TranskribierenEingabe(   # wird die jüngste Version
                    quelle_id=quelle.id, name=e.name, sprache=e.sprache, sprecher=e.sprecher, anzahl=e.anzahl,
                    hauptfassung=True, von=e.von), titel=f"{e.name}: neu transkribieren")
            return {"aufnahme_id": str(quelle.id), "transkript_id": tid, "pfad": quelle.pfad, "staende": len(eintrag.staende),
                    "folgeauftrag": folge.id if folge else None}
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    # --- sprecher_erkennen ----------------------------------------------------------------------------------------

    async def sprecher_erkennen(k: Kontext) -> dict:
        e: SprecherEingabe = k.eingabe
        transkripte = teile.transkripte_fuer(e.anfrage_id)
        t, knoten = await transkripte.lesen(e.transkript_id)
        quelle = aufnahme_id(t, knoten)
        if quelle is None:
            raise ValueError("Das Transkript nennt keine Aufnahme; ohne Ton keine Sprechererkennung")
        ordner = teile.arbeit / k.auftrag_id
        ordner.mkdir(parents=True, exist_ok=True)
        try:
            await k.fortschritt(0.0, "Vorbereiten", phase="vorbereiten")
            v = await ton_holen(k, quelle, ordner, teile.zugang(e.anfrage_id))
            wav = v.wav
            plan = await abschnitte(k, v)
            gesammelt: dict[str, list] = dict(k.zwischenstand.get("abdruecke", {}))
            for a in plan:
                if str(a.nummer) in gesammelt:
                    continue
                await k.pruefen()
                await k.fortschritt(len(gesammelt) / len(plan), f"Stimmabdrücke, Abschnitt {a.nummer} von {len(plan)}",
                                    phase="abdruecke")
                drin = [s for s in t.segmente if a.start <= s.start < a.ende]
                stueck = await ausschneiden(wav, a.start, a.ende, ordner / f"abschnitt-{a.nummer}.wav")
                zeiten = [(round(max(0.0, s.start - a.start), 3), round(min(a.ende, s.ende) - a.start, 3)) for s in drin]
                gesammelt[str(a.nummer)] = await geduldig(
                    k, lambda: teile.klangwerk.abdruecke(stueck, zeiten, titel=f"{t.name}, Sprecher", prioritaet="hintergrund"),
                    "Stimmabdrücke")
                stueck.unlink(missing_ok=True)
                await k.merken(abdruecke=gesammelt)
            abdruecke = [x for a in plan for x in gesammelt[str(a.nummer)]]
            segmente, sprecher = await sprecher_bestimmen(k, wav, ordner, t.segmente, abdruecke, e.anzahl, t.name,
                                                          trennung=e.weg == "trennung", plan=plan)
            await k.fortschritt(None, "Speichern", phase="speichern")
            neu = t.model_copy(update={"segmente": segmente, "sprecher": sprecher,
                                       "wellenform": t.wellenform or v.wellenform})
            try:
                neu, knoten = await transkripte.schreiben(e.transkript_id, neu, knoten.etag,
                                                          Aenderung(was="Sprecher neu erkannt", wer=e.von))
            except StandVeraltet as f:
                raise RuntimeError("Das Transkript wurde inzwischen geändert; bitte die Erkennung neu starten") from f
            await teile.geschrieben(neu, knoten, e.anfrage_id)
            return {"transkript_id": str(e.transkript_id), "sprecher": len(sprecher)}
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    # --- korrigieren ----------------------------------------------------------------------------------------------

    async def korrigieren(k: Kontext) -> dict:
        e: KorrigierenEingabe = k.eingabe
        modell = teile.ki_modell()
        t, _ = await teile.transkripte_fuer(e.anfrage_id).lesen(e.transkript_id)
        bereiche = korrektur.fenster(len(t.segmente))
        gesammelt: list[dict] = list(k.zwischenstand.get("vorschlaege", []))
        erledigt = int(k.zwischenstand.get("fenster", 0))
        await k.fortschritt(erledigt / max(len(bereiche), 1), "Korrigieren", phase="korrigieren")
        for n, bereich in enumerate(bereiche):
            if n < erledigt:
                continue
            await k.pruefen()
            antwort = await geduldig(k, lambda: g_leitstelle().chat(
                korrektur.anfrage(t.segmente, bereich), modell=modell,
                titel=f"{t.name}, Korrektur {n + 1} von {len(bereiche)}", prioritaet="hintergrund",
                temperature=0.1, max_tokens=1200), "Korrektur")
            gesammelt += [v.model_dump(mode="json") for v in korrektur.vorschlaege(t.segmente, bereich, antwort.text)]
            await k.merken(vorschlaege=gesammelt, fenster=n + 1)
            await k.fortschritt((n + 1) / len(bereiche), f"Fenster {n + 1} von {len(bereiche)}")
        liste = [korrektur.Vorschlag.model_validate(v) for v in gesammelt]
        await teile.vorschlaege.ersetzen(e.transkript_id, k.auftrag_id, liste)
        return {"transkript_id": str(e.transkript_id), "vorschlaege": len(liste)}

    # --- auswerten ------------------------------------------------------------------------------------------------

    async def auswerten(k: Kontext) -> dict:
        e: AuswertenEingabe = k.eingabe
        modell = teile.ki_modell()
        kw = teile.zugang(e.anfrage_id)
        t, knoten = await teile.transkripte_fuer(e.anfrage_id).lesen(e.transkript_id)
        await k.fortschritt(None, auswertung.titel(e.vorlage), phase="auswerten")
        antwort = await geduldig(k, lambda: g_leitstelle().chat(
            auswertung.anfrage(e.vorlage, export.als_markdown(t)), modell=modell,
            titel=f"{t.name}, {auswertung.titel(e.vorlage)}", prioritaet="hintergrund", temperature=0.2,
            max_tokens=3000), "Auswertung")
        await k.fortschritt(None, "Speichern", phase="speichern")
        inhalt = f"# {t.name}: {auswertung.titel(e.vorlage)}\n\n{antwort.text.strip()}\n".encode()
        if (aufnahme := aufnahme_id(t, knoten)) is not None:
            # neben die Aufnahme, die Vorlage ist die Rolle (Runde.protokoll.md); erneut ausgewertet: neue Version
            datei = await begleiter_ablegen(kw, aufnahme, e.vorlage, auswertung.zusatz(e.vorlage), inhalt,
                                            "text/markdown; charset=utf-8")
            return {"transkript_id": str(e.transkript_id), "datei_id": str(datei.id), "pfad": datei.pfad,
                    "modell": antwort.modell}
        ordner = str(PurePosixPath(knoten.pfad).parent)
        zusatz = 0
        while True:
            zusatz += 1
            dateiname = auswertung.dateiname(t.name if zusatz == 1 else f"{t.name} {zusatz}", e.vorlage)
            try:
                datei = await kw.schreiben(orte.ort(ordner, dateiname), inhalt, nur_neu=True,
                                           inhaltstyp="text/markdown; charset=utf-8")
                break
            except StandVeraltet:
                if zusatz >= 100:
                    raise
        await kw.herkunft_setzen(datei.id, knoten.id, "abgeleitet_von")
        return {"transkript_id": str(e.transkript_id), "datei_id": str(datei.id), "pfad": datei.pfad,
                "modell": antwort.modell}

    def g_leitstelle():
        if g.leitstelle is None:
            raise KeineLeitstelle("Keine Leitstelle eingerichtet")
        return g.leitstelle

    # --- profile_uebernehmen --------------------------------------------------------------------------------------

    async def profile_uebernehmen(k: Kontext) -> dict:
        """Sprecherprofile der alten App in die eigenen; vorhandene Namen bleiben, wie sie sind."""
        e: ProfileUebernehmenEingabe = k.eingabe
        await k.fortschritt(None, f"{len(e.profile)} Profile einmischen", phase="profile")
        ergebnis = await teile.profile.aendern(lambda p: altbestand.profile_einmischen(p, e.profile))
        await g.protokoll.eintragen("altbestand.profile", f"{len(ergebnis['neu'])} Sprecherprofile übernommen",
                                    bezug_art="sprecher", bezug_name=e.von)
        return ergebnis

    vorbereiten = Phase(schluessel="vorbereiten", titel="Vorbereiten", symbol="box-open")
    speichern = Phase(schluessel="speichern", titel="Speichern", symbol="floppy-disk")
    sprecher_phase = Phase(schluessel="sprecher", titel="Sprecher", symbol="user-group")
    hoeren_phasen = [vorbereiten, Phase(schluessel="hoeren", titel="Hören", symbol="ear-listen"), sprecher_phase, speichern]
    return [
        Art("transkribieren", "Transkribieren", transkribieren_in_reihe, eingabe=TranskribierenEingabe, fortsetzbar=True,
            nach_neustart="fortsetzen", phasen=hoeren_phasen),
        Art("aus_anfrage", "Transkribieren (Kellerwolke)", aus_anfrage, eingabe=AnfrageEingabe, fortsetzbar=True,
            nach_neustart="fortsetzen", phasen=hoeren_phasen),
        Art("sprecher_erkennen", "Sprecher erkennen", sprecher_erkennen, eingabe=SprecherEingabe, fortsetzbar=True,
            nach_neustart="fortsetzen",
            phasen=[vorbereiten, Phase(schluessel="abdruecke", titel="Stimmabdrücke", symbol="fingerprint"),
                    sprecher_phase, speichern]),
        Art("korrigieren", "KI-Korrektur", korrigieren, eingabe=KorrigierenEingabe, fortsetzbar=True,
            nach_neustart="fortsetzen",
            phasen=[Phase(schluessel="korrigieren", titel="Korrigieren", symbol="wand-magic-sparkles")]),
        Art("auswerten", "Auswertung", auswerten, eingabe=AuswertenEingabe, nach_neustart="fortsetzen",
            phasen=[Phase(schluessel="auswerten", titel="Auswerten", symbol="list-ul"), speichern]),
        Art("zusammenfuehren", "Ablage zusammenführen", lambda k: umzug.ausfuehren(teile, k), fortsetzbar=True,
            nach_neustart="fortsetzen", phasen=[Phase(schluessel="umziehen", titel="Zusammenführen", symbol="code-merge")]),
        Art("uebernehmen", "Übernehmen", uebernehmen, eingabe=UebernehmenEingabe, fortsetzbar=True, nach_neustart="fortsetzen",
            phasen=[Phase(schluessel="lesen", titel="Altbestand lesen", symbol="box-archive"),
                    Phase(schluessel="laden", titel="Original laden", symbol="download"),
                    Phase(schluessel="ablegen", titel="Ablegen", symbol="cloud-arrow-up"),
                    Phase(schluessel="staende", titel="Stände übernehmen", symbol="clock-rotate-left")]),
        Art("profile_uebernehmen", "Sprecherprofile übernehmen", profile_uebernehmen, eingabe=ProfileUebernehmenEingabe,
            phasen=[Phase(schluessel="profile", titel="Profile", symbol="user-group")]),
    ]


# Was die App im Dateimenü der Kellerwolke anbietet (und in der eigenen Dateiwahl): Ton und Video transkribieren, im
# Hintergrund als Auftrag aus_anfrage; öffnen führt in die Ansicht der App. Auch am Transkript erscheint Öffnen.
MEDIEN = ("audio/*", "video/*")
ANGEBOTE = [
    Angebot(Aktion(kennung="oeffnen", titel="In Transkription öffnen", symbol="fa-up-right-from-square", typen=MEDIEN,
                   art="oeffnen", rolle=orte.ROLLE)),
    Angebot(Aktion(kennung="transkribieren", titel="Transkribieren", titel_erneut="Neu transkribieren",
                   symbol="fa-closed-captioning", typen=MEDIEN, rolle=orte.ROLLE), auftrag="aus_anfrage"),
]


__all__ = ["ANGEBOTE", "AuswertenEingabe", "KorrigierenEingabe", "ProfileUebernehmenEingabe", "SprecherEingabe", "TranskribierenAnfrage", "TranskribierenEingabe",
           "UebernehmenAnfrage", "UebernehmenEingabe",
           "arten", "geduldig"]
