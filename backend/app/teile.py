"""Die fachlichen Teile der Transkription, einmal verdrahtet: Ablage, Index, Vorschläge, Dienste, Ton. Aufträge und
Schnittstelle bekommen dieses eine Objekt statt vieler einzelner Abhängigkeiten."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import httpx

from appkern.app import Begleiter, Geruest
from appkern.einstellungen import Angebot, Option

from .ablage.profile import Sprecherprofile
from appkern.kellerwolke import Kellerwolke, Knoten

from .ablage.transkripte import Transkripte, zugang
from . import altbestand
from .abgleich import Abgleich
from .dienste import Klangwerk
from .einstellungen import AppEinstellungen
from .modell.transkript import Transkript
from .sprechererkennung import Schwellen
from .suchindex import Suchindex
from appkern.ton import Abspielfassungen, Ton, TonFehler, programm
from .vorschlaege import Vorschlaege


class Teile(Begleiter):
    def __init__(self, geruest: Geruest[AppEinstellungen]) -> None:
        self.geruest = geruest
        self.transkripte = Transkripte(lambda: geruest.kellerwolke)
        self.profile = Sprecherprofile(lambda: geruest.kellerwolke)
        self.index = Suchindex(geruest.db)
        self.vorschlaege = Vorschlaege(geruest.db)
        self.abgleich = Abgleich(geruest, self.transkripte, self.index)
        self.abspielen = Abspielfassungen(geruest.daten / "abspielen", lambda: self.ton,
                                          lambda: float(self.einstellungen.abspiel_speicher_gb))
        e = lambda: geruest.einstellungen.stand  # noqa: E731
        self.klangwerk = Klangwerk(lambda: geruest.leitstelle,
                                   lambda: (e().dienst_hoeren, e().dienst_sprecher, e().dienst_trennen))
        self.angebote()

    def zugang(self, anfrage: UUID | None = None) -> Kellerwolke:
        """Der Zugang zur Kellerwolke; mit einer Anfrage (Datei außerhalb der App, aus der Kellerwolke angefragt) der
        Zugang mit ihrem Recht: genau diese Datei und ihre Begleiter, solange die Anfrage offen ist."""
        kw = zugang(lambda: self.geruest.kellerwolke)
        return kw.mit_anfrage(anfrage) if anfrage else kw

    def transkripte_fuer(self, anfrage: UUID | None = None) -> Transkripte:
        return self.transkripte.fuer(self.zugang(anfrage)) if anfrage else self.transkripte

    async def geschrieben(self, t: Transkript, knoten: Knoten, anfrage: UUID | None = None) -> None:
        """Nach jedem Schreiben eines Transkripts: der eigene Baum steht im Verzeichnis der App (Liste, Suche); von
        Dateien aus der Kellerwolke (mit Anfrage) bleibt nur die Notiz zur Version."""
        if anfrage is None:
            await self.index.eintragen(t, knoten)
        else:
            await self.index.notiz_merken(t, knoten)

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

        async def alte_app() -> Angebot:
            """Sucht im Heimnetz (je /24 von Kellerwolke und Leitstelle) nach der alten App und zählt ihren Altbestand."""
            e = g.einstellungen.stand
            optionen = [Option(wert="", titel="Kein Altbestand")]
            async with httpx.AsyncClient() as client:
                gefunden = await altbestand.suchen([e.kellerwolke_adresse, e.leitstelle_adresse], client)
                for adresse in gefunden:
                    try:
                        zahl = len(await altbestand.AlteApp(adresse, client).aufnahmen())
                        hinweis = f"{zahl} eigene Aufnahmen"
                    except altbestand.AltFehler as f:
                        hinweis = str(f)
                    optionen.append(Option(wert=adresse, titel=f"Alte App auf {httpx.URL(adresse).host}", hinweis=hinweis))
            stand = f"gefunden: {', '.join(gefunden)}" if gefunden else "im Heimnetz nicht gefunden; eigene Adresse eintragen"
            return Angebot(optionen=optionen, eigener_wert=True, stand=stand)

        g.einstellungen.anbieten("altbestand_adresse", alte_app)

    async def transkript_wegraeumen(self, transkript_id: UUID | str, wer: str, anfrage: UUID | None = None) -> None:
        """In den Papierkorb der Kellerwolke, aus Verzeichnis und Vorschlägen, mit Eintrag im Protokoll."""
        eintrag = await self.index.eintrag(transkript_id)
        await self.transkripte_fuer(anfrage).loeschen(transkript_id)
        await self.index.entfernen(transkript_id)
        await self.vorschlaege.entfernen(transkript_id)
        await self.geruest.protokoll.eintragen("transkript.geloescht", f"{eintrag.name if eintrag else transkript_id} in den Papierkorb",
                                               bezug_art="transkript", bezug_name=wer)

    async def starten(self) -> None:
        await self.index.einrichten()
        await self.vorschlaege.einrichten()
