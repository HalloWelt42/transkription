"""KI-Auswertung eines Transkripts über die Leitstelle: aus einer Vorlage (Protokoll, Zusammenfassung, Aufgaben) wird
eine Markdown-Datei neben der Aufnahme (Begleiter mit der Vorlage als Rolle: `Runde.protokoll.md`). Grundlage ist der Markdown-Export mit Sprechern und
Zeiten; die KI soll nichts erfinden und die Namen der Sprecher verwenden."""

from __future__ import annotations

from typing import Literal

from appkern.leitstelle import Nachricht

Vorlage = Literal["protokoll", "zusammenfassung", "aufgaben"]

GEMEINSAM = ("Du wertest die Abschrift eines Gesprächs aus. Verwende nur, was in der Abschrift steht, erfinde nichts "
             "und nenne die Sprecher bei ihren Namen. Antworte auf Deutsch in Markdown, ohne Einleitung und ohne Schlusswort.")

VORLAGEN: dict[str, tuple[str, str]] = {
    "protokoll": ("Protokoll", GEMEINSAM + " Gliedere so: ## Zusammenfassung (drei bis sechs Sätze), ## Themen, "
                  "## Entscheidungen und Zusagen, ## Offene Punkte und Aufgaben (mit Zuständigen, falls genannt)."),
    "zusammenfassung": ("Zusammenfassung", GEMEINSAM + " Schreibe eine Zusammenfassung in fünf bis zehn Sätzen und "
                        "danach ## Kernaussagen als Liste."),
    "aufgaben": ("Aufgaben", GEMEINSAM + " Liste nur Aufgaben, Zusagen und Termine auf, je Zeile: Was, Wer, Bis wann "
                 "(soweit genannt), mit der Zeitmarke der Stelle in eckigen Klammern."),
}


def titel(vorlage: Vorlage) -> str:
    return VORLAGEN[vorlage][0]


def anfrage(vorlage: Vorlage, markdown: str) -> list[Nachricht]:
    return [Nachricht.system(VORLAGEN[vorlage][1]), Nachricht.nutzer(markdown)]


def dateiname(name: str, vorlage: Vorlage) -> str:
    """Nur für Transkripte ohne Aufnahme (Altbestand der früheren Ablage): Datei neben dem Transkript."""
    return f"{name} ({titel(vorlage)}).md"


def zusatz(vorlage: Vorlage) -> str:
    """Neben der Aufnahme: Stamm der Aufnahme und dieser Zusatz, die Vorlage ist die Rolle."""
    return f".{vorlage}.md"
