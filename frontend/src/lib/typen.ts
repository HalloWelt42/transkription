// Was die Schnittstelle der Transkription liefert (Spiegel der Pydantic-Modelle im Backend).

export interface Wort {
  wort: string;
  start: number;
  ende: number;
  sicherheit?: number | null;
}

export interface Segment {
  start: number;
  ende: number;
  sprecher: string | null;
  text: string;
  woerter: Wort[];
}

export interface Sprecher {
  kennung: string;
  name: string;
  profil_id?: string | null;
  aehnlichkeit?: number | null;
  vorschlag_id?: string | null;
  vorschlag_aehnlichkeit?: number | null;
}

export type MarkerFarbe = "gelb" | "rot" | "gruen" | "blau" | "lila";

export interface Marker {
  id: string;
  zeit: number;
  titel: string;
  farbe: MarkerFarbe;
}

export interface Notiz {
  was: string;
  wer: string | null;
  app: string | null;
  zeit: string;
}

export interface Transkript {
  format: string;
  name: string;
  quelle: { knoten_id: string; pfad: string; etag: string | null } | null;
  sprache: string;
  dauer_s: number;
  erstellt_am: string;
  geaendert_am: string;
  sprecher: Sprecher[];
  segmente: Segment[];
  marker: Marker[];
  wellenform?: number[] | null;
  aenderung?: Notiz | null;
  erzeugt_mit?: ErzeugtMit | null;
  fassungen?: Hoerfassung[];
}

export interface ErzeugtMit {
  dienst: string;
  modell: string | null;
  app: string;
  hoeren_s?: number | null;       // Rechenzeit des Hördienstes für die ganze Aufnahme
}

// Dieselbe Aufnahme von einem anderen Hördienst gehört (zum Vergleich neben der Hauptfassung)
export interface Hoerfassung {
  id: string;
  erzeugt_mit: ErzeugtMit;
  erstellt_am: string;
  sprache: string;
  sprecher: Sprecher[];
  segmente: Segment[];
}

// Ein Hördienst der Leitstelle zur Wahl beim Transkribieren
export interface Hoerdienst {
  kennung: string;
  name: string;
  hinweis: string;
  vorgabe: boolean;
}

export interface TranskriptAntwort {
  id: string;
  pfad: string;
  stand: string;
  transkript: Transkript;
}

export interface Fundstelle {
  zeit: number;
  art: "text" | "marker";
  ausschnitt: string;
}

export interface Eintrag {
  id: string;
  name: string;
  pfad: string;
  stand: string | null;
  quelle_id: string | null;
  sprache: string;
  dauer_s: number;
  segmente: number;
  sprecher: string[];
  erstellt_am: string;
  geaendert_am: string;
  treffer: number;
  im_namen: boolean;          // der Name passt zur Suche
  fundstellen: Fundstelle[];
}

export interface Verzeichnis {
  gesamt: number;
  ab: number;
  anzahl: number;
  eintraege: Eintrag[];
}

export interface Ordner {
  id: string;
  name: string;
  pfad: string;
  recht: string;
  eigen: boolean;
}

export type AufnahmeStand = "ohne" | "wartet" | "laeuft" | "transkribiert";

export interface Aufnahme {
  id: string;
  name: string;
  pfad: string;
  art: "ton" | "video";
  groesse: number | null;
  inhaltstyp: string | null;
  dauer_s: number | null;
  geaendert_am: string;
  stand: AufnahmeStand;
  transkripte: { id: string; name: string }[];
  auftrag: { id: string; zustand: string; fortschritt: number | null; schritt: string; phase: string | null } | null;
  marker: { zeit: number; titel: string }[];
}

export interface AufnahmenSeite {
  ordner: Ordner;
  unterordner: Ordner[];
  gesamt: number;
  zahlen: { alle: number; ohne: number; transkribiert: number };
  eintraege: Aufnahme[];
}

export interface Version {
  id: string;
  groesse: number;
  erstellt_am: string;
  aktuell: boolean;
  notiz: Notiz | null;
}

export interface Vorschlag {
  id: string;
  start: number;
  alt: string;
  neu: string;
  auftrag_id: string | null;
}

export interface Probe {
  transkript_id: string;
  start: number;
  ende: number;
  text: string;
}

export interface Profil {
  id: string;
  name: string;
  proben: number;
  beispiele: Probe[];
  transkripte: number;
  erstellt_am: string;
  geaendert_am: string;
}

export type ExportFormat = "txt" | "md" | "srt" | "vtt" | "docx" | "json";
export type Vorlage = "protokoll" | "zusammenfassung" | "aufgaben";

// --- Altbestand der alten App ------------------------------------------------------------------------------------

export interface AltStand {
  id: string;
  erstellt_am: string;
  segmente: number;
  sprecher: number;
  mit_woertern: boolean;
}

export interface AltEintrag {
  schluessel: string;
  quelle: string;
  name: string;
  vorschlag: string;
  endung: string;
  groesse: number | null;
  dauer_s: number;
  staende: AltStand[];
  uebernommen: { aufnahme_id: string; pfad: string } | null;
  unvollstaendig: { aufnahme_id: string; pfad: string } | null;
  auftrag_id: string | null;
}

export interface AltbestandSeite {
  adresse: string;
  eintraege: AltEintrag[];
}

// Zusammenführen der früheren getrennten Ablage (Vorschau): was wohin kommt; nichts wird gelöscht.
export interface Umzugsschritt {
  art: "begleiter" | "daneben" | "ohne_aufnahme" | "ordner";
  knoten_id: string;
  von: string;
  nach: string;
  aufnahme_id: string | null;
}

export interface Umzugsplan {
  noetig: boolean;
  schritte: Umzugsschritt[];
  zahlen: Record<string, number>;
}

// Mitlesen beim Transkribieren (GET /transkribieren/<auftrag>/bisher)
export interface Bisher {
  zustand: string;
  phase: string | null;
  schritt: string;
  stuecke: { start: number; ende: number; text: string }[];
  abschnitte: number;          // 0: noch nicht geplant
  abschnitte_fertig: number;
  dauer_s: number | null;
  gehoert_bis_s: number;
  rest_s: number | null;       // geschätzte Sekunden, bis alles gehört ist; leer: noch keine Schätzung
  geschaetzt_aus: "" | "auftrag" | "frueher";
}

// Fachwörter-Wörterbuch (Hinweis an den Hördienst); ohne Änderungsdatum: noch der Startinhalt
export interface WoerterbuchStand {
  woerter: string[];
  geaendert_am: string | null;
}
