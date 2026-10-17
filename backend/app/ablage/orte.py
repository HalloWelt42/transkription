"""Orte im Zweig der App und was als Aufnahme gilt. Einzige Stelle für Ordner- und Dateinamen."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from appkern.kellerwolke import Knoten, pfad_aus

AUFNAHMEN = "Aufnahmen"
TRANSKRIPTE = "Transkripte"
SPRECHER = "Sprecher"
PROFILE = "profile.json"
ENDUNG = ".transkript.json"
INHALTSTYP = "application/json"
FELD_MARKER = "marker"   # an einer Aufnahme: beim Aufnehmen gesetzte Marker [{zeit, titel}]
FELD_DAUER = "dauer_s"   # an einer Aufnahme: Dauer in Sekunden, sobald bekannt (beim Transkribieren gemessen)

TON = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".aif", ".aiff", ".caf", ".amr"}
VIDEO = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".mpg", ".mpeg", ".wmv", ".3gp"}

_UNERLAUBT = re.compile(r'[/\\:*?"<>|\x00-\x1f]+')


def ort(zweig: str, *teile: str) -> str:
    return pfad_aus(zweig, *teile)


def art_der_aufnahme(knoten: Knoten) -> str | None:
    """"ton", "video" oder None (keine Aufnahme). Inhaltstyp zuerst, sonst die Endung."""
    if knoten.ist_ordner:
        return None
    typ = (knoten.inhaltstyp or "").lower()
    if typ.startswith("audio/"):
        return "ton"
    if typ.startswith("video/"):
        return "video"
    return art_der_aufnahme_name(knoten.name)


def art_der_aufnahme_name(name: str) -> str | None:
    """Nur nach der Endung (vor dem Hochladen)."""
    endung = PurePosixPath(name).suffix.lower()
    return "ton" if endung in TON else "video" if endung in VIDEO else None


def ist_transkript(knoten: Knoten) -> bool:
    return not knoten.ist_ordner and knoten.name.endswith(ENDUNG)


def anzeigename(dateiname: str) -> str:
    """Name einer Aufnahme ohne Endung, als Vorschlag für das Transkript."""
    return PurePosixPath(dateiname).stem or dateiname


def dateiname(name: str, zusatz: int = 0) -> str:
    """Sicherer Dateiname eines Transkripts; `zusatz` macht ihn eindeutig ("Folge 12 (2).transkript.json")."""
    sauber = _UNERLAUBT.sub(" ", name).strip(" .") or "Transkript"
    sauber = re.sub(r"\s+", " ", sauber)[:150]
    return f"{sauber} ({zusatz}){ENDUNG}" if zusatz > 1 else f"{sauber}{ENDUNG}"
