"""Altbestand der alten Sprachwerkstatt: eigene Tonaufnahmen und ihre Transkripte von Hand übernehmen (Entwurf 1d).

Die alte App liefert nur lesend: Eckdaten aller fertigen Transkripte (`/api/transcribe/kurz`), ein Transkript ganz
(`/api/transcribe/<id>`) und die Quelldatei unverändert mit SHA-256 im Kopf (`/api/transcribe/<id>/original`). Hier wird
daraus der Altbestand: nur eigene Aufnahmen (keine Tonspuren von Videos, keine Ergebnisse der Sprachausgabe), je
Quelldatei ein Eintrag mit all ihren Ständen. Die Übernahme selbst ist ein Auftrag (arten.py).
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from .modell.transkript import Aenderung, ErzeugtMit, Quelle, Segment, Sprecher, Transkript, Wort

PORT = 10031                      # Vorgabe der alten App
FELD_ALTBESTAND = "altbestand"    # an der übernommenen Aufnahme: Pfad der Quelle in der alten App
SPRACHEN = {"german": "de", "english": "en", "french": "fr", "spanish": "es", "italian": "it", "dutch": "nl"}


class AltFehler(Exception):
    """Die alte App antwortet nicht oder anders als erwartet."""


class AltStand(BaseModel):
    id: str
    erstellt_am: str
    segmente: int
    sprecher: int
    mit_woertern: bool


class AltAufnahme(BaseModel):
    schluessel: str               # Kurzform des Quellpfads, stabil über Aufrufe
    quelle: str                   # Pfad der Quelldatei in der alten App
    name: str                     # wie in der alten App
    vorschlag: str                # Name für die Übernahme (ohne Endung)
    endung: str
    groesse: int | None
    dauer_s: float
    staende: list[AltStand]       # älteste zuerst


def schluessel(quelle: str) -> str:
    return hashlib.sha256(quelle.encode()).hexdigest()[:16]


def ist_eigene_aufnahme(name: str, quelle: str) -> bool:
    """Eigene Tonaufnahmen: keine Tonspuren aus Videos (tubevault_) und keine Ergebnisse der Sprachausgabe (results)."""
    return bool(quelle) and not name.startswith("tubevault_") and "/results/" not in quelle


def gruppieren(kurz: list[dict[str, Any]]) -> list[AltAufnahme]:
    je_quelle: dict[str, list[dict[str, Any]]] = {}
    for t in kurz:
        quelle = t.get("source_audio_path") or ""
        if ist_eigene_aufnahme(t.get("name") or "", quelle):
            je_quelle.setdefault(quelle, []).append(t)
    aus = []
    for quelle, liste in je_quelle.items():
        liste.sort(key=lambda t: t.get("created_at") or "")
        neuester = liste[-1]
        name = neuester.get("name") or PurePosixPath(quelle).name
        aus.append(AltAufnahme(
            schluessel=schluessel(quelle), quelle=quelle, name=name, vorschlag=PurePosixPath(name).stem,
            endung=PurePosixPath(quelle).suffix.lower(), groesse=neuester.get("source_size"),
            dauer_s=float(max((t.get("dauer_s") or 0) for t in liste)),
            staende=[AltStand(id=t["id"], erstellt_am=t.get("created_at") or "", segmente=t.get("segment_count") or 0,
                              sprecher=t.get("speaker_count") or 0, mit_woertern=bool(t.get("mit_woertern"))) for t in liste]))
    return sorted(aus, key=lambda a: a.staende[-1].erstellt_am, reverse=True)


class AlteApp:
    def __init__(self, adresse: str, client: httpx.AsyncClient) -> None:
        self.adresse = adresse.rstrip("/")
        self._client = client

    async def _json(self, pfad: str, zeit: float = 60.0) -> Any:
        try:
            antwort = await self._client.get(f"{self.adresse}{pfad}", timeout=zeit)
        except httpx.HTTPError as f:
            raise AltFehler(f"Die alte App unter {self.adresse} antwortet nicht ({type(f).__name__})") from f
        if antwort.status_code != 200:
            raise AltFehler(f"Die alte App meldet {antwort.status_code} für {pfad}")
        return antwort.json()

    async def aufnahmen(self) -> list[AltAufnahme]:
        return gruppieren(await self._json("/api/transcribe/kurz"))

    async def transkript(self, alt_id: str) -> dict[str, Any]:
        return await self._json(f"/api/transcribe/{alt_id}")

    async def original(self, alt_id: str, ziel: Path) -> str:
        """Lädt die Quelldatei unverändert und prüft die Prüfsumme; liefert sie."""
        summe = hashlib.sha256()
        try:
            async with self._client.stream("GET", f"{self.adresse}/api/transcribe/{alt_id}/original",
                                           timeout=httpx.Timeout(60, read=600)) as antwort:
                if antwort.status_code != 200:
                    raise AltFehler(f"Die alte App liefert das Original nicht ({antwort.status_code})")
                erwartet = antwort.headers.get("x-pruefsumme", "")
                with ziel.open("wb") as f:
                    async for stueck in antwort.aiter_bytes(1024 * 1024):
                        summe.update(stueck)
                        f.write(stueck)
        except httpx.HTTPError as f:
            raise AltFehler(f"Laden aus der alten App abgebrochen ({type(f).__name__})") from f
        if not erwartet or summe.hexdigest() != erwartet:
            raise AltFehler("Prüfsumme des Originals stimmt nicht; nichts übernommen")
        return erwartet


async def suchen(netze: list[str], client: httpx.AsyncClient, zeit: float = 0.4) -> list[str]:
    """Adressen im Heimnetz, unter denen die alte App antwortet (je /24 der bekannten Rechner, Port PORT)."""
    kandidaten: list[str] = []
    for adresse in netze:
        host = urlsplit(adresse).hostname or ""
        try:
            netz = ipaddress.ip_network(f"{host}/24", strict=False)
        except ValueError:
            continue
        kandidaten += [str(ip) for ip in netz.hosts() if str(ip) not in kandidaten]
    grenze = asyncio.Semaphore(64)

    async def pruefen(ip: str) -> str | None:
        async with grenze:
            try:
                _, schreiber = await asyncio.wait_for(asyncio.open_connection(ip, PORT), zeit)
                schreiber.close()
            except (OSError, asyncio.TimeoutError):
                return None
            try:
                antwort = await client.get(f"http://{ip}:{PORT}/api/system/version", timeout=2.0)
                return f"http://{ip}:{PORT}" if antwort.status_code == 200 else None
            except httpx.HTTPError:
                return None

    return [a for a in await asyncio.gather(*(pruefen(ip) for ip in kandidaten)) if a]


# --- Umwandeln ------------------------------------------------------------------------------------------------------

_ROH_SPRECHER = re.compile(r"^SPEAKER_\d+$")


def _zeit(wert: Any) -> float:
    try:
        return max(0.0, round(float(wert), 3))
    except (TypeError, ValueError):
        return 0.0


def in_transkript(alt: dict[str, Any], name: str, quelle: Quelle, dauer_s: float) -> Transkript:
    """Ein Transkript der alten App im Format transkript/1: Sprecher je Gruppe der alten Erkennung (Namen, Stimmabdruck),
    Segmente mit Wortzeiten, so weit vorhanden."""
    sprecher_alt = alt.get("speakers") or []
    segmente_alt = alt.get("segments") or []
    kennung: dict[Any, str] = {}
    sprecher: list[Sprecher] = []

    def zu(gruppe: Any, label: str | None) -> str | None:
        if gruppe is None and not label:
            return None
        schl = gruppe if gruppe is not None else f"name:{label}"
        if schl not in kennung:
            n = len(kennung) + 1
            kennung[schl] = f"s{n}"
            info = next((s for s in sprecher_alt if s.get("cluster") == gruppe), None) if gruppe is not None else None
            titel = (info or {}).get("label") or label or f"Sprecher {n}"
            if _ROH_SPRECHER.match(titel):
                titel = f"Sprecher {n}"
            abdruck = (info or {}).get("embedding")
            sprecher.append(Sprecher(kennung=f"s{n}", name=titel[:120],
                                     abdruck=[float(v) for v in abdruck] if isinstance(abdruck, list) and abdruck else None))
        return kennung[schl]

    segmente = []
    for s in segmente_alt:
        start, ende = _zeit(s.get("start")), _zeit(s.get("end"))
        text = (s.get("text") or "").strip()
        if not text:
            continue
        woerter = []
        for w in s.get("words") or []:
            wort = (w.get("word") or "").strip()
            if wort:
                ws, we = _zeit(w.get("start")), _zeit(w.get("end"))
                woerter.append(Wort(wort=wort, start=ws, ende=max(ws, we)))
        segmente.append(Segment(start=start, ende=max(start, ende), text=text, woerter=woerter,
                                sprecher=zu(s.get("speaker_cluster"), s.get("speaker"))))
    try:
        erstellt = datetime.fromisoformat(alt.get("created_at") or "")
    except ValueError:
        erstellt = None
    daten: dict[str, Any] = dict(
        name=name, quelle=quelle, sprache=SPRACHEN.get((alt.get("language") or "").lower(), "de"),
        dauer_s=round(max(dauer_s, max((s.ende for s in segmente), default=0.0)), 3), sprecher=sprecher, segmente=segmente,
        erzeugt_mit=ErzeugtMit(dienst="alte Sprachwerkstatt", modell=None, app="Übernahme"),
        aenderung=Aenderung(was=f"übernommen aus der alten App (Stand vom {erstellt:%d.%m.%Y %H:%M})" if erstellt else
                            "übernommen aus der alten App", app="Übernahme"))
    if erstellt:
        daten["erstellt_am"] = erstellt
    return Transkript(**daten)
