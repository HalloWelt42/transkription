"""Hörabschnitte planen aus dem, was die Tonarbeit liefert (hier mit `TonHier` gerechnet, im Betrieb im Tondienst auf
dem Mac; dessen eigene Tests prüfen Wandeln und Formate). Auf dem Pi bleibt nur der Ausschnitt als Bytekopie."""

import asyncio
from pathlib import Path

import pytest

from appkern.ton import HOEREN, Aufbereiten, Ausgabe, Messen, Pause, PausenWahl, TonFehler, TonHier, programm
from appkern.ton.wav import ausschnitt, dauer

from app.ton import Abschnitt, abschnitte_planen


async def erzeugen(ziel: Path, *argumente: str) -> Path:
    p = await asyncio.create_subprocess_exec(programm("ffmpeg"), "-nostdin", "-loglevel", "error", "-y", *argumente, str(ziel))
    assert await p.wait() == 0
    return ziel


@pytest.fixture
async def mit_pausen(tmp_path: Path) -> Path:
    """20 s: je 3 s Ton, 1 s Stille, als Stereo-MP3 mit 44,1 kHz."""
    return await erzeugen(tmp_path / "probe.mp3", "-f", "lavfi", "-i",
                          "aevalsrc='if(lt(mod(t,4),3),0.5*sin(2*PI*440*t),0)|if(lt(mod(t,4),3),0.5*sin(2*PI*440*t),0)':s=44100:d=20")


async def test_aufbereiten_pausen_abschnitte_ausschnitt(mit_pausen: Path, tmp_path: Path):
    wav = tmp_path / "probe.wav"
    erg = await TonHier().aufbereiten(mit_pausen, Aufbereiten(ausgaben=[Ausgabe(format=HOEREN)],
                                                              messen=Messen(pausen=PausenWahl(), wellenform=40)), [wav])
    assert wav.read_bytes()[:4] == b"RIFF" and dauer(wav) == pytest.approx(20.0, abs=0.1)
    pausen = erg.messwerte.pausen
    assert len(pausen) >= 4 and all(0.8 < p.laenge < 1.2 for p in pausen[:4])
    assert pausen[0].start == pytest.approx(3.0, abs=0.1)
    abschnitte = abschnitte_planen(dauer(wav), pausen, hoechstens_s=7, mindestens_s=2)
    # Pausen alle 4 s, höchstens 7 s: geschnitten wird je in der Mitte der Pause
    assert [a.ende for a in abschnitte] == pytest.approx([3.5, 7.5, 11.5, 15.5, 20.0], abs=0.1)
    stueck = ausschnitt(wav, abschnitte[1].start, abschnitte[1].ende, tmp_path / "stueck.wav")
    assert dauer(stueck) == pytest.approx(abschnitte[1].ende - abschnitte[1].start, abs=0.001)
    welle = erg.messwerte.wellenform
    # fester Maßstab in Dezibel: der Prüfton (halbe Aussteuerung, -6 dB) steht bei etwa 90, Pausen sind leer
    assert len(welle) == 40 and max(welle) == pytest.approx(90, abs=4) and min(welle) < 20
    assert sum(w > 80 for w in welle) >= 25                                 # der Ton (440 Hz) bleibt erhalten


async def test_video_nur_tonspur(tmp_path: Path):
    video = await erzeugen(tmp_path / "v.mp4", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=2",
                           "-f", "lavfi", "-i", "sine=f=300:d=2", "-shortest", "-c:v", "libx264", "-c:a", "aac")
    wav = await TonHier().wandeln(video, tmp_path / "v.wav", HOEREN)
    assert dauer(wav) == pytest.approx(2.0, abs=0.15)


async def test_kaputte_datei(tmp_path: Path):
    kaputt = tmp_path / "kaputt.wav"
    kaputt.write_bytes(b"kein Ton")
    with pytest.raises(TonFehler):
        await TonHier().wandeln(kaputt, tmp_path / "x.wav", HOEREN)
    with pytest.raises(TonFehler):
        dauer(kaputt)


def test_planen_ohne_pausen_und_kurz():
    assert abschnitte_planen(0, []) == []
    assert abschnitte_planen(300, []) == [Abschnitt(1, 0.0, 300.0)]
    hart = abschnitte_planen(1500, [], hoechstens_s=600)
    assert [(a.start, a.ende) for a in hart] == [(0.0, 600.0), (600.0, 1200.0), (1200.0, 1500.0)]
    # lieber die längere Pause im späten Fenster als die letzte kurze
    pausen = [Pause(start=400, ende=400.5), Pause(start=500, ende=503), Pause(start=590, ende=590.4)]
    assert abschnitte_planen(1000, pausen, hoechstens_s=600)[0].ende == 501.5
