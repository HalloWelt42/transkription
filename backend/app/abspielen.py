"""Abspielfassungen: der Spieler spielt nie das Original, sondern eine von ffmpeg dekodierte PCM-WAV (44,1 kHz, mono,
16 Bit) derselben Quelle, aus der auch der Hördienst seinen Ton bekommt. So laufen Wortzeiten und Wiedergabe ohne
Versatz: WAV springt im Browser samplegenau, MP3 mit variabler Bitrate oder Aufnahmen aus dem Browser (WebM ohne
Index) nicht. Bewährtes Verfahren der alten txt2voice (dieselben ffmpeg-Parameter).

Die Fassungen sind abgeleitet und jederzeit neu erzeugbar; sie liegen darum nicht in der Kellerwolke, sondern im
Zwischenspeicher der App (`daten/abspielen`), je Quelle und Stand eine Datei. Wird der Speicher voller als erlaubt,
gehen die am längsten nicht gespielten zuerst.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from appkern.kellerwolke import Kellerwolke, Knoten

from .ton import Ton


class Abspielfassungen:
    def __init__(self, ordner: Path, ton: Callable[[], Ton], hoechstens_gb: Callable[[], float]) -> None:
        self.ordner = ordner
        self._ton = ton
        self._hoechstens_gb = hoechstens_gb
        self._sperren: dict[str, asyncio.Lock] = {}

    def pfad(self, quelle: Knoten) -> Path:
        return self.ordner / f"{quelle.id}-{quelle.etag or 'ohne'}.wav"

    def vorhanden(self, quelle: Knoten) -> Path | None:
        p = self.pfad(quelle)
        return p if p.is_file() else None

    async def aus_datei(self, quelle: Knoten, roh: Path) -> Path:
        """Aus einer schon geholten Originaldatei (beim Transkribieren)."""
        async with self._sperre(quelle):
            if (p := self.vorhanden(quelle)) is not None:
                return p
            return await self._erzeugen(quelle, roh)

    async def holen(self, quelle: Knoten, kw: Kellerwolke) -> Path:
        """Die Fassung zur Quelle; fehlt sie, wird das Original geholt und gewandelt."""
        async with self._sperre(quelle):
            if (p := self.vorhanden(quelle)) is not None:
                os.utime(p)                          # zuletzt gespielt: bleibt beim Aufräumen länger
                return p
            self.ordner.mkdir(parents=True, exist_ok=True)
            roh = self.ordner / f".{quelle.id}.roh{PurePosixPath(quelle.name).suffix.lower() or '.bin'}"
            try:
                await kw.herunterladen(quelle.id, roh)
                return await self._erzeugen(quelle, roh)
            finally:
                roh.unlink(missing_ok=True)

    def _sperre(self, quelle: Knoten) -> asyncio.Lock:
        return self._sperren.setdefault(str(quelle.id), asyncio.Lock())

    async def _erzeugen(self, quelle: Knoten, roh: Path) -> Path:
        self.ordner.mkdir(parents=True, exist_ok=True)
        for alt in self.ordner.glob(f"{quelle.id}-*.wav"):          # frühere Stände dieser Quelle
            alt.unlink(missing_ok=True)
        ziel = await self._ton().abspielfassung(roh, self.pfad(quelle))
        self.aufraeumen()
        return ziel

    def aufraeumen(self) -> None:
        if not self.ordner.is_dir():
            return
        grenze = self._hoechstens_gb() * 1024 ** 3
        dateien = sorted((p for p in self.ordner.glob("*.wav")), key=lambda p: p.stat().st_mtime)
        summe = sum(p.stat().st_size for p in dateien)
        jetzt = time.time()
        for p in dateien[:-1]:                       # die neueste bleibt immer
            if summe <= grenze:
                break
            if jetzt - p.stat().st_mtime < 60:       # gerade erst erzeugt oder gespielt
                continue
            summe -= p.stat().st_size
            p.unlink(missing_ok=True)
