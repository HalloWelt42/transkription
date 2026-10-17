"""Verzeichnis und Suchindex der Transkripte in der SQLite-Datei der App. Nur ein Abbild der Dateien in der
Kellerwolke: jederzeit aus ihnen neu aufbaubar (siehe `abgleich`).

Gesucht wird im Text der Segmente und in den Titeln der Marker, als Teilwort (Trigramm-Index: "kosten" findet auch
"Nebenkostenabrechnung"), Groß- und Kleinschreibung egal. Begriffe unter drei Zeichen gehen den langsameren Weg über
LIKE. Die Liste ist seitenweise; je Transkript kommen die Zahl der Treffer und die ersten Fundstellen mit Zeit.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from appkern.datenbank import Datenbank
from appkern.kellerwolke import Knoten

from .modell.transkript import Transkript

BAUSTEIN = "transkription"
STUFEN = [
    """
    CREATE TABLE transkript (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        pfad TEXT NOT NULL,
        stand TEXT,
        quelle_id TEXT,
        quelle_pfad TEXT,
        sprache TEXT NOT NULL,
        dauer_s REAL NOT NULL,
        segmente INTEGER NOT NULL,
        sprecher TEXT NOT NULL,
        erstellt_am TEXT NOT NULL,
        geaendert_am TEXT NOT NULL
    );
    CREATE INDEX transkript_quelle ON transkript (quelle_id);
    CREATE INDEX transkript_geaendert ON transkript (geaendert_am DESC);
    CREATE TABLE transkript_sprecher (
        transkript_id TEXT NOT NULL REFERENCES transkript (id) ON DELETE CASCADE,
        name TEXT NOT NULL COLLATE NOCASE,
        PRIMARY KEY (transkript_id, name)
    );
    CREATE VIRTUAL TABLE fundstelle USING fts5 (text, transkript_id UNINDEXED, zeit UNINDEXED, art UNINDEXED,
                                                 tokenize = 'trigram');
    CREATE TABLE version_notiz (
        transkript_id TEXT NOT NULL,
        version_id TEXT NOT NULL,
        was TEXT NOT NULL,
        wer TEXT,
        app TEXT,
        zeit TEXT NOT NULL,
        PRIMARY KEY (transkript_id, version_id)
    );
    CREATE TABLE abgleich (ordner_id TEXT PRIMARY KEY, seit INTEGER NOT NULL);
    """,
]
FUNDSTELLEN_JE_TRANSKRIPT = 3
_RAND = 60


class Fundstelle(BaseModel):
    zeit: float
    art: str = Field(description="text oder marker")
    ausschnitt: str


class Eintrag(BaseModel):
    id: UUID
    name: str
    pfad: str
    stand: str | None
    quelle_id: UUID | None
    quelle_pfad: str | None
    sprache: str
    dauer_s: float
    segmente: int
    sprecher: list[str]
    erstellt_am: datetime
    geaendert_am: datetime
    treffer: int = 0
    fundstellen: list[Fundstelle] = Field(default_factory=list)


class Seite(BaseModel):
    gesamt: int
    ab: int
    anzahl: int
    eintraege: list[Eintrag]


class Notiz(BaseModel):
    was: str
    wer: str | None = None
    app: str | None = None
    zeit: datetime


def ausschnitt(text: str, begriffe: list[str], rand: int = _RAND) -> str:
    """Stelle um den ersten Begriff herum, mit "..." an gekürzten Enden."""
    klein = text.lower()
    pos = min((p for p in (klein.find(b.lower()) for b in begriffe) if p >= 0), default=0)
    von, bis = max(0, pos - rand), min(len(text), pos + rand)
    if von > 0:
        luecke = text.find(" ", von, pos)
        von = luecke + 1 if luecke >= 0 else von
    if bis < len(text):
        luecke = text.rfind(" ", pos, bis)
        bis = luecke if luecke > pos else bis
    return f"{'... ' if von > 0 else ''}{text[von:bis].strip()}{' ...' if bis < len(text) else ''}"


def _like(begriff: str) -> str:
    return "%" + begriff.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _bedingung(begriffe: list[str]) -> tuple[str, list[str]]:
    """Bedingung auf `fundstelle` für alle Begriffe (UND)."""
    if all(len(b) >= 3 for b in begriffe):
        return "fundstelle MATCH ?", [" AND ".join('"' + b.replace('"', '""') + '"' for b in begriffe)]
    return " AND ".join("text LIKE ? ESCAPE '\\'" for _ in begriffe), [_like(b) for b in begriffe]


def _notiz(v: sqlite3.Connection, t: Transkript, knoten: Knoten) -> None:
    if t.aenderung is not None and knoten.etag:
        a = t.aenderung
        v.execute("INSERT OR REPLACE INTO version_notiz (transkript_id, version_id, was, wer, app, zeit) "
                  "VALUES (?,?,?,?,?,?)", (str(knoten.id), knoten.etag, a.was, a.wer, a.app, a.zeit.isoformat()))


class Suchindex:
    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def einrichten(self) -> None:
        await self.db.einrichten(BAUSTEIN, STUFEN)

    # --- Schreiben --------------------------------------------------------------------------------------------

    async def eintragen(self, t: Transkript, knoten: Knoten) -> None:
        """Ein Transkript (neu oder geändert) samt Fundstellen und der Notiz seiner Version."""
        tid = str(knoten.id)
        namen = [s.name for s in t.sprecher]

        def arbeit(v: sqlite3.Connection) -> None:
            v.execute(
                "INSERT INTO transkript (id, name, pfad, stand, quelle_id, quelle_pfad, sprache, dauer_s, segmente, "
                "sprecher, erstellt_am, geaendert_am) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, pfad=excluded.pfad, stand=excluded.stand, quelle_id=excluded.quelle_id, "
                "quelle_pfad=excluded.quelle_pfad, sprache=excluded.sprache, dauer_s=excluded.dauer_s, "
                "segmente=excluded.segmente, sprecher=excluded.sprecher, erstellt_am=excluded.erstellt_am, "
                "geaendert_am=excluded.geaendert_am",
                (tid, t.name, knoten.pfad, knoten.etag, str(t.quelle.knoten_id) if t.quelle else None,
                 t.quelle.pfad if t.quelle else None, t.sprache, t.dauer_s, len(t.segmente), json.dumps(namen),
                 t.erstellt_am.isoformat(), t.geaendert_am.isoformat()))
            v.execute("DELETE FROM transkript_sprecher WHERE transkript_id=?", (tid,))
            v.executemany("INSERT OR IGNORE INTO transkript_sprecher (transkript_id, name) VALUES (?,?)",
                          [(tid, n) for n in namen])
            v.execute("DELETE FROM fundstelle WHERE transkript_id=?", (tid,))
            v.executemany("INSERT INTO fundstelle (text, transkript_id, zeit, art) VALUES (?,?,?,?)",
                          [(s.text, tid, s.start, "text") for s in t.segmente if s.text.strip()]
                          + [(m.titel, tid, m.zeit, "marker") for m in t.marker])
            _notiz(v, t, knoten)

        await self.db.transaktion(arbeit)

    async def notiz_merken(self, t: Transkript, knoten: Knoten) -> None:
        """Nur die Notiz zur neuen Version (was, wer), für Transkripte außerhalb des eigenen Baums: sie stehen nicht im
        Verzeichnis, ihre Versionen sollen trotzdem sagen, was geschah."""
        await self.db.transaktion(lambda v: _notiz(v, t, knoten))

    async def entfernen(self, transkript_id: UUID | str) -> None:
        tid = str(transkript_id)

        def arbeit(v: sqlite3.Connection) -> None:
            v.execute("DELETE FROM fundstelle WHERE transkript_id=?", (tid,))
            v.execute("DELETE FROM version_notiz WHERE transkript_id=?", (tid,))
            v.execute("DELETE FROM transkript WHERE id=?", (tid,))

        await self.db.transaktion(arbeit)

    # --- Lesen ------------------------------------------------------------------------------------------------

    async def staende(self) -> dict[str, str | None]:
        return {z["id"]: z["stand"] for z in await self.db.zeilen("SELECT id, stand FROM transkript")}

    async def eintrag(self, transkript_id: UUID | str) -> Eintrag | None:
        z = await self.db.zeile("SELECT * FROM transkript WHERE id=?", (str(transkript_id),))
        return _eintrag(z) if z else None

    async def seite(self, *, suche: str = "", sprache: str | None = None, sprecher: list[str] | None = None,
                    ab: int = 0, anzahl: int = 20) -> Seite:
        begriffe = suche.split()
        bedingungen, werte = [], []
        if sprache:
            bedingungen.append("t.sprache = ?")
            werte.append(sprache)
        for name in sprecher or []:
            bedingungen.append("EXISTS (SELECT 1 FROM transkript_sprecher s WHERE s.transkript_id = t.id AND s.name = ?)")
            werte.append(name)
        treffer_sql = ""
        if begriffe:
            bed, bed_werte = _bedingung(begriffe)
            treffer_sql = f"JOIN (SELECT transkript_id, count(*) AS treffer FROM fundstelle WHERE {bed} GROUP BY transkript_id) f ON f.transkript_id = t.id"
            werte = bed_werte + werte
        wo = f"WHERE {' AND '.join(bedingungen)}" if bedingungen else ""
        auswahl = "t.*, f.treffer" if begriffe else "t.*, 0 AS treffer"
        basis = f"FROM transkript t {treffer_sql} {wo}"
        gesamt = (await self.db.zeile(f"SELECT count(*) AS n {basis}", werte))["n"]
        zeilen = await self.db.zeilen(f"SELECT {auswahl} {basis} ORDER BY t.geaendert_am DESC, t.id LIMIT ? OFFSET ?",
                                      [*werte, anzahl, ab])
        eintraege = [_eintrag(z) for z in zeilen]
        if begriffe:
            for e in eintraege:
                e.fundstellen = await self._fundstellen(str(e.id), begriffe)
        return Seite(gesamt=gesamt, ab=ab, anzahl=anzahl, eintraege=eintraege)

    async def _fundstellen(self, tid: str, begriffe: list[str]) -> list[Fundstelle]:
        bed, werte = _bedingung(begriffe)
        zeilen = await self.db.zeilen(
            f"SELECT text, zeit, art FROM fundstelle WHERE {bed} AND transkript_id = ? ORDER BY zeit LIMIT ?",
            [*werte, tid, FUNDSTELLEN_JE_TRANSKRIPT])
        return [Fundstelle(zeit=z["zeit"], art=z["art"], ausschnitt=ausschnitt(z["text"], begriffe)) for z in zeilen]

    async def zur_quelle(self, quelle_ids: list[str]) -> dict[str, list[Eintrag]]:
        """Transkripte je Aufnahme (für den Stand in der Liste der Aufnahmen)."""
        if not quelle_ids:
            return {}
        platz = ",".join("?" * len(quelle_ids))
        zeilen = await self.db.zeilen(f"SELECT *, 0 AS treffer FROM transkript WHERE quelle_id IN ({platz}) "
                                      "ORDER BY geaendert_am DESC", quelle_ids)
        aus: dict[str, list[Eintrag]] = {}
        for z in zeilen:
            aus.setdefault(z["quelle_id"], []).append(_eintrag(z))
        return aus

    async def sprecher_namen(self) -> list[str]:
        zeilen = await self.db.zeilen("SELECT name, count(*) AS n FROM transkript_sprecher GROUP BY name "
                                      "ORDER BY n DESC, name LIMIT 200")
        return [z["name"] for z in zeilen]

    async def notizen(self, transkript_id: UUID | str) -> dict[str, Notiz]:
        zeilen = await self.db.zeilen("SELECT * FROM version_notiz WHERE transkript_id=?", (str(transkript_id),))
        return {z["version_id"]: Notiz(was=z["was"], wer=z["wer"], app=z["app"], zeit=z["zeit"]) for z in zeilen}

    # --- Stand des Abgleichs ----------------------------------------------------------------------------------

    async def abgleich_seit(self, ordner_id: UUID | str) -> int:
        z = await self.db.zeile("SELECT seit FROM abgleich WHERE ordner_id=?", (str(ordner_id),))
        return z["seit"] if z else 0

    async def abgleich_merken(self, ordner_id: UUID | str, seit: int) -> None:
        await self.db.ausfuehren("INSERT INTO abgleich (ordner_id, seit) VALUES (?, ?) "
                                 "ON CONFLICT(ordner_id) DO UPDATE SET seit=excluded.seit", (str(ordner_id), seit))


def _eintrag(z: dict) -> Eintrag:
    return Eintrag(id=z["id"], name=z["name"], pfad=z["pfad"], stand=z["stand"], quelle_id=z["quelle_id"],
                   quelle_pfad=z["quelle_pfad"], sprache=z["sprache"], dauer_s=z["dauer_s"], segmente=z["segmente"],
                   sprecher=json.loads(z["sprecher"]), erstellt_am=z["erstellt_am"], geaendert_am=z["geaendert_am"],
                   treffer=z.get("treffer") or 0)
