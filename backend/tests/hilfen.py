"""Gemeinsames der Tests: Werte aus `backend/.env.test` (nicht im Repo) für die Verbundtests."""

import os
from pathlib import Path


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
