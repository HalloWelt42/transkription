"""Arten von Aufträgen der Transkription.

transkribieren      Vorbereiten (Ton holen, wandeln, Abschnitte an Sprechpausen planen), Hören (je Abschnitt Text mit
                    Wortzeiten und Stimmabdrücke; nach Abbruch oder Neustart geht es beim nächsten Abschnitt weiter),
                    Sprecher (Trennung oder Gruppieren, Abgleich mit den Profilen), Speichern (Datei, Herkunft, Index).
sprecher_erkennen   für ein vorhandenes Transkript neu, auf Wunsch mit bekannter Sprecherzahl.
korrigieren         KI-Korrektur in Fenstern von drei Segmenten; Ergebnis sind Vorschläge, nichts wird überschrieben.
auswerten           KI-Auswertung nach Vorlage als Markdown-Datei neben dem Transkript.

Wartet die Leitstelle (Halt, Modell lädt, Speicher knapp), steht das als Schritt im Auftrag und es wird nach der
genannten Zeit erneut versucht; gesperrte oder abgelehnte Aufträge gehen ohne Wiederholung an den Menschen.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath
from typing import Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

from appkern.auftraege import Art, Kontext, Phase
from appkern.kellerwolke import KellerwolkeFehler, StandVeraltet
from appkern.leitstelle import DienstFehler, DienstWeg, Halt, NichtErreichbar, NichtGefunden

from . import auswertung, export, korrektur
from .ablage import orte
from .ablage.transkripte import zugang
from .dienste import KeineLeitstelle, Wechsel
from .einstellungen import Sprache, SprecherWeg
from .fassung import FASSUNG
from .modell.transkript import Aenderung, ErzeugtMit, Marker, Quelle, Segment, Transkript
from .sprechererkennung import erkennen
from .teile import Teile
from .ton import Abschnitt, abschnitte_planen

T = TypeVar("T")
GEDULD_S = 30 * 60
WARTEN_S = 30


class TranskribierenAnfrage(BaseModel):
    quelle_id: UUID = Field(description="Knoten der Aufnahme in der Kellerwolke")
    name: str | None = Field(None, max_length=200, description="Name des Transkripts; leer: Name der Aufnahme")
    sprache: Sprache | None = Field(None, description="leer: Vorgabe aus den Einstellungen")
    sprecher: SprecherWeg | None = Field(None, description="ohne, Stimmen gruppieren oder mit Sprechertrennung; leer: Vorgabe "
                                                            "aus den Einstellungen (ab Werk ohne)")
    anzahl: int | None = Field(None, ge=1, le=20, description="bekannte Zahl der Sprecher")


class TranskribierenEingabe(TranskribierenAnfrage):
    von: str | None = Field(None, description="wer den Auftrag gab (Konto, bei anderen Apps auch die App)")


class SprecherEingabe(BaseModel):
    transkript_id: UUID
    weg: Literal["stimmen", "trennung"] = Field("stimmen", description="Stimmen gruppieren oder erst die Sprechertrennung fragen")
    anzahl: int | None = Field(None, ge=1, le=20)
    von: str | None = None


class KorrigierenEingabe(BaseModel):
    transkript_id: UUID
    von: str | None = None


class AuswertenEingabe(BaseModel):
    transkript_id: UUID
    vorlage: auswertung.Vorlage = "protokoll"
    von: str | None = None


WARTEN_BEI: tuple[type[Exception], ...] = (Halt, DienstWeg, NichtErreichbar)


async def geduldig(k: Kontext, aufruf: Callable[[], Awaitable[T]], was: str,
                   warten_bei: tuple[type[Exception], ...] = WARTEN_BEI) -> T:
    """Ruft die Leitstelle; wartet sie (Halt, Dienst lädt oder passt gerade nicht), wird nach ihrer Angabe erneut
    versucht, höchstens `GEDULD_S` lang. Abbrechen geht auch während des Wartens. Wo es einen Ausweg gibt (die
    Sprechertrennung), wird nur bei Halt gewartet."""
    beginn = time.monotonic()
    while True:
        try:
            return await aufruf()
        except warten_bei as f:
            if time.monotonic() - beginn > GEDULD_S:
                raise
            pause = f.nochmal_in or WARTEN_S
            await k.fortschritt(None, f"{was}: {f.meldung}; neuer Versuch in {pause} s")
            for _ in range(int(pause)):
                await k.pruefen()
                await asyncio.sleep(1)


def _segmente(roh: list[dict]) -> list[Segment]:
    return [Segment.model_validate(s) for s in roh]


def arten(teile: Teile) -> list[Art]:
    g = teile.geruest

    async def ton_holen(k: Kontext, quelle_id: UUID | str, ordner: Path) -> tuple[Path, float]:
        """Original holen, für den Hördienst wandeln (16 kHz mono) und gleich die Abspielfassung erzeugen: beide aus
        derselben Quelle mit demselben Dekoder, damit Wortzeiten und Wiedergabe gleich laufen."""
        kw = zugang(lambda: g.kellerwolke)
        quelle = await kw.knoten(quelle_id)
        roh = ordner / f"quelle{PurePosixPath(quelle.name).suffix.lower() or '.bin'}"
        await k.fortschritt(None, f"Ton holen ({quelle.name})")
        await kw.herunterladen(quelle.id, roh)
        await k.fortschritt(None, "Ton wandeln")
        wav = await teile.ton.wandeln(roh, ordner / "ton.wav")
        await k.fortschritt(None, "Abspielfassung erzeugen")
        await teile.abspielen.aus_datei(quelle, roh)
        roh.unlink(missing_ok=True)
        return wav, await teile.ton.dauer(wav)

    async def abschnitte(k: Kontext, wav: Path, dauer: float) -> list[Abschnitt]:
        """Plan aus dem Zwischenstand (beim Fortsetzen derselbe), sonst neu an den Sprechpausen."""
        if "abschnitte" in k.zwischenstand:
            return [Abschnitt(*a) for a in k.zwischenstand["abschnitte"]]
        await k.fortschritt(None, "Sprechpausen suchen")
        plan = abschnitte_planen(dauer, await teile.ton.pausen(wav), hoechstens_s=teile.einstellungen.abschnitt_min * 60)
        await k.merken(abschnitte=[[a.nummer, a.start, a.ende] for a in plan], dauer=dauer)
        return plan

    async def sprecher_bestimmen(k: Kontext, wav: Path, ordner: Path, segmente: list[Segment],
                                 abdruecke: list[list[float] | None], anzahl: int | None, titel: str, trennung: bool):
        """Nur auf ausdrücklichen Wunsch: mit `trennung` fragt sie erst die Sprechertrennung (scheitert die, wird
        gruppiert), sonst gruppiert sie die Stimmabdrücke."""
        e = teile.einstellungen
        wechsel: list[Wechsel] | None = None
        if trennung:
            await k.fortschritt(None, "Sprechertrennung", phase="sprecher")
            try:
                flac = await teile.ton.flac(wav, ordner / "ton.flac")
                wechsel = await geduldig(k, lambda: teile.klangwerk.trennen(
                    flac, anzahl=anzahl, zugang=e.trennen_zugang.get_secret_value(), titel=titel,
                    prioritaet="hintergrund"), "Sprechertrennung", warten_bei=(Halt,))
            except (DienstWeg, DienstFehler, NichtGefunden, NichtErreichbar) as f:
                await g.protokoll.eintragen("sprecher.ohne_trennung", f"{titel}: {f.meldung}", stufe="warnung",
                                            bezug_art="auftrag", bezug_name=titel)
                await k.fortschritt(None, "Sprechertrennung nicht verfügbar; gruppiere nach Stimmen")
        await k.fortschritt(None, "Sprecher zuordnen", phase="sprecher")
        profile, _ = await teile.profile.lesen()
        return erkennen(segmente, abdruecke, wechsel, profile, teile.schwellen, anzahl)

    # --- transkribieren -------------------------------------------------------------------------------------------

    async def transkribieren(k: Kontext) -> dict:
        e: TranskribierenEingabe = k.eingabe
        einst = teile.einstellungen
        sprache = e.sprache or einst.sprache
        weg = e.sprecher or einst.sprecher_weg
        mit_sprechern = weg != "ohne"
        if "transkript_id" in k.zwischenstand:          # schon gespeichert, nur der Abschluss fehlte
            return {"transkript_id": k.zwischenstand["transkript_id"]}
        kw = zugang(lambda: g.kellerwolke)
        quelle = await kw.knoten(e.quelle_id)
        name = e.name or orte.anzeigename(quelle.name)
        ordner = teile.arbeit / k.auftrag_id
        ordner.mkdir(parents=True, exist_ok=True)
        try:
            await k.fortschritt(0.0, "Vorbereiten", phase="vorbereiten")
            wav, dauer = await ton_holen(k, quelle.id, ordner)
            plan = await abschnitte(k, wav, dauer)
            wellenform = await teile.ton.wellenform(wav)
            if quelle.felder.get(orte.FELD_DAUER) is None:
                try:          # für die Liste der Aufnahmen; in nur lesbaren Ordnern geht es nicht, das ist kein Fehler
                    await kw.felder_setzen(quelle.id, {orte.FELD_DAUER: round(dauer, 1)})
                except KellerwolkeFehler:
                    pass

            fertig: dict[str, dict] = dict(k.zwischenstand.get("hoeren", {}))
            await k.fortschritt(len(fertig) / max(len(plan), 1), "Hören", phase="hoeren")
            for a in plan:
                if str(a.nummer) in fertig:
                    continue
                await k.pruefen()
                await k.fortschritt(len(fertig) / len(plan), f"Abschnitt {a.nummer} von {len(plan)}")
                stueck = await teile.ton.ausschneiden(wav, a, ordner / f"abschnitt-{a.nummer}.wav")
                titel = f"{name}, Abschnitt {a.nummer} von {len(plan)}"
                erg = await geduldig(k, lambda: teile.klangwerk.hoeren(stueck, sprache, versatz=a.start, titel=titel,
                                                                        prioritaet="hintergrund"), "Hören")
                abdruecke: list = []
                if mit_sprechern and erg.segmente:
                    zeiten = [(round(s.start - a.start, 3), round(s.ende - a.start, 3)) for s in erg.segmente]
                    abdruecke = await geduldig(k, lambda: teile.klangwerk.abdruecke(stueck, zeiten, titel=titel,
                                                                                     prioritaet="hintergrund"),
                                               "Stimmabdrücke")
                stueck.unlink(missing_ok=True)
                fertig[str(a.nummer)] = {"segmente": [s.model_dump(mode="json") for s in erg.segmente],
                                         "abdruecke": abdruecke, "sprache": erg.sprache, "modell": erg.modell}
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
                                                              trennung=weg == "trennung")

            await k.pruefen()
            await k.fortschritt(None, "Speichern", phase="speichern")
            marker = [Marker(zeit=m["zeit"], titel=m["titel"]) for m in quelle.felder.get(orte.FELD_MARKER) or []
                      if isinstance(m, dict) and "zeit" in m and m.get("titel")]
            t = Transkript(name=name, quelle=Quelle(knoten_id=quelle.id, pfad=quelle.pfad, etag=quelle.etag), marker=marker,
                           sprache=(erkannt if sprache == "auto" and erkannt else sprache), dauer_s=round(dauer, 3),
                           sprecher=sprecher, segmente=segmente, wellenform=wellenform,
                           erzeugt_mit=ErzeugtMit(dienst=einst.dienst_hoeren, modell=modell, app=FASSUNG),
                           aenderung=Aenderung(was="erzeugt", wer=e.von))
            knoten = await teile.transkripte.anlegen(t, quelle)
            await k.merken(transkript_id=str(knoten.id))
            await teile.index.eintragen(t, knoten)
            return {"transkript_id": str(knoten.id), "name": t.name, "pfad": knoten.pfad, "segmente": len(segmente),
                    "sprecher": len(sprecher), "dauer_s": t.dauer_s}
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    # --- sprecher_erkennen ----------------------------------------------------------------------------------------

    async def sprecher_erkennen(k: Kontext) -> dict:
        e: SprecherEingabe = k.eingabe
        t, knoten = await teile.transkripte.lesen(e.transkript_id)
        if t.quelle is None:
            raise ValueError("Das Transkript nennt keine Aufnahme; ohne Ton keine Sprechererkennung")
        ordner = teile.arbeit / k.auftrag_id
        ordner.mkdir(parents=True, exist_ok=True)
        try:
            await k.fortschritt(0.0, "Vorbereiten", phase="vorbereiten")
            wav, dauer = await ton_holen(k, t.quelle.knoten_id, ordner)
            plan = await abschnitte(k, wav, dauer)
            gesammelt: dict[str, list] = dict(k.zwischenstand.get("abdruecke", {}))
            for a in plan:
                if str(a.nummer) in gesammelt:
                    continue
                await k.pruefen()
                await k.fortschritt(len(gesammelt) / len(plan), f"Stimmabdrücke, Abschnitt {a.nummer} von {len(plan)}",
                                    phase="abdruecke")
                drin = [s for s in t.segmente if a.start <= s.start < a.ende]
                stueck = await teile.ton.ausschneiden(wav, a, ordner / f"abschnitt-{a.nummer}.wav")
                zeiten = [(round(max(0.0, s.start - a.start), 3), round(min(a.ende, s.ende) - a.start, 3)) for s in drin]
                gesammelt[str(a.nummer)] = await geduldig(
                    k, lambda: teile.klangwerk.abdruecke(stueck, zeiten, titel=f"{t.name}, Sprecher", prioritaet="hintergrund"),
                    "Stimmabdrücke")
                stueck.unlink(missing_ok=True)
                await k.merken(abdruecke=gesammelt)
            abdruecke = [x for a in plan for x in gesammelt[str(a.nummer)]]
            segmente, sprecher = await sprecher_bestimmen(k, wav, ordner, t.segmente, abdruecke, e.anzahl, t.name,
                                                          trennung=e.weg == "trennung")
            await k.fortschritt(None, "Speichern", phase="speichern")
            neu = t.model_copy(update={"segmente": segmente, "sprecher": sprecher,
                                       "wellenform": t.wellenform or await teile.ton.wellenform(wav)})
            try:
                neu, knoten = await teile.transkripte.schreiben(e.transkript_id, neu, knoten.etag,
                                                                Aenderung(was="Sprecher neu erkannt", wer=e.von))
            except StandVeraltet as f:
                raise RuntimeError("Das Transkript wurde inzwischen geändert; bitte die Erkennung neu starten") from f
            await teile.index.eintragen(neu, knoten)
            return {"transkript_id": str(e.transkript_id), "sprecher": len(sprecher)}
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    # --- korrigieren ----------------------------------------------------------------------------------------------

    async def korrigieren(k: Kontext) -> dict:
        e: KorrigierenEingabe = k.eingabe
        t, _ = await teile.transkripte.lesen(e.transkript_id)
        bereiche = korrektur.fenster(len(t.segmente))
        gesammelt: list[dict] = list(k.zwischenstand.get("vorschlaege", []))
        erledigt = int(k.zwischenstand.get("fenster", 0))
        await k.fortschritt(erledigt / max(len(bereiche), 1), "Korrigieren", phase="korrigieren")
        for n, bereich in enumerate(bereiche):
            if n < erledigt:
                continue
            await k.pruefen()
            antwort = await geduldig(k, lambda: g_leitstelle().chat(
                korrektur.anfrage(t.segmente, bereich), modell=teile.einstellungen.ki_modell or None,
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
        t, knoten = await teile.transkripte.lesen(e.transkript_id)
        await k.fortschritt(None, auswertung.titel(e.vorlage), phase="auswerten")
        antwort = await geduldig(k, lambda: g_leitstelle().chat(
            auswertung.anfrage(e.vorlage, export.als_markdown(t)), modell=teile.einstellungen.ki_modell or None,
            titel=f"{t.name}, {auswertung.titel(e.vorlage)}", prioritaet="hintergrund", temperature=0.2,
            max_tokens=3000), "Auswertung")
        await k.fortschritt(None, "Speichern", phase="speichern")
        kw = zugang(lambda: g.kellerwolke)
        ordner = str(PurePosixPath(knoten.pfad).parent)
        inhalt = f"# {t.name}: {auswertung.titel(e.vorlage)}\n\n{antwort.text.strip()}\n".encode()
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

    vorbereiten = Phase(schluessel="vorbereiten", titel="Vorbereiten", symbol="box-open")
    speichern = Phase(schluessel="speichern", titel="Speichern", symbol="floppy-disk")
    sprecher_phase = Phase(schluessel="sprecher", titel="Sprecher", symbol="user-group")
    return [
        Art("transkribieren", "Transkribieren", transkribieren, eingabe=TranskribierenEingabe, fortsetzbar=True,
            nach_neustart="fortsetzen",
            phasen=[vorbereiten, Phase(schluessel="hoeren", titel="Hören", symbol="ear-listen"), sprecher_phase, speichern]),
        Art("sprecher_erkennen", "Sprecher erkennen", sprecher_erkennen, eingabe=SprecherEingabe, fortsetzbar=True,
            nach_neustart="fortsetzen",
            phasen=[vorbereiten, Phase(schluessel="abdruecke", titel="Stimmabdrücke", symbol="fingerprint"),
                    sprecher_phase, speichern]),
        Art("korrigieren", "KI-Korrektur", korrigieren, eingabe=KorrigierenEingabe, fortsetzbar=True,
            nach_neustart="fortsetzen",
            phasen=[Phase(schluessel="korrigieren", titel="Korrigieren", symbol="wand-magic-sparkles")]),
        Art("auswerten", "Auswertung", auswerten, eingabe=AuswertenEingabe, nach_neustart="fortsetzen",
            phasen=[Phase(schluessel="auswerten", titel="Auswerten", symbol="list-ul"), speichern]),
    ]


__all__ = ["AuswertenEingabe", "KorrigierenEingabe", "SprecherEingabe", "TranskribierenAnfrage", "TranskribierenEingabe",
           "arten", "geduldig"]
