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
  erzeugt_mit?: { dienst: string; modell: string | null; app: string } | null;
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
