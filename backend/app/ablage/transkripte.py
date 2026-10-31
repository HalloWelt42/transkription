"""Transkripte als Dateien in der Kellerwolke: je Aufnahme eines, als Begleitdatei neben ihr (Rolle transkript); neu
transkribiert wird eine neue Version (Entscheidung 17.10.2026). Lesen mit Stand, schreiben nur mit dem zuletzt
gelesenen Stand, Versionen lesen und zurückholen, in den Papierkorb legen.

Liegt die Aufnahme außerhalb der App (aus der Kellerwolke angefragt), arbeitet `fuer(zugang)` mit dem Zugang dieser
Anfrage: dann darf die App genau diese Aufnahme und ihre Begleiter, solange die Anfrage offen ist.

Der Stand ist der ETag der Datei in der Kellerwolke (er ist zugleich die Kennung der Version). Wer mit einem veralteten
Stand schreibt, bekommt `StandVeraltet` und muss neu lesen; so überschreibt niemand still die Arbeit eines anderen.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID

from pydantic import ValidationError

from appkern.kellerwolke import Kellerwolke, Knoten, Version

from ..modell.transkript import Aenderung, Transkript, gehoert_einfuegen, jetzt
from . import orte


class KeineKellerwolke(Exception):
    """Die App ist noch nicht mit einer Kellerwolke verbunden."""


class Unlesbar(Exception):
    """Die Datei ist kein lesbares Transkript (etwa von Hand oder von einer anderen App geändert)."""


def _transkript(inhalt: bytes, name: str) -> Transkript:
    try:
        return Transkript.model_validate_json(inhalt)
    except ValidationError as f:
        raise Unlesbar(f"{name} ist kein lesbares Transkript ({f.errors()[0]['msg']} bei "
                       f"{'.'.join(str(x) for x in f.errors()[0]['loc']) or 'Inhalt'})") from None


def zugang(liefern: Callable[[], Kellerwolke | None]) -> Kellerwolke:
    kw = liefern()
    if kw is None:
        raise KeineKellerwolke("Keine Kellerwolke eingerichtet")
    return kw


def aufnahme_id(t: Transkript, knoten: Knoten) -> UUID | None:
    """Die Aufnahme eines Transkripts: die Hauptdatei, deren Begleiter es ist (die Wahrheit, seit es eine Ablage gibt);
    sonst die Angabe in der Datei (frühere Ablage, Transkripte ohne Gruppe)."""
    return knoten.haupt_id or (t.quelle.knoten_id if t.quelle else None)


async def begleiter_ablegen(kw: Kellerwolke, haupt_id: UUID | str, rolle: str, zusatz: str, inhalt: bytes,
                            inhaltstyp: str) -> Knoten:
    """Begleiter einer Rolle neben die Aufnahme: neu, oder eine neue Version des vorhandenen."""
    vorhanden = next((b for b in await kw.begleiter(haupt_id) if b.rolle == rolle), None)
    return await kw.begleiter_schreiben(haupt_id, rolle, zusatz, inhalt, stand=vorhanden.etag if vorhanden else None,
                                        nur_neu=vorhanden is None, inhaltstyp=inhaltstyp)


def _inhalt(t: Transkript) -> bytes:
    return t.model_dump_json(indent=1, exclude_none=True).encode("utf-8")


class Transkripte:
    def __init__(self, kellerwolke: Callable[[], Kellerwolke | None]) -> None:
        """`kellerwolke` liefert den aktuellen Zugang (er wird nach geänderten Einstellungen neu gebaut)."""
        self._kw = kellerwolke

    @property
    def kw(self) -> Kellerwolke:
        return zugang(self._kw)

    def fuer(self, kw: Kellerwolke) -> Transkripte:
        """Dieselbe Ablage mit einem bestimmten Zugang (etwa dem einer Anfrage aus der Kellerwolke)."""
        return Transkripte(lambda: kw)

    async def ordner(self) -> Knoten:
        """Wurzel des einen Baums der App: Aufnahmen mit ihren Transkripten daneben."""
        kw = self.kw
        return await kw.ordner(orte.ort((await kw.ich()).zweig, orte.AUFNAHMEN))

    async def zweig(self) -> Knoten:
        """Der ganze Zweig der App; der Abgleich sieht so auch Transkripte, die noch in der früheren getrennten Ablage
        liegen (bis zum Zusammenführen)."""
        kw = self.kw
        return await kw.pfad((await kw.ich()).zweig)

    async def zur_quelle(self, quelle_id: UUID | str) -> Knoten | None:
        """Das Transkript einer Aufnahme (ihr Begleiter der Rolle transkript), sonst None."""
        return next((b for b in await self.kw.begleiter(quelle_id) if b.rolle == orte.ROLLE), None)

    async def speichern(self, t: Transkript, quelle: Knoten, aenderung: Aenderung,
                        erneut: Aenderung | None = None, hauptfassung: bool = False) -> tuple[Transkript, Knoten]:
        """Das Transkript einer Aufnahme: neu als Begleiter neben ihr (`aenderung`), oder eine neue Version des
        vorhandenen (`erneut`, sonst `aenderung`; Name und Anlagezeit bleiben, die bisherigen Stände bleiben Versionen).
        Stammt es von einem anderen Hördienst als die Hauptfassung, wird es dessen Fassung neben ihr, außer mit
        `hauptfassung` (siehe `gehoert_einfuegen`)."""
        kw = self.kw
        vorhanden = await self.zur_quelle(quelle.id)
        if vorhanden is not None:
            bisher = _transkript(await kw.lesen_ganz(vorhanden.id), vorhanden.name)
            t, haupt = gehoert_einfuegen(bisher, t, hauptfassung)
            t = t.model_copy(update={"name": bisher.name, "erstellt_am": bisher.erstellt_am})
            aenderung = erneut or aenderung
            if not haupt:
                neu = t.fassungen[-1].erzeugt_mit
                aenderung = Aenderung(was=f"Fassung von {neu.modell or neu.dienst} ergänzt", wer=aenderung.wer,
                                      app=aenderung.app)
        t = t.model_copy(update={"geaendert_am": jetzt(), "aenderung": aenderung})
        knoten = await kw.begleiter_schreiben(quelle.id, orte.ROLLE, orte.ENDUNG, _inhalt(t),
                                              stand=vorhanden.etag if vorhanden else None, nur_neu=vorhanden is None,
                                              inhaltstyp=orte.INHALTSTYP)
        return t, knoten

    async def lesen(self, transkript_id: UUID | str) -> tuple[Transkript, Knoten]:
        kw = self.kw
        knoten = await kw.knoten(transkript_id)
        return _transkript(await kw.lesen_ganz(transkript_id), knoten.name), knoten

    async def schreiben(self, transkript_id: UUID | str, t: Transkript, stand: str,
                        aenderung: Aenderung) -> tuple[Transkript, Knoten]:
        """Neue Version mit dem zuletzt gelesenen Stand (sonst `StandVeraltet`); liefert sie so, wie sie gespeichert ist."""
        t = t.model_copy(update={"geaendert_am": jetzt(), "aenderung": aenderung})
        return t, await self.kw.neue_version(transkript_id, _inhalt(t), stand=stand, inhaltstyp=orte.INHALTSTYP)

    async def versionen(self, transkript_id: UUID | str) -> list[Version]:
        return await self.kw.versionen(transkript_id)

    async def version(self, transkript_id: UUID | str, version_id: UUID | str) -> Transkript:
        return _transkript(await self.kw.version_ganz(transkript_id, version_id), "Diese Version")

    async def zurueckholen(self, transkript_id: UUID | str, version_id: UUID | str, stand: str, wer: str | None,
                           app: str | None = None) -> tuple[Transkript, Knoten]:
        alt = await self.version(transkript_id, version_id)
        was = f"Fassung vom {alt.geaendert_am:%d.%m.%Y %H:%M} zurückgeholt"
        return await self.schreiben(transkript_id, alt, stand, Aenderung(was=was, wer=wer, app=app))

    async def loeschen(self, transkript_id: UUID | str) -> None:
        """In den Papierkorb der Kellerwolke; die Aufnahme bleibt."""
        await self.kw.loeschen(transkript_id)

    async def alle(self) -> AsyncIterator[Knoten]:
        """Alle Transkripte im Zweig der App, auch in Unterordnern (und in der früheren Ablage, bis sie zusammengeführt
        ist)."""
        kw = self.kw
        offen = [(await self.zweig()).id]
        while offen:
            async for k in kw.alle_kinder(offen.pop()):
                if k.ist_ordner:
                    offen.append(k.id)
                elif orte.ist_transkript(k):
                    yield k
