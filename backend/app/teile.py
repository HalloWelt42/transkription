"""Die fachlichen Teile der Transkription, einmal verdrahtet: Ablage, Index, Vorschläge, Dienste, Ton. Aufträge und
Schnittstelle bekommen dieses eine Objekt statt vieler einzelner Abhängigkeiten."""

from __future__ import annotations

from pathlib import Path

from appkern.app import Begleiter, Geruest
from appkern.einstellungen import Angebot, Option

from .ablage.profile import Sprecherprofile
from .ablage.transkripte import Transkripte
from .abgleich import Abgleich
from .dienste import Klangwerk
from .einstellungen import AppEinstellungen
from .sprechererkennung import Schwellen
from .suchindex import Suchindex
from .ton import Ton, TonFehler, programm
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
        self.angebote()

    @property
    def einstellungen(self) -> AppEinstellungen:
        return self.geruest.einstellungen.stand

    @property
    def ton(self) -> Ton:
        return Ton(self.einstellungen.ffmpeg_ordner)

    @property
    def schwellen(self) -> Schwellen:
        e = self.einstellungen
        return Schwellen(gruppieren=e.sprecher_zusammenlegen / 100, zusammenlegen=e.sprecher_zusammenlegen / 100,
                         sicher=e.sprecher_sicher / 100, vorschlag=e.sprecher_vorschlag / 100)

    @property
    def arbeit(self) -> Path:
        """Ordner für Zwischendateien der Aufträge (je Auftrag ein Unterordner, danach gelöscht)."""
        return self.geruest.daten / "arbeit"

    def angebote(self) -> None:
        """Auswahl aus dem System für die Einstellungen: Dienste und Modelle der Leitstelle, der Ort von ffmpeg."""
        g = self.geruest
        g.einstellungen.anbieten("dienst_hoeren", g.leitstelle_angebot("hoeren"))
        g.einstellungen.anbieten("dienst_sprecher", g.leitstelle_angebot("sprecher_erkennen"))
        g.einstellungen.anbieten("dienst_trennen", g.leitstelle_angebot("sprecher_trennen"))
        g.einstellungen.anbieten("ki_modell", g.leitstelle_angebot("text", leer="Kette der App in der Leitstelle"))

        async def ffmpeg() -> Angebot:
            optionen = [Option(wert="", titel="Automatisch finden", hinweis="Suchpfad und übliche Orte")]
            try:
                pfad = Path(programm("ffmpeg", self.einstellungen.ffmpeg_ordner))
            except TonFehler as f:
                return Angebot(optionen=optionen, stand=str(f))
            if str(pfad.parent) != self.einstellungen.ffmpeg_ordner:
                optionen.append(Option(wert=str(pfad.parent), titel=str(pfad.parent), hinweis="hier gefunden"))
            return Angebot(optionen=optionen, stand=f"gefunden: {pfad}")

        g.einstellungen.anbieten("ffmpeg_ordner", ffmpeg)

    async def starten(self) -> None:
        await self.index.einrichten()
        await self.vorschlaege.einrichten()
