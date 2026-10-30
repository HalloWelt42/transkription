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
from pydantic import BaseModel, Field

from appkern.anfragen import AnfrageEingabe, Angebot
from appkern.auftraege import Art, Kontext, Phase
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
from .fassung import FASSUNG
from .modell.transkript import Aenderung, ErzeugtMit, Marker, Quelle, Segment, Transkript
from .sprechererkennung import an_wechseln_teilen, erkennen
from .teile import Teile
from appkern.ton import ABSPIELEN, HOEREN, Aufbereiten, Ausgabe, Messen, Pause, PausenWahl
from appkern.ton.wav import ausschnitt, dauer as wav_dauer

from .ton import Abschnitt, abschnitte_planen

T = TypeVar("T")


class TranskribierenAnfrage(BaseModel):
    quelle_id: UUID = Field(description="Knoten der Aufnahme in der Kellerwolke")
    name: str | None = Field(None, max_length=200, description="Name des Transkripts; leer: Name der Aufnahme")
    sprache: Sprache | None = Field(None, description="leer: Vorgabe aus den Einstellungen")
    sprecher: SprecherWeg | None = Field(None, description="ohne, Stimmen gruppieren oder mit Sprechertrennung; leer: Vorgabe "
                                                            "aus den Einstellungen (ab Werk ohne)")
    anzahl: int | None = Field(None, ge=1, le=20, description="bekannte Zahl der Sprecher")
    anfrage_id: UUID | None = Field(None, description="Anfrage der Kellerwolke: die Aufnahme liegt außerhalb der App, die "
                                                      "App darf sie nur für diesen Auftrag lesen")


class TranskribierenEingabe(TranskribierenAnfrage):
    von: str | None = Field(None, description="wer den Auftrag gab (Konto, bei anderen Apps auch die App)")


class AnfrageOptionen(BaseModel):
    """Was eine andere App beim Weitergeben einer Anfrage mitgeben darf (etwa die Vertonung die Sprache des Tons).
    Andere Namen gelten nicht; ein ungültiger Wert lässt den Auftrag mit klarer Meldung scheitern."""

    sprache: Sprache | None = None
    sprecher: SprecherWeg | None = None
    anzahl: int | None = Field(None, ge=1, le=20)


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
        plan = abschnitte_planen(v.dauer, v.pausen, hoechstens_s=teile.einstellungen.abschnitt_min * 60)
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
                                 plan: list[Abschnitt]):
        """Nur auf ausdrücklichen Wunsch: mit `trennung` fragt sie erst die Sprechertrennung (scheitert die, wird
        gruppiert), sonst gruppiert sie die Stimmabdrücke. Mit Trennung werden die Segmente an den Sprecherwechseln
        geteilt und ihre Abdrücke neu bestimmt (sonst mischen lange Segmente zwei Stimmen)."""
        e = teile.einstellungen
        wechsel: list[Wechsel] | None = None
        if trennung:
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
        await teile.sprachen.pruefen(sprache)          # vor aller Arbeit: kann der Hördienst sie?
        weg = e.sprecher or einst.sprecher_weg
        mit_sprechern = weg != "ohne"
        if "transkript_id" in k.zwischenstand:          # schon gespeichert, nur der Abschluss fehlte
            return {"transkript_id": k.zwischenstand["transkript_id"], "ergebnis_id": k.zwischenstand["transkript_id"]}
        kw = teile.zugang(e.anfrage_id)
        transkripte = teile.transkripte_fuer(e.anfrage_id)
        quelle = await kw.knoten(e.quelle_id)
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
                erg = await geduldig(k, lambda: teile.klangwerk.hoeren(stueck, sprache, versatz=a.start, titel=titel,
                                                                        hinweis=hinweis, prioritaet="hintergrund"), "Hören")
                abdruecke: list = []
                if mit_sprechern and erg.segmente:
                    zeiten = [(round(s.start - a.start, 3), round(s.ende - a.start, 3)) for s in erg.segmente]
                    abdruecke = await geduldig(k, lambda: teile.klangwerk.abdruecke(stueck, zeiten, titel=titel,
                                                                                     prioritaet="hintergrund"),
                                               "Stimmabdrücke")
                stueck.unlink(missing_ok=True)
                fertig[str(a.nummer)] = {"segmente": [s.model_dump(mode="json") for s in erg.segmente],
                                         "abdruecke": abdruecke, "sprache": erg.sprache, "modell": erg.modell,
                                         "gerechnet_s": round(time.monotonic() - beginn, 1)}
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

            sprecher = []
            if mit_sprechern and segmente:
                segmente, sprecher = await sprecher_bestimmen(k, wav, ordner, segmente, abdruecke_alle, e.anzahl, name,
                                                              trennung=weg == "trennung", plan=plan)

            segmente = an_satzenden(segmente)       # Beiträge enden an Satzenden, nicht an jeder Sprechpause
            await k.pruefen()
            await k.fortschritt(None, "Speichern", phase="speichern")
            marker = [Marker(zeit=m["zeit"], titel=m["titel"]) for m in quelle.felder.get(orte.FELD_MARKER) or []
                      if isinstance(m, dict) and "zeit" in m and m.get("titel")]
            t = Transkript(name=name, quelle=Quelle(knoten_id=quelle.id, pfad=quelle.pfad, etag=quelle.etag), marker=marker,
                           sprache=(erkannt if sprache == "auto" and erkannt else sprache), dauer_s=round(dauer, 3),
                           sprecher=sprecher, segmente=segmente, wellenform=wellenform,
                           erzeugt_mit=ErzeugtMit(dienst=einst.dienst_hoeren, modell=modell, app=FASSUNG),
                           aenderung=Aenderung(was="erzeugt", wer=e.von))
            t, knoten = await transkripte.speichern(t, quelle, Aenderung(was="erzeugt", wer=e.von),
                                                    erneut=Aenderung(was="neu transkribiert", wer=e.von))
            await k.merken(transkript_id=str(knoten.id))
            await teile.geschrieben(t, knoten, e.anfrage_id)
            return {"transkript_id": str(knoten.id), "ergebnis_id": str(knoten.id), "name": t.name, "pfad": knoten.pfad,
                    "segmente": len(segmente), "sprecher": len(sprecher), "dauer_s": t.dauer_s}
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

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
                folge = await g.auftraege.einreihen("transkribieren", TranskribierenEingabe(
                    quelle_id=quelle.id, name=e.name, sprache=e.sprache, sprecher=e.sprecher, anzahl=e.anzahl,
                    von=e.von), titel=f"{e.name}: neu transkribieren")
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
        Art("transkribieren", "Transkribieren", transkribieren, eingabe=TranskribierenEingabe, fortsetzbar=True,
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
