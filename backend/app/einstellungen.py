"""Einstellungen von Transkription. Kellerwolke, Leitstelle und weitere Konten bringt das Gerüst mit; hier kommen die
der Transkription dazu. Die Seite Einstellungen der Oberfläche entsteht daraus von selbst. Was das System kennt
(Dienste und Modelle der Leitstelle), kommt als Auswahl (siehe `teile.Teile.angebote`), nicht als Textfeld. Ton wird
hier nie gerechnet: Wandeln, Pausen und Wellenform macht der Tondienst auf dem Mac (der Pi liefert nur Daten)."""

from typing import Literal

from pydantic import Field, SecretStr

from appkern.app import Grundeinstellungen

from .sprachen import Sprache

HOEREN = {"gruppe": "Hören"}
SPRECHER = {"gruppe": "Sprecher"}
KI = {"gruppe": "KI"}
TECHNIK = {"gruppe": "Technik"}
ALTBESTAND = {"gruppe": "Altbestand"}

SprecherWeg = Literal["ohne", "stimmen", "trennung"]
SPRECHER_WEGE = {"ohne": "Ohne Sprecher", "stimmen": "Stimmen gruppieren", "trennung": "Mit Sprechertrennung"}


class AppEinstellungen(Grundeinstellungen):
    sprache: Sprache = Field("de", title="Sprache", json_schema_extra=HOEREN,
                             description="In welcher Sprache gesprochen wird; Vorgabe für neue Aufträge, je Auftrag änderbar. "
                                         "Zur Wahl steht, was der Hördienst kann; Erkennen lässt ihn entscheiden.")
    abschnitt_min: int = Field(10, ge=2, le=30, title="Abschnittslänge", json_schema_extra={**HOEREN, "einheit": "Minuten"},
                               description="Lange Aufnahmen gehen in Abschnitten dieser Länge an den Hördienst, geschnitten in "
                                           "Sprechpausen. Nach einem Abbruch geht es beim nächsten Abschnitt weiter.")
    dienst_hoeren: str = Field("klangwerk-hoeren", title="Dienst zum Hören", json_schema_extra=HOEREN,
                               description="Macht aus Ton Text mit Wortzeiten. Zur Wahl steht, was die Leitstelle dieser App "
                                           "anbietet.")
    dienst_ton: str = Field("klangwerk-ton", title="Tondienst", json_schema_extra=HOEREN,
                            description="Wandelt jede Aufnahme für Hören und Abspielen, findet Sprechpausen und Wellenform. "
                                        "Gerechnet wird auf dem Mac, nie hier.")

    sprecher_weg: SprecherWeg = Field("ohne", title="Sprecher beim Transkribieren",
                                      json_schema_extra={**SPRECHER, "beschriftungen": SPRECHER_WEGE},
                                      description="Vorgabe für die Wahl je Aufnahme. Ab Werk ohne: die automatische Zuordnung "
                                                  "ist nicht bei jeder Aufnahme sauber. Sprecher erkennen oder von Hand zuordnen "
                                                  "geht jederzeit später am Transkript.")
    dienst_sprecher: str = Field("klangwerk-sprecher", title="Dienst für Stimmabdrücke", json_schema_extra=SPRECHER,
                                 description="Liefert je Stelle einen Stimmabdruck; damit werden Stimmen gruppiert und mit den "
                                             "Profilen verglichen.")
    dienst_trennen: str = Field("klangwerk-trennen", title="Dienst für die Sprechertrennung", json_schema_extra=SPRECHER,
                                description="Sagt, wer wann spricht.")
    trennen_zugang: SecretStr = Field(SecretStr(""), title="Zugang zum Modell der Sprechertrennung", json_schema_extra=SPRECHER,
                                      description="Nur nötig, wenn der Dienst meldet, dass ihm der Zugang zu seinem Modell fehlt. "
                                                  "Sonst leer lassen.")
    sprecher_sicher: int = Field(70, ge=30, le=99, title="Profil sicher ab",
                                 json_schema_extra={**SPRECHER, "schritt": 5, "einheit": "% Ähnlichkeit"},
                                 description="Ab dieser Ähnlichkeit zu einem Profil bekommt ein Sprecher dessen Namen von selbst.")
    sprecher_vorschlag: int = Field(50, ge=20, le=95, title="Profil vorschlagen ab",
                                    json_schema_extra={**SPRECHER, "schritt": 5, "einheit": "% Ähnlichkeit"},
                                    description="Ab dieser Ähnlichkeit wird ein Profil zum Bestätigen vorgeschlagen.")
    sprecher_zusammenlegen: int = Field(60, ge=30, le=99, title="Stimmen zusammenlegen ab",
                                        json_schema_extra={**SPRECHER, "schritt": 5, "einheit": "% Ähnlichkeit"},
                                        description="Zwei erkannte Sprecher mit so ähnlichen Stimmen werden einer.")

    ki_modell: str = Field("qwen/qwen3-next-80b", title="Sprachmodell", json_schema_extra=KI,
                           description="Für Korrektur und Auswertung. Die App wählt das Modell, nie die Leitstelle; zur Wahl "
                                       "steht, was die Leitstelle dieser App für Text anbietet.")

    abspiel_speicher_gb: int = Field(20, ge=1, le=500, title="Speicher für Abspielfassungen",
                                     json_schema_extra={**TECHNIK, "einheit": "GB"},
                                     description="Der Spieler nutzt eine gewandelte Fassung jeder Aufnahme (dadurch ohne Versatz "
                                                 "zum Text). Wird es mehr, gehen die am längsten nicht gespielten zuerst; sie "
                                                 "entstehen bei Bedarf neu.")
    altbestand_adresse: str = Field("", title="Alte App", json_schema_extra=ALTBESTAND,
                                    description="Die alte Sprachwerkstatt im Heimnetz, aus der du einzelne eigene Aufnahmen "
                                                "samt Transkripten von Hand übernimmst. Leer: kein Altbestand.")
