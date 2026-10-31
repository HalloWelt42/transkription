"""Mitlesen beim Transkribieren: was ein laufender Auftrag schon gehört hat und wie lange er noch braucht.

Der Auftrag hört in Abschnitten (an Sprechpausen geplant) und legt jeden fertigen Abschnitt in seinen Zwischenstand
(`hoeren`), samt der Rechenzeit, die er gebraucht hat (`gerechnet_s`), und dem Beginn des laufenden (`abschnitt_beginn`).
Daraus kommt hier der Text bis jetzt und die Schätzung: Rechenzeit je Sekunde Ton aus den fertigen Abschnitten dieses
Auftrags, vor dem ersten aus den zuletzt fertigen Aufträgen desselben Hördienstes (jedes Modell hat sein eigenes Tempo);
mal den Ton, der noch fehlt, abzüglich der Zeit, die der laufende Abschnitt schon rechnet. Derselbe Takt gibt dem
Auftrag selbst seinen Fortschritt während eines Abschnitts (siehe `arten`), so steht das Hören nie bei 0 Prozent. Der Zwischenstand ist die einzige Wahrheit, gelesen wird er aus der Tabelle der
Aufträge des Appkerns (der Auftrag selbst gibt ihn nicht heraus).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from appkern.datenbank import Datenbank

ARTEN = ("transkribieren", "aus_anfrage")
FRUEHERE = 10                    # so viele zuletzt fertige Aufträge geben den Takt, solange der eigene fehlt


class Stueck(BaseModel):
    start: float
    ende: float
    text: str


class Bisher(BaseModel):
    zustand: str
    phase: str | None
    schritt: str
    stuecke: list[Stueck] = Field(description="was schon gehört ist, in der Reihenfolge der Aufnahme")
    abschnitte: int = Field(description="so viele Abschnitte hat der Plan (0: noch nicht geplant)")
    abschnitte_fertig: int
    dauer_s: float | None = Field(None, description="Länge der Aufnahme, sobald der Ton gewandelt ist")
    gehoert_bis_s: float = Field(0, description="bis zu dieser Stelle der Aufnahme steht der Text")
    rest_s: float | None = Field(None, description="geschätzte Sekunden, bis das Hören fertig ist; leer: noch keine Schätzung")
    geschaetzt_aus: str = Field("", description="worauf die Schätzung beruht: diesem Auftrag oder früheren")


def _plan(stand: dict[str, Any]) -> list[tuple[int, float, float]]:
    return [(int(a[0]), float(a[1]), float(a[2])) for a in stand.get("abschnitte") or []]


def takt(stand: dict[str, Any]) -> tuple[float, float]:
    """Gemessene Rechenzeit und die Sekunden Ton dazu, aus den fertigen Abschnitten eines Zwischenstands."""
    fertig = stand.get("hoeren") or {}
    rechnen = ton = 0.0
    for nummer, start, ende in _plan(stand):
        teil = fertig.get(str(nummer))
        if teil and teil.get("gerechnet_s"):
            rechnen += float(teil["gerechnet_s"])
            ton += ende - start
    return rechnen, ton


def rest_schaetzen(stand: dict[str, Any], jetzt: datetime, frueher: tuple[float, float] = (0.0, 0.0)) -> tuple[float | None, str]:
    """Sekunden, bis alle Abschnitte gehört sind, und woher der Takt kommt ("" ohne Schätzung)."""
    plan = _plan(stand)
    if not plan:
        return None, ""
    fertig = stand.get("hoeren") or {}
    offen = sum(ende - start for nummer, start, ende in plan if str(nummer) not in fertig)
    if not offen:
        return 0.0, "auftrag"
    rechnen, ton = takt(stand)
    herkunft = "auftrag"
    if not ton:
        rechnen, ton = frueher
        herkunft = "frueher"
    if not ton:
        return None, ""
    rest = offen * rechnen / ton
    if beginn := stand.get("abschnitt_beginn"):
        rest -= (jetzt - datetime.fromisoformat(beginn)).total_seconds()
    return max(rest, 0.0), herkunft


def bisher_aus(zeile: dict[str, Any], jetzt: datetime, frueher: tuple[float, float] = (0.0, 0.0)) -> Bisher:
    stand = json.loads(zeile["zwischenstand"] or "{}")
    plan = _plan(stand)
    fertig = stand.get("hoeren") or {}
    stuecke: list[Stueck] = []
    gehoert_bis = 0.0
    for nummer, _start, ende in plan:              # nur lückenlos von vorn: so wächst der Text von oben nach unten
        teil = fertig.get(str(nummer))
        if teil is None:
            break
        stuecke += [Stueck(start=s["start"], ende=s["ende"], text=s["text"]) for s in teil.get("segmente") or []
                    if (s.get("text") or "").strip()]
        gehoert_bis = ende
    laeuft = zeile["zustand"] in ("wartet", "laeuft")
    rest, herkunft = rest_schaetzen(stand, jetzt, frueher) if laeuft else (None, "")
    return Bisher(zustand=zeile["zustand"], phase=zeile["phase"], schritt=zeile["schritt"] or "", stuecke=stuecke,
                  abschnitte=len(plan), abschnitte_fertig=sum(str(n) in fertig for n, _, _ in plan),
                  dauer_s=stand.get("dauer"), gehoert_bis_s=gehoert_bis, rest_s=rest, geschaetzt_aus=herkunft)


def hoerdienst_von(eingabe: dict[str, Any], vorgabe: str) -> str:
    """Der Hördienst eines Auftrags; ohne Angabe (auch alle vor der Wahl je Auftrag) der eingestellte."""
    return eingabe.get("hoerdienst") or (eingabe.get("optionen") or {}).get("hoerdienst") or vorgabe


class Mitlesen:
    def __init__(self, db: Datenbank, vorgabe: Callable[[], str]) -> None:
        """`vorgabe`: der eingestellte Hördienst (für Aufträge ohne eigene Wahl)."""
        self.db = db
        self.vorgabe = vorgabe

    async def bisher(self, auftrag_id: str) -> Bisher | None:
        """Stand eines Auftrags zum Transkribieren; None, wenn es keinen solchen gibt."""
        platz = ",".join("?" * len(ARTEN))
        zeile = await self.db.zeile(f"SELECT zustand, phase, schritt, zwischenstand, eingabe FROM auftrag WHERE id=? AND art IN ({platz})",
                                    (auftrag_id, *ARTEN))
        if zeile is None:
            return None
        eigen = takt(json.loads(zeile["zwischenstand"] or "{}"))[1] > 0
        frueher = (0.0, 0.0) if eigen else await self.frueher(hoerdienst_von(json.loads(zeile["eingabe"] or "{}"), self.vorgabe()))
        return bisher_aus(zeile, datetime.now(UTC), frueher)

    async def frueher(self, hoerdienst: str) -> tuple[float, float]:
        """Takt der zuletzt fertigen Aufträge dieses Hördienstes (die vor der Messung zählen nicht)."""
        platz = ",".join("?" * len(ARTEN))
        zeilen = await self.db.zeilen(
            f"SELECT zwischenstand, eingabe FROM auftrag WHERE zustand='fertig' AND art IN ({platz}) "
            "ORDER BY erstellt_am DESC LIMIT ?", (*ARTEN, FRUEHERE * 5))
        rechnen = ton = 0.0
        gezaehlt = 0
        for z in zeilen:
            if hoerdienst_von(json.loads(z["eingabe"] or "{}"), self.vorgabe()) != hoerdienst:
                continue
            r, t = takt(json.loads(z["zwischenstand"] or "{}"))
            if t:
                rechnen, ton, gezaehlt = rechnen + r, ton + t, gezaehlt + 1
            if gezaehlt >= FRUEHERE:
                break
        return rechnen, ton
