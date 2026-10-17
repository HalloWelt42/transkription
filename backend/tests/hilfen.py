"""Gemeinsames der Tests: Werte aus `backend/.env.test` (nicht im Repo) für die Verbundtests."""

import os
from pathlib import Path

from appkern.kellerwolke import Kellerwolke


def werte() -> dict[str, str]:
    alle = dict(os.environ)
    datei = Path(__file__).resolve().parents[1] / ".env.test"
    if datei.is_file():
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            k, _, w = zeile.partition("=")
            alle.setdefault(k.strip(), w.strip())
    return alle


W = werte()
HAT_KELLERWOLKE = bool(W.get("KELLERWOLKE_ADRESSE") and W.get("KELLERWOLKE_SCHLUESSEL"))


async def aktionen_zurueckziehen() -> None:
    """Am Ende eines Laufs mit gestarteter App: die Aktionen des Testzugangs zurückziehen, damit das Dateimenü der
    Kellerwolke nur die Aktionen echter Apps zeigt (eine App selbst zieht beim Beenden nichts zurück, Anfragen warten)."""
    kw = Kellerwolke(W["KELLERWOLKE_ADRESSE"], W["KELLERWOLKE_SCHLUESSEL"])
    try:
        await kw.aktionen_melden([])
    finally:
        await kw.schliessen()
