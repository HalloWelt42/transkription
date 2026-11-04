"""Orte im Zweig der App und was als Aufnahme gilt. Einzige Stelle für Ordner- und Dateinamen.

Eine Ablage (Entscheidung 17.10.2026): Aufnahmen und ihre Transkripte liegen in einem Baum unter Aufnahmen, das
Transkript als Begleitdatei neben seiner Aufnahme (`Runde.wav`, `Runde.transkript.json`). Den Namen vergibt die
Kellerwolke aus dem Stamm der Aufnahme und dem Zusatz; Verschieben, Umbenennen und Papierkorb nehmen es mit."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from appkern.kellerwolke import Knoten, pfad_aus

AUFNAHMEN = "Aufnahmen"            # Wurzel des einen Baums: Aufnahmen mit ihren Begleitern
ALT_TRANSKRIPTE = "Transkripte"    # nur noch für das Zusammenführen der früheren getrennten Ablage
SPRECHER = "Sprecher"
PROFILE = "profile.json"
WOERTERBUCH = "Fachwörter.json"   # Fachwörter, die dem Hördienst als Hinweis mitgehen
ROLLE = "transkript"               # Rolle des Transkripts als Begleiter seiner Aufnahme
ENDUNG = ".transkript.json"        # zugleich der Zusatz hinter dem Stamm der Aufnahme
INHALTSTYP = "application/json"
TEIL = "teil_"                     # Rolle weiterer Teile eines Gesprächs neben der Aufnahme: teil_b, teil_c ... (HELF-154)
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
    return not knoten.ist_ordner and (knoten.rolle == ROLLE or knoten.name.endswith(ENDUNG))


def teil_rolle(nummer: int) -> str:
    """Rolle des Teils `nummer` (ab 2). Rollen der Kellerwolke kennen nur Kleinbuchstaben und _, darum zählt die Rolle
    in Buchstaben wie Spalten einer Tabelle: 2 ist teil_b, 27 ist teil_aa; die Nummer selbst steht im Transkript."""
    buchstaben = ""
    while nummer > 0:
        nummer, rest = divmod(nummer - 1, 26)
        buchstaben = chr(ord("a") + rest) + buchstaben
    return f"{TEIL}{buchstaben}"


def teil_nummer(rolle: str) -> int:
    nummer = 0
    for zeichen in rolle.removeprefix(TEIL):
        nummer = nummer * 26 + ord(zeichen) - ord("a") + 1
    return nummer


def teil_zusatz(nummer: int, dateiname: str) -> str:
    """Zusatz hinter dem Stamm der Aufnahme: "Runde.teil-2.webm"."""
    return f".teil-{nummer}{PurePosixPath(dateiname).suffix.lower()}"


def ist_teil(knoten: Knoten) -> bool:
    """Ein weiterer Teil eines Gesprächs: gehört zur Aufnahme und erscheint nicht als eigene Aufnahme."""
    return bool(knoten.rolle and knoten.rolle.startswith(TEIL))


def anzeigename(dateiname: str) -> str:
    """Name einer Aufnahme ohne Endung, als Vorschlag für das Transkript."""
    return PurePosixPath(dateiname).stem or dateiname


def dateiname(name: str, zusatz: int = 0) -> str:
    """Sicherer Dateiname eines Transkripts; `zusatz` macht ihn eindeutig ("Folge 12 (2).transkript.json")."""
    sauber = _UNERLAUBT.sub(" ", name).strip(" .") or "Transkript"
    sauber = re.sub(r"\s+", " ", sauber)[:150]
    return f"{sauber} ({zusatz}){ENDUNG}" if zusatz > 1 else f"{sauber}{ENDUNG}"


def unterordner(pfad: str) -> str:
    """Ein relativer Unterordner (etwa "Besprechungen/2026"), jeder Teil wie ein Dateiname bereinigt; leer bleibt leer."""
    teile = [_UNERLAUBT.sub(" ", t).strip(" .") for t in pfad.replace("\\", "/").split("/")]
    teile = [re.sub(r"\s+", " ", t)[:120] for t in teile if t and t not in (".", "..")]
    return "/".join(teile)
