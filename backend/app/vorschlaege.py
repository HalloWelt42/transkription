"""Vorschläge der KI-Korrektur je Transkript (Zustand der App, keine Inhalte): offen, bis der Nutzer sie übernimmt
oder verwirft. Ein neuer Korrekturlauf ersetzt die noch offenen eines Transkripts."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from appkern.datenbank import Datenbank

from .korrektur import Vorschlag

BAUSTEIN = "vorschlaege"
STUFEN = [
    """
    CREATE TABLE vorschlag (
        id TEXT PRIMARY KEY,
        transkript_id TEXT NOT NULL,
        auftrag_id TEXT,
        start REAL NOT NULL,
        alt TEXT NOT NULL,
        neu TEXT NOT NULL,
        zustand TEXT NOT NULL DEFAULT 'offen' CHECK (zustand IN ('offen', 'uebernommen', 'verworfen')),
        erstellt_am TEXT NOT NULL
    );
    CREATE INDEX vorschlag_transkript ON vorschlag (transkript_id, zustand, start);
    """,
]
Entscheid = Literal["uebernommen", "verworfen"]


class OffenerVorschlag(Vorschlag):
    auftrag_id: str | None = None


class Entscheidung(BaseModel):
    id: UUID
    zustand: Entscheid


class Vorschlaege:
    def __init__(self, db: Datenbank) -> None:
        self.db = db

    async def einrichten(self) -> None:
        await self.db.einrichten(BAUSTEIN, STUFEN)

    async def ersetzen(self, transkript_id: UUID | str, auftrag_id: str, liste: list[Vorschlag]) -> None:
        jetzt = datetime.now(UTC).isoformat()

        def arbeit(v: sqlite3.Connection) -> None:
            v.execute("DELETE FROM vorschlag WHERE transkript_id=? AND zustand='offen'", (str(transkript_id),))
            v.executemany("INSERT INTO vorschlag (id, transkript_id, auftrag_id, start, alt, neu, erstellt_am) "
                          "VALUES (?,?,?,?,?,?,?)",
                          [(str(x.id), str(transkript_id), auftrag_id, x.start, x.alt, x.neu, jetzt) for x in liste])

        await self.db.transaktion(arbeit)

    async def offene(self, transkript_id: UUID | str) -> list[OffenerVorschlag]:
        zeilen = await self.db.zeilen("SELECT * FROM vorschlag WHERE transkript_id=? AND zustand='offen' ORDER BY start",
                                      (str(transkript_id),))
        return [OffenerVorschlag(id=z["id"], start=z["start"], alt=z["alt"], neu=z["neu"], auftrag_id=z["auftrag_id"])
                for z in zeilen]

    async def entscheiden(self, transkript_id: UUID | str, entscheidungen: list[Entscheidung]) -> None:
        def arbeit(v: sqlite3.Connection) -> None:
            v.executemany("UPDATE vorschlag SET zustand=? WHERE id=? AND transkript_id=? AND zustand='offen'",
                          [(e.zustand, str(e.id), str(transkript_id)) for e in entscheidungen])

        await self.db.transaktion(arbeit)

    async def entfernen(self, transkript_id: UUID | str) -> None:
        await self.db.ausfuehren("DELETE FROM vorschlag WHERE transkript_id=?", (str(transkript_id),))
