"""Tonvorbereitung mit dem echten ffmpeg: wandeln (auch aus Video), Dauer, Pausen, Abschnitte planen und ausschneiden."""

import asyncio
from pathlib import Path

import pytest

from app.ton import Abschnitt, Pause, Ton, TonFehler, abschnitte_planen, programm


async def erzeugen(ziel: Path, *argumente: str) -> Path:
    p = await asyncio.create_subprocess_exec(programm("ffmpeg"), "-nostdin", "-loglevel", "error", "-y", *argumente, str(ziel))
    assert await p.wait() == 0
    return ziel


@pytest.fixture
async def mit_pausen(tmp_path: Path) -> Path:
    """20 s: je 3 s Ton, 1 s Stille, als Stereo-MP3 mit 44,1 kHz."""
    return await erzeugen(tmp_path / "probe.mp3", "-f", "lavfi", "-i",
                          "aevalsrc='if(lt(mod(t,4),3),0.5*sin(2*PI*440*t),0)|if(lt(mod(t,4),3),0.5*sin(2*PI*440*t),0)':s=44100:d=20")


async def test_wandeln_dauer_pausen_ausschneiden(mit_pausen: Path, tmp_path: Path):
    ton = Ton()
    wav = await ton.wandeln(mit_pausen, tmp_path / "probe.wav")
    assert wav.read_bytes()[:4] == b"RIFF" and not list(tmp_path.glob(".*teil*"))
    assert await ton.dauer(wav) == pytest.approx(20.0, abs=0.1)
    pausen = await ton.pausen(wav)
    assert len(pausen) >= 4 and all(0.8 < p.laenge < 1.2 for p in pausen[:4])
    assert pausen[0].start == pytest.approx(3.0, abs=0.1)
    abschnitte = abschnitte_planen(await ton.dauer(wav), pausen, hoechstens_s=7, mindestens_s=2)
    # Pausen alle 4 s, höchstens 7 s: geschnitten wird je in der Mitte der Pause
    assert [a.ende for a in abschnitte] == pytest.approx([3.5, 7.5, 11.5, 15.5, 20.0], abs=0.1)
    stueck = await ton.ausschneiden(wav, abschnitte[1], tmp_path / "stueck.wav")
    assert await ton.dauer(stueck) == pytest.approx(abschnitte[1].ende - abschnitte[1].start, abs=0.05)
    welle = await ton.wellenform(wav, punkte=40)
    # fester Maßstab in Dezibel: der Prüfton (halbe Aussteuerung, -6 dB) steht bei etwa 90, Pausen sind leer
    assert len(welle) == 40 and max(welle) == pytest.approx(90, abs=4) and min(welle) < 20
    assert sum(w > 80 for w in welle) >= 25                                 # der Ton (440 Hz) bleibt erhalten
    flac = await ton.flac(wav, tmp_path / "ganz.flac")
    assert flac.stat().st_size < wav.stat().st_size


async def test_video_nur_tonspur(tmp_path: Path):
    video = await erzeugen(tmp_path / "v.mp4", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=2",
                           "-f", "lavfi", "-i", "sine=f=300:d=2", "-shortest", "-c:v", "libx264", "-c:a", "aac")
    wav = await Ton().wandeln(video, tmp_path / "v.wav")
    assert await Ton().dauer(wav) == pytest.approx(2.0, abs=0.15)


async def test_kaputte_datei(tmp_path: Path):
    kaputt = tmp_path / "kaputt.wav"
    kaputt.write_bytes(b"kein Ton")
    with pytest.raises(TonFehler):
        await Ton().wandeln(kaputt, tmp_path / "x.wav")
    with pytest.raises(TonFehler):
        programm("ffmpeg-gibt-es-nicht")


def test_planen_ohne_pausen_und_kurz():
    assert abschnitte_planen(0, []) == []
    assert abschnitte_planen(300, []) == [Abschnitt(1, 0.0, 300.0)]
    hart = abschnitte_planen(1500, [], hoechstens_s=600)
    assert [(a.start, a.ende) for a in hart] == [(0.0, 600.0), (600.0, 1200.0), (1200.0, 1500.0)]
    # lieber die längere Pause im späten Fenster als die letzte kurze
    pausen = [Pause(400, 400.5), Pause(500, 503), Pause(590, 590.4)]
    assert abschnitte_planen(1000, pausen, hoechstens_s=600)[0].ende == 501.5
