"""Einstellungen von Transkription. Kellerwolke, Leitstelle und weitere Konten bringt das Gerüst mit; hier kommen die
der Transkription dazu. Die Seite Einstellungen der Oberfläche entsteht daraus von selbst."""

from typing import Literal

from pydantic import Field, SecretStr

from appkern.app import Grundeinstellungen

HOEREN = {"gruppe": "Hören"}
SPRECHER = {"gruppe": "Sprecher"}
KI = {"gruppe": "KI"}
TECHNIK = {"gruppe": "Technik"}

SPRACHEN = {"de": "Deutsch", "en": "Englisch", "fr": "Französisch", "es": "Spanisch", "it": "Italienisch",
            "nl": "Niederländisch", "auto": "Erkennen"}
Sprache = Literal["de", "en", "fr", "es", "it", "nl", "auto"]


class AppEinstellungen(Grundeinstellungen):
    sprache: Sprache = Field("de", title="Sprache", json_schema_extra={**HOEREN, "beschriftungen": SPRACHEN},
                             description="Vorgabe beim Transkribieren; je Auftrag änderbar.")
    abschnitt_min: int = Field(10, ge=2, le=30, title="Abschnittslänge in Minuten", json_schema_extra=HOEREN,
                               description="Lange Aufnahmen gehen in Abschnitten dieser Länge (geschnitten in Sprechpausen) "
                                           "an den Hördienst; nach einem Abbruch geht es beim nächsten Abschnitt weiter.")
    dienst_hoeren: str = Field("klangwerk-hoeren", title="Hördienst", json_schema_extra=HOEREN,
                               description="Name des Dienstes in der Leitstelle, der Ton in Text mit Wortzeiten verwandelt.")

    sprecher_erkennen: bool = Field(True, title="Sprecher erkennen", json_schema_extra=SPRECHER,
                                    description="Vorgabe beim Transkribieren; je Auftrag änderbar.")
    dienst_sprecher: str = Field("klangwerk-sprecher", title="Dienst für Stimmabdrücke", json_schema_extra=SPRECHER,
                                 description="Name des Dienstes in der Leitstelle, der je Stelle einen Stimmabdruck liefert.")
    sprechertrennung: bool = Field(True, title="Sprechertrennung nutzen", json_schema_extra=SPRECHER,
                                   description="Erst die Sprechertrennung fragen, wer wann spricht; ohne sie (oder wenn "
                                               "sie fehlt) werden die Stimmabdrücke gruppiert.")
    dienst_trennen: str = Field("klangwerk-trennen", title="Dienst für die Sprechertrennung", json_schema_extra=SPRECHER,
                                description="Name des Dienstes in der Leitstelle.")
    trennen_zugang: SecretStr = Field(SecretStr(""), title="Zugang der Sprechertrennung", json_schema_extra=SPRECHER,
                                      description="Nur nötig, solange der Dienst noch ohne Zugang zu seinem Modell läuft.")
    sprecher_sicher: float = Field(0.70, ge=0.3, le=0.99, title="Profil sicher ab",
                                   json_schema_extra={**SPRECHER, "schritt": 0.05},
                                   description="Ab dieser Ähnlichkeit bekommt ein Sprecher Namen und Profil von selbst.")
    sprecher_vorschlag: float = Field(0.50, ge=0.2, le=0.95, title="Profil vorschlagen ab",
                                      json_schema_extra={**SPRECHER, "schritt": 0.05},
                                      description="Ab dieser Ähnlichkeit wird ein Profil zum Bestätigen vorgeschlagen.")
    sprecher_zusammenlegen: float = Field(0.60, ge=0.3, le=0.99, title="Sprecher zusammenlegen ab",
                                          json_schema_extra={**SPRECHER, "schritt": 0.05},
                                          description="Zwei erkannte Sprecher mit so ähnlichen Stimmen werden einer.")

    ki_modell: str = Field("", title="Sprachmodell", json_schema_extra=KI,
                           description="Für Korrektur und Auswertung; leer heißt: die Kette der App in der Leitstelle.")

    ffmpeg_ordner: str = Field("", title="Ordner von ffmpeg", json_schema_extra=TECHNIK,
                               description="Leer: im Suchpfad und an den üblichen Orten suchen.")
