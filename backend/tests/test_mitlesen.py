"""Mitlesen beim Transkribieren: Text bis jetzt (lückenlos von vorn) und die Schätzung der Restzeit aus der Rechenzeit
je Sekunde Ton, erst aus früheren Aufträgen, dann aus dem eigenen."""

import json
from datetime import UTC, datetime, timedelta

from app.mitlesen import bisher_aus, rest_schaetzen

JETZT = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def stand(fertig: dict[int, float | None], beginn_vor_s: float | None = None) -> dict:
    """Drei Abschnitte zu 600 s; `fertig` je Nummer die Rechenzeit (None: ohne Messung, wie vor dieser Fassung)."""
    aus: dict = {"abschnitte": [[1, 0.0, 600.0], [2, 600.0, 1200.0], [3, 1200.0, 1800.0]], "dauer": 1800.0,
                 "hoeren": {str(n): {"segmente": [{"start": (n - 1) * 600 + 1, "ende": (n - 1) * 600 + 5, "text": f"Teil {n}"}],
                                     **({"gerechnet_s": r} if r else {})} for n, r in fertig.items()}}
    if beginn_vor_s is not None:
        aus["abschnitt_beginn"] = (JETZT - timedelta(seconds=beginn_vor_s)).isoformat()
    return aus


def test_schaetzung_aus_dem_eigenen_takt_abzueglich_des_laufenden_abschnitts():
    # 600 s Ton in 120 s gerechnet: offen 1200 s Ton sind 240 s, der laufende rechnet schon 30 s
    assert rest_schaetzen(stand({1: 120}, beginn_vor_s=30), JETZT) == (210.0, "auftrag")


def test_schaetzung_vor_dem_ersten_abschnitt_aus_frueheren_auftraegen_sonst_keine():
    assert rest_schaetzen(stand({}), JETZT) == (None, "")
    assert rest_schaetzen(stand({}), JETZT, frueher=(300.0, 1500.0)) == (360.0, "frueher")
    assert rest_schaetzen({}, JETZT, frueher=(300.0, 1500.0)) == (None, "")                 # noch kein Plan


def test_schaetzung_wird_nie_negativ_und_ist_am_ende_null():
    assert rest_schaetzen(stand({1: 60}, beginn_vor_s=3600), JETZT)[0] == 0.0
    assert rest_schaetzen(stand({1: 60, 2: 60, 3: 60}), JETZT) == (0.0, "auftrag")


def test_text_waechst_nur_lueckenlos_von_vorn():
    zeile = {"zustand": "laeuft", "phase": "hoeren", "schritt": "Abschnitt 2 von 3",
             "zwischenstand": json.dumps(stand({1: 100, 3: 100}))}
    b = bisher_aus(zeile, JETZT)
    assert [s.text for s in b.stuecke] == ["Teil 1"] and b.gehoert_bis_s == 600.0
    assert (b.abschnitte, b.abschnitte_fertig, b.dauer_s) == (3, 2, 1800.0)
    fertig = bisher_aus({**zeile, "zustand": "fertig"}, JETZT)
    assert fertig.rest_s is None                                                           # nur laufende schätzen
