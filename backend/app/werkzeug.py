"""Werkzeuge am Rechner der App für einmalige Übernahmen aus der alten App, im Container etwa
`docker exec transkription python -m app.werkzeug altbestand /daten/umzug/plan.json`. Ohne --ausfuehren ändern sie
nichts. Mit der Kellerwolke reden sie nicht selbst: was dort geschehen soll, reihen sie als Auftrag ein, den die App
mit ihrem eigenen Zugang ausführt (unter Aufträge zu verfolgen).

  altbestand <plan.json> [--ausfuehren]
      Eigene Aufnahmen der alten App samt Transkripten übernehmen (je Aufnahme ein Auftrag "uebernehmen", alte Stände
      werden Versionen) und ihre Sprecherprofile (ein Auftrag). Danach die App neu starten: sie liest dann die Adresse
      der alten App und beginnt mit den Aufträgen.
  umwandeln <liste.json> <ordner>
      Transkripte der alten App ins Format transkript/1, eine Datei je Eintrag (für Dateien, die nicht in diese App
      kommen, etwa Sprachausgaben, die als Begleiter neben ihren Ton gelegt werden).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from appkern.auftraege.dienst import SCHEMA as AUFTRAG_SCHEMA

from .altbestand import AlteApp, AltesProfil, in_transkript
from .arten import ProfileUebernehmenEingabe, UebernehmenAnfrage, UebernehmenEingabe

VON = "Umzug aus der alten App"


class PlanAufnahme(BaseModel):
    quelle: str = Field(min_length=1, description="Pfad der Quelldatei in der alten App (wie sie ihn meldet)")
    zielordner: str = Field("", max_length=300, description="Unterordner von Aufnahmen; leer: direkt dort")
    name: str | None = Field(None, max_length=200, description="leer: der Name in der alten App ohne Endung")


class UmzugPlan(BaseModel):
    adresse: str = Field(min_length=1, description="die alte App, wie die App sie erreicht (etwa http://192.168.178.45:10031)")
    aufnahmen: list[PlanAufnahme] = Field(default_factory=list)
    profile: list[AltesProfil] = Field(default_factory=list)


class Umwandlung(BaseModel):
    id: str = Field(min_length=1, description="Kennung des Transkripts in der alten App")
    name: str = Field(min_length=1)
    dauer_s: float = Field(0.0, ge=0)
    datei: str = Field(min_length=1, description="Dateiname im Zielordner")


class Umwandlungen(BaseModel):
    adresse: str
    eintraege: list[Umwandlung]


def _mb(n: int | None) -> str:
    return f"{(n or 0) / 1e6:.0f} MB"


async def altbestand(plan_datei: Path, ausfuehren: bool, daten: Path | None = None) -> int:
    """`daten`: Datenordner der App (vorgegeben wie bei der App selbst)."""
    plan = UmzugPlan.model_validate_json(plan_datei.read_text(encoding="utf-8"))
    async with httpx.AsyncClient() as client:
        alte = {a.quelle: a for a in await AlteApp(plan.adresse, client).aufnahmen()}
    from .main import app_bauen, daten_ordner
    g = app_bauen(daten or daten_ordner()).state.geruest    # gebaut, nicht gestartet: nur Datenbank und Einstellungen
    await g.db.oeffnen()
    try:
        await g.einstellungen.starten()
        # nur das Schema (wie beim Start der App, ändert bei einer laufenden nichts); nie `auftraege.starten`, das
        # würde die laufenden Aufträge der App für unterbrochen halten
        await g.db.einrichten("auftraege", AUFTRAG_SCHEMA)
        # was schon wartet, läuft oder fertig ist, kommt nicht noch einmal; Gescheitertes darf erneut
        bisher = await g.db.zeilen("SELECT art, eingabe, zustand FROM auftrag WHERE art IN ('uebernehmen', "
                                   "'profile_uebernehmen') AND zustand IN ('wartet', 'laeuft', 'fertig')")
        eingereiht = {json.loads(z["eingabe"]).get("schluessel"): z["zustand"] for z in bisher if z["art"] == "uebernehmen"}
        profile_schon = next((z["zustand"] for z in bisher if z["art"] == "profile_uebernehmen"), None)
        neu: list[UebernehmenAnfrage] = []
        summen: Counter[str] = Counter()
        print(f"Altbestand aus {plan.adresse}{'' if ausfuehren else ' (Vorschau, es ändert sich nichts)'}")
        for a in plan.aufnahmen:
            alt = alte.get(a.quelle)
            name = a.name or (alt.vorschlag if alt else a.quelle.rsplit("/", 1)[-1])
            if alt is None:
                befund = "fehlt"
            elif alt.schluessel in eingereiht:
                befund = f"schon {eingereiht[alt.schluessel]}"
            else:
                befund = "neu"
                neu.append(UebernehmenAnfrage(schluessel=alt.schluessel, zielordner=a.zielordner, name=name))
            summen[befund.split()[0]] += 1
            ziel = "/".join(t for t in ("Aufnahmen", a.zielordner, name + (alt.endung if alt else "")) if t)
            print(f"{befund:16} {ziel}" + (f"  ({len(alt.staende)} Stände, {_mb(alt.groesse)})" if alt else ""))
        for p in plan.profile:
            print(f"{'Profil, ' + profile_schon if profile_schon else 'Profil':16} {p.name} ({p.proben} Proben)")
        print(f"Summe: {summen['neu']} neu, {summen['schon']} schon eingereiht, {summen['fehlt']} fehlen in der alten App; "
              f"{len(plan.profile)} Profile")
        fehlt = summen["fehlt"]
        if not ausfuehren:
            return 1 if fehlt else 0
        if g.einstellungen.stand.altbestand_adresse != plan.adresse:
            await g.einstellungen.aendern({"altbestand_adresse": plan.adresse})
        for a in neu:
            await g.auftraege.einreihen("uebernehmen", UebernehmenEingabe(**a.model_dump(), von=VON),
                                        titel=f"Übernehmen: {a.name}")
        profile_neu = bool(plan.profile) and profile_schon is None
        if profile_neu:
            await g.auftraege.einreihen("profile_uebernehmen", ProfileUebernehmenEingabe(profile=plan.profile, von=VON),
                                        titel="Sprecherprofile übernehmen")
        print(f"Eingereiht: {len(neu)} Übernahmen{', Sprecherprofile' if profile_neu else ''}. "
              "Jetzt die App neu starten, dann beginnt sie.")
        return 1 if fehlt else 0
    finally:
        await g.db.schliessen()


async def umwandeln(liste_datei: Path, ordner: Path) -> int:
    liste = Umwandlungen.model_validate_json(liste_datei.read_text(encoding="utf-8"))
    ordner.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as client:
        alte = AlteApp(liste.adresse, client)
        for e in liste.eintraege:
            ziel = (ordner / e.datei).resolve()
            if not ziel.is_relative_to(ordner.resolve()):
                raise ValueError(f"{e.datei} liegt außerhalb von {ordner}")
            t = in_transkript(await alte.transkript(e.id), e.name, None, e.dauer_s)
            ziel.write_text(t.model_dump_json(indent=1, exclude_none=True), encoding="utf-8")
            print(f"umgewandelt  {e.datei}  ({len(t.segmente)} Abschnitte)")
    return 0


def main() -> None:
    teiler = argparse.ArgumentParser(prog="python -m app.werkzeug", description=__doc__.split("\n\n")[0])
    arten = teiler.add_subparsers(dest="was", required=True)
    a = arten.add_parser("altbestand", help="Aufnahmen und Sprecherprofile der alten App übernehmen")
    a.add_argument("plan", type=Path)
    a.add_argument("--ausfuehren", action="store_true", help="Aufträge einreihen (sonst nur Vorschau)")
    a.add_argument("--daten", type=Path, help="Datenordner der App (sonst wie bei der App selbst)")
    u = arten.add_parser("umwandeln", help="Transkripte der alten App ins Format transkript/1")
    u.add_argument("liste", type=Path)
    u.add_argument("ordner", type=Path)
    argumente = teiler.parse_args()
    if argumente.was == "altbestand":
        sys.exit(asyncio.run(altbestand(argumente.plan, argumente.ausfuehren, argumente.daten)))
    sys.exit(asyncio.run(umwandeln(argumente.liste, argumente.ordner)))


if __name__ == "__main__":
    main()
