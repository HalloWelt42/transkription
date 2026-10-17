"""Ton vorbereiten mit ffmpeg: Dauer messen, in 16 kHz mono wandeln (auch aus Video), Sprechpausen finden, Abschnitte
planen und ausschneiden. Die Dienste der Leitstelle bekommen so nie eine ganze lange Aufnahme am Stück, und ein
abgebrochener Auftrag setzt beim nächsten Abschnitt wieder an.

Ein Abschnitt endet in der Mitte einer Sprechpause, möglichst nah an der Höchstlänge und lieber an einer längeren
Pause; gibt es im Fenster keine Pause, wird hart bei der Höchstlänge geschnitten.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

SUCHORTE = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")
_STILLE_BEGINN = re.compile(r"silence_start: (-?[0-9.]+)")
_STILLE_ENDE = re.compile(r"silence_end: (-?[0-9.]+)")


class TonFehler(Exception):
    """ffmpeg fehlt oder konnte die Datei nicht lesen."""


@dataclass(frozen=True)
class Pause:
    start: float
    ende: float

    @property
    def mitte(self) -> float:
        return (self.start + self.ende) / 2

    @property
    def laenge(self) -> float:
        return self.ende - self.start


@dataclass(frozen=True)
class Abschnitt:
    nummer: int
    start: float
    ende: float


def programm(name: str, eingestellt: str = "") -> str:
    """Pfad zu ffmpeg oder ffprobe: eingestellt, sonst im Suchpfad, sonst an den üblichen Orten."""
    if eingestellt:
        kandidat = Path(eingestellt).expanduser()
        kandidat = kandidat.with_name(name) if kandidat.name in ("ffmpeg", "ffprobe") else kandidat / name
        if kandidat.is_file():
            return str(kandidat)
    gefunden = shutil.which(name) or next((f"{o}/{name}" for o in SUCHORTE if Path(o, name).is_file()), None)
    if not gefunden:
        raise TonFehler(f"{name} nicht gefunden (in den Einstellungen den Ordner von ffmpeg eintragen)")
    return gefunden


async def _ausfuehren(*befehl: str) -> tuple[str, str]:
    prozess = await asyncio.create_subprocess_exec(*befehl, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        aus, fehler = await prozess.communicate()
    except asyncio.CancelledError:
        prozess.kill()
        await prozess.wait()
        raise
    if prozess.returncode != 0:
        letzte = fehler.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise TonFehler(f"{Path(befehl[0]).name} gescheitert: {' '.join(letzte)}")
    return aus.decode("utf-8", "replace"), fehler.decode("utf-8", "replace")


class Ton:
    def __init__(self, ordner: str = "") -> None:
        self.ordner = ordner

    async def dauer(self, datei: Path) -> float:
        aus, _ = await _ausfuehren(programm("ffprobe", self.ordner), "-v", "error", "-show_entries", "format=duration",
                                   "-of", "json", str(datei))
        try:
            return float(json.loads(aus)["format"]["duration"])
        except (KeyError, ValueError, TypeError) as f:
            raise TonFehler("Dauer nicht lesbar (keine Ton- oder Videodatei?)") from f

    async def wandeln(self, quelle: Path, ziel: Path) -> Path:
        """16 kHz mono 16 bit WAV (Video: nur die Tonspur); erst vollständig, dann an seinen Platz."""
        vorlaeufig = ziel.with_name(f".{ziel.name}.teil.wav")
        await _ausfuehren(programm("ffmpeg", self.ordner), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                          "-i", str(quelle), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(vorlaeufig))
        vorlaeufig.replace(ziel)
        return ziel

    async def pausen(self, datei: Path, *, schwelle_db: float = -35.0, mindestens_s: float = 0.4) -> list[Pause]:
        _, protokoll = await _ausfuehren(programm("ffmpeg", self.ordner), "-nostdin", "-hide_banner", "-i", str(datei),
                                         "-af", f"silencedetect=noise={schwelle_db}dB:d={mindestens_s}", "-f", "null", "-")
        pausen, beginn = [], None
        for zeile in protokoll.splitlines():
            if (b := _STILLE_BEGINN.search(zeile)) is not None:
                beginn = max(0.0, float(b.group(1)))
            elif (e := _STILLE_ENDE.search(zeile)) is not None and beginn is not None:
                pausen.append(Pause(beginn, float(e.group(1))))
                beginn = None
        return pausen

    async def ausschneiden(self, datei: Path, abschnitt: Abschnitt, ziel: Path) -> Path:
        await _ausfuehren(programm("ffmpeg", self.ordner), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                          "-ss", f"{abschnitt.start:.3f}", "-to", f"{abschnitt.ende:.3f}", "-i", str(datei),
                          "-c:a", "pcm_s16le", str(ziel))
        return ziel

    async def wellenform(self, datei: Path, punkte: int = 800) -> list[int]:
        """Lautstärke in `punkte` Abschnitten (0 bis 100, Spitzenwert je Abschnitt) für die Anzeige im Spieler. Aus
        2000 Werten je Sekunde: genug für die Grundtöne der Stimme (weniger würde sie beim Umrechnen wegfiltern) und
        klein genug für Stunden (zwei Stunden etwa 30 MB). Ausreißer zählen nicht: 100 ist das 99. Perzentil."""
        import numpy as np

        prozess = await asyncio.create_subprocess_exec(
            programm("ffmpeg", self.ordner), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(datei),
            "-ac", "1", "-ar", "2000", "-f", "s16le", "-", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        roh, fehler = await prozess.communicate()
        if prozess.returncode != 0:
            raise TonFehler(f"ffmpeg gescheitert: {fehler.decode('utf-8', 'replace').strip()[-200:]}")
        werte = np.abs(np.frombuffer(roh, dtype="<i2").astype(np.float64))
        if werte.size == 0:
            return []
        teile = np.array_split(werte, min(punkte, werte.size))
        spitzen = np.array([t.max() for t in teile])
        hoch = float(np.percentile(spitzen, 99)) or float(spitzen.max()) or 1.0
        return [int(min(100, round(100 * w / hoch))) for w in spitzen]

    async def flac(self, datei: Path, ziel: Path) -> Path:
        """Verlustfrei kleiner (etwa die Hälfte) für Dienste, die die ganze Aufnahme brauchen (Sprechertrennung)."""
        await _ausfuehren(programm("ffmpeg", self.ordner), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                          "-i", str(datei), "-c:a", "flac", str(ziel))
        return ziel


def abschnitte_planen(dauer: float, pausen: list[Pause], *, hoechstens_s: float = 600.0,
                      mindestens_s: float = 60.0) -> list[Abschnitt]:
    """Abschnitte von höchstens `hoechstens_s` Sekunden, geschnitten in Sprechpausen (siehe Modultext)."""
    if dauer <= 0:
        return []
    abschnitte: list[Abschnitt] = []
    start = 0.0
    while dauer - start > hoechstens_s:
        grenze = start + hoechstens_s
        im_fenster = [p for p in pausen if start + mindestens_s <= p.mitte <= grenze]
        spaet = [p for p in im_fenster if p.mitte >= start + hoechstens_s * 0.6]
        if spaet:
            schnitt = max(spaet, key=lambda p: (round(p.laenge, 1), p.mitte)).mitte
        elif im_fenster:
            schnitt = im_fenster[-1].mitte
        else:
            schnitt = grenze
        abschnitte.append(Abschnitt(len(abschnitte) + 1, round(start, 3), round(schnitt, 3)))
        start = schnitt
    abschnitte.append(Abschnitt(len(abschnitte) + 1, round(start, 3), round(dauer, 3)))
    return abschnitte
