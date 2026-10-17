"""Schnittstelle der Transkription unter /api/v1. Alles hinter der Anmeldung (Kellerwolke-Konto oder App-Schlüssel
einer anderen App); Inhalte für `<audio>` und Downloads unter /api/v1/inhalt auch mit dem Inhalts-Cookie."""

from fastapi import FastAPI

from ..teile import Teile
from . import aufnahmen, fehler, inhalt, sprecher, transkripte


def einbinden(app: FastAPI, teile: Teile) -> None:
    fehler.behandeln(app)
    for modul in (aufnahmen, transkripte, sprecher, inhalt):
        app.include_router(modul.router(teile))
