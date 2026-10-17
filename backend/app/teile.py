"""Die fachlichen Teile der Transkription, einmal verdrahtet: Ablage, Index, Vorschläge, Dienste, Ton. Aufträge und
Schnittstelle bekommen dieses eine Objekt statt vieler einzelner Abhängigkeiten."""

from __future__ import annotations

from pathlib import Path

from appkern.app import Begleiter, Geruest

from .ablage.profile import Sprecherprofile
from .ablage.transkripte import Transkripte
from .abgleich import Abgleich
from .dienste import Klangwerk
from .einstellungen import AppEinstellungen
from .sprechererkennung import Schwellen
from .suchindex import Suchindex
from .ton import Ton
from .vorschlaege import Vorschlaege


class Teile(Begleiter):
    def __init__(self, geruest: Geruest[AppEinstellungen]) -> None:
        self.geruest = geruest
        self.transkripte = Transkripte(lambda: geruest.kellerwolke)
        self.profile = Sprecherprofile(lambda: geruest.kellerwolke)
        self.index = Suchindex(geruest.db)
        self.vorschlaege = Vorschlaege(geruest.db)
        self.abgleich = Abgleich(geruest, self.transkripte, self.index)
        e = lambda: geruest.einstellungen.stand  # noqa: E731
        self.klangwerk = Klangwerk(lambda: geruest.leitstelle,
                                   lambda: (e().dienst_hoeren, e().dienst_sprecher, e().dienst_trennen))

    @property
    def einstellungen(self) -> AppEinstellungen:
        return self.geruest.einstellungen.stand

    @property
    def ton(self) -> Ton:
        return Ton(self.einstellungen.ffmpeg_ordner)

    @property
    def schwellen(self) -> Schwellen:
        e = self.einstellungen
        return Schwellen(gruppieren=e.sprecher_zusammenlegen, zusammenlegen=e.sprecher_zusammenlegen,
                         sicher=e.sprecher_sicher, vorschlag=e.sprecher_vorschlag)

    @property
    def arbeit(self) -> Path:
        """Ordner für Zwischendateien der Aufträge (je Auftrag ein Unterordner, danach gelöscht)."""
        return self.geruest.daten / "arbeit"

    async def starten(self) -> None:
        await self.index.einrichten()
        await self.vorschlaege.einrichten()
