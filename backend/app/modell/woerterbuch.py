"""Fachwörter-Wörterbuch (`Fachwörter.json` im Zweig der App in der Kellerwolke): Wörter in ihrer richtigen
Schreibweise, die dem Hördienst als Hinweis mitgehen, damit er sie so schreibt (etwa Qwen statt "Gwen").

Gepflegt wird es nur von Hand: einsehen und ändern auf der Seite Wörterbuch, und beim Bearbeiten eines Transkripts
schlägt die App korrigierte Wörter zur Aufnahme vor; aufgenommen wird nur, was der Nutzer bestätigt, nie von selbst.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .transkript import jetzt

FORMAT = "woerterbuch/1"
WORT_HOECHSTENS = 60
# Startinhalt, solange es die Datei noch nicht gibt: die Fehlhörungen aus der Aufnahme vom 28.10.2026 (HELF-3)
START = ["Qwen", "ComfyUI", "VAE", "Zigbee", "Ollama", "DynDNS", "Claude"]


def sauber(wort: str) -> str:
    """Ein Wort ohne Leerraum am Rand und ohne Satzzeichen am Ende, Leerraum innen einfach."""
    return " ".join(wort.split()).strip(".,;:!?\"'()[]{}")


class Woerterbuch(BaseModel):
    model_config = ConfigDict(extra="allow")
    format: str = FORMAT
    woerter: list[str] = Field(default_factory=list)
    geaendert_am: datetime = Field(default_factory=jetzt)

    @field_validator("woerter")
    @classmethod
    def _eindeutig(cls, woerter: list[str]) -> list[str]:
        """Bereinigt, ohne Leere und Doppelte (Groß und Klein gleich), erste Schreibweise gilt, sortiert."""
        gesehen: dict[str, str] = {}
        for w in woerter:
            w = sauber(w)
            if not w:
                continue
            if len(w) > WORT_HOECHSTENS:
                raise ValueError(f"Wort zu lang (höchstens {WORT_HOECHSTENS} Zeichen): {w[:20]}...")
            gesehen.setdefault(w.lower(), w)
        return sorted(gesehen.values(), key=str.lower)

    def dazu(self, woerter: list[str]) -> list[str]:
        """Nimmt Wörter auf; liefert die wirklich neuen."""
        bekannt = {w.lower() for w in self.woerter}
        neu = [sauber(w) for w in woerter if sauber(w) and sauber(w).lower() not in bekannt]
        self.woerter = Woerterbuch(woerter=[*self.woerter, *neu]).woerter
        self.geaendert_am = jetzt()
        return neu


def hinweis(stil: str, woerter: list[str]) -> str:
    """Der Hinweis an den Hördienst: der Stilsatz (Schreibweise mit Satzzeichen) und die Fachwörter."""
    teile = [stil.strip()] if stil.strip() else []
    if woerter:
        teile.append(f"Fachwörter: {', '.join(woerter)}.")
    return " ".join(teile)
