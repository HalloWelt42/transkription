"""Abgleich des Suchindex mit den Transkripten im Zweig der App in der Kellerwolke (Begleiter des Gerüsts).

Beim Verbinden einmal vollständig (nur geänderte Dateien werden gelesen), danach über den Ereignisstrom der
Kellerwolke: neue, geänderte, verschobene und gelöschte Transkripte kommen von selbst in den Index, auch wenn sie
außerhalb der App geändert wurden (etwa eine Version in der Kellerwolke zurückgeholt). Reicht das Journal nicht mehr
zurück, gleicht er wieder vollständig ab. Fehler stehen im Log; nach einer Pause beginnt er neu.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from appkern.app import Begleiter, Geruest
from appkern.kellerwolke import Knoten, KellerwolkeFehler, NichtGefunden

from .ablage import orte
from .ablage.transkripte import KeineKellerwolke, Transkripte, Unlesbar
from .suchindex import Suchindex

logger = logging.getLogger("transkription.abgleich")
PAUSE_S = 30.0


class Abgleich(Begleiter):
    def __init__(self, geruest: Geruest, transkripte: Transkripte, index: Suchindex) -> None:
        self.geruest = geruest
        self.transkripte = transkripte
        self.index = index
        self._aufgabe: asyncio.Task | None = None
        self.bereit = asyncio.Event()   # nach dem ersten vollständigen Abgleich (für Tests und die Anzeige)

    async def verbunden(self) -> None:
        await self.stoppen()
        self.bereit.clear()
        if self.geruest.kellerwolke is not None:
            self._aufgabe = asyncio.create_task(self._laufen(), name="abgleich")

    async def stoppen(self) -> None:
        if self._aufgabe is not None:
            self._aufgabe.cancel()
            await asyncio.gather(self._aufgabe, return_exceptions=True)
            self._aufgabe = None

    async def _laufen(self) -> None:
        while True:
            try:
                await self._folgen()
            except asyncio.CancelledError:
                raise
            except (KellerwolkeFehler, KeineKellerwolke) as f:
                logger.warning("Abgleich mit der Kellerwolke unterbrochen: %s", f)
            except Exception:  # noqa: BLE001 - der Abgleich darf die App nie anhalten
                logger.exception("Abgleich")
            await asyncio.sleep(PAUSE_S)

    async def _folgen(self) -> None:
        ordner = await self.transkripte.zweig()
        seit = await self.index.abgleich_seit(ordner.id)
        if seit == 0:
            seit = await self._journal_ende(ordner.id)      # erst die Stelle merken, dann lesen: nichts geht verloren
            await self.vollstaendig()
            await self.index.abgleich_merken(ordner.id, seit)
        self.bereit.set()
        async for stand in self.transkripte.kw.beobachten(ordner.id, seit):
            if stand.luecke:
                await self.vollstaendig()
            else:
                for knoten_id in dict.fromkeys(e.knoten_id for e in stand.eintraege):
                    await self.nachlesen(knoten_id, ordner)
            await self.index.abgleich_merken(ordner.id, stand.bis)

    async def _journal_ende(self, ordner_id: UUID) -> int:
        seit = 0
        while True:
            stand = await self.transkripte.kw.aenderungen(ordner_id, seit, 500)
            seit = stand.bis
            if len(stand.eintraege) < 500:
                return seit

    async def vollstaendig(self) -> None:
        """Alle Transkripte im Ordner; nur Dateien mit anderem Stand werden gelesen, Verschwundene entfernt."""
        bekannt = await self.index.staende()
        gesehen: set[str] = set()
        async for k in self.transkripte.alle():
            gesehen.add(str(k.id))
            if bekannt.get(str(k.id)) != k.etag:
                await self._eintragen(k.id)
        for tid in set(bekannt) - gesehen:
            await self.index.entfernen(tid)

    async def nachlesen(self, knoten_id: UUID, ordner: Knoten) -> None:
        """Eine geänderte Stelle: liegt dort (noch) ein Transkript irgendwo im Zweig der App, kommt es in den Index,
        sonst heraus."""
        try:
            knoten = await self.transkripte.kw.knoten(knoten_id)
        except NichtGefunden:
            await self.index.entfernen(knoten_id)
            return
        if not knoten.pfad.startswith(ordner.pfad + "/") or not orte.ist_transkript(knoten):
            await self.index.entfernen(knoten_id)
            return
        if (await self.index.staende()).get(str(knoten_id)) != knoten.etag:
            await self._eintragen(knoten_id)

    async def _eintragen(self, knoten_id: UUID) -> None:
        try:
            t, knoten = await self.transkripte.lesen(knoten_id)
        except NichtGefunden:
            await self.index.entfernen(knoten_id)
            return
        except Unlesbar as f:
            logger.warning("Transkript %s bleibt aus dem Index: %s", knoten_id, f)
            return
        await self.index.eintragen(t, knoten)
