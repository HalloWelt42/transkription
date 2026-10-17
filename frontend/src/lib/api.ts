// Aufrufe der Schnittstelle der Transkription (über `hole` der Schale: Anmeldung, Fehler, Verbindungsstand).
import type { ErkennenWeg, SprecherWeg } from "./sprecherwahl";
import { hole, json, type Auftrag } from "appkern-oberflaeche";
import type {
  AufnahmenSeite, ExportFormat, Ordner, Profil, TranskriptAntwort, Verzeichnis, Version, Vorlage, Vorschlag,
  Marker, Segment, Transkript,
} from "./typen";

function abfrage(werte: Record<string, string | number | null | undefined | string[]>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(werte)) {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  }
  const text = p.toString();
  return text ? `?${text}` : "";
}

// --- Aufnahmen --------------------------------------------------------------------------------------------------

export const ordnerListe = () => hole<Ordner[]>("/aufnahmen/ordner");

export const aufnahmen = (o: { ordner?: string | null; filter?: string; suche?: string; ab?: number; anzahl?: number }) =>
  hole<AufnahmenSeite>(`/aufnahmen${abfrage(o)}`);

export const transkribieren = (e: { quelle_id: string; name?: string; sprache?: string; sprecher?: SprecherWeg; anzahl?: number | null }) =>
  hole<Auftrag>("/transkribieren", { method: "POST", ...json(e) });

// --- Transkripte ------------------------------------------------------------------------------------------------

export const verzeichnis = (o: { suche?: string; sprache?: string | null; sprecher?: string[]; ab?: number; anzahl?: number }) =>
  hole<Verzeichnis>(`/transkripte${abfrage(o)}`);

export const sprecherNamen = () => hole<string[]>("/transkripte/sprecher-namen");

export const ausMitschrift = (e: { quelle_id: string; name: string; sprache: string; stuecke: { start: number; ende: number; text: string }[] }) =>
  hole<TranskriptAntwort>("/transkripte", { method: "POST", ...json(e) });

export const transkript = (id: string) => hole<TranskriptAntwort>(`/transkripte/${id}`);

export interface Aenderungen {
  stand: string;
  name?: string;
  segmente?: Segment[];
  sprecher?: { kennung: string; name: string }[];
  marker?: Marker[];
  was?: string;
  vorschlaege?: { id: string; zustand: "uebernommen" | "verworfen" }[];
}

export const aendern = (id: string, a: Aenderungen) =>
  hole<TranskriptAntwort>(`/transkripte/${id}`, { method: "PATCH", ...json(a) });

export const loeschen = (id: string) => hole<void>(`/transkripte/${id}`, { method: "DELETE" });

export const versionen = (id: string) => hole<Version[]>(`/transkripte/${id}/versionen`);
export const version = (id: string, v: string) => hole<Transkript>(`/transkripte/${id}/versionen/${v}`);
export const zurueckholen = (id: string, v: string, stand: string) =>
  hole<TranskriptAntwort>(`/transkripte/${id}/versionen/${v}/zurueck`, { method: "POST", ...json({ stand }) });

export const exportAblegen = (id: string, format: ExportFormat) =>
  hole<{ id: string; pfad: string; name: string }>(`/transkripte/${id}/export`, { method: "POST", ...json({ format }) });

export const exportAdresse = (id: string, format: ExportFormat) => `/api/v1/inhalt/transkripte/${id}/export?format=${format}`;
export const tonAdresse = (id: string) => `/api/v1/inhalt/transkripte/${id}/ton`;
export const aufnahmeAdresse = (id: string) => `/api/v1/inhalt/aufnahmen/${id}`;

export const vorschlaege = (id: string) => hole<Vorschlag[]>(`/transkripte/${id}/vorschlaege`);

export const profilZuordnen = (id: string, kennung: string, z: { stand: string; profil_id?: string; name?: string }) =>
  hole<TranskriptAntwort>(`/transkripte/${id}/sprecher/${kennung}/profil`, { method: "POST", ...json(z) });

export const sprecherErkennen = (id: string, weg: ErkennenWeg, anzahl: number | null) =>
  hole<Auftrag>(`/transkripte/${id}/sprecher-erkennen`, { method: "POST", ...json({ weg, anzahl }) });
export const korrigieren = (id: string) => hole<Auftrag>(`/transkripte/${id}/korrigieren`, { method: "POST" });
export const auswerten = (id: string, vorlage: Vorlage) =>
  hole<Auftrag>(`/transkripte/${id}/auswerten`, { method: "POST", ...json({ vorlage }) });

// --- Sprecherprofile --------------------------------------------------------------------------------------------

export const profile = () => hole<Profil[]>("/sprecher");
export const profilUmbenennen = (id: string, name: string) => hole<Profil[]>(`/sprecher/${id}`, { method: "PATCH", ...json({ name }) });
export const profileZusammenfuehren = (ziel: string, quelle: string) =>
  hole<Profil[]>(`/sprecher/${ziel}/zusammenfuehren`, { method: "POST", ...json({ quelle_id: quelle }) });
export const profilLoeschen = (id: string) => hole<Profil[]>(`/sprecher/${id}`, { method: "DELETE" });

// --- Einstellungen (nur zum Anzeigen der Schwellen) -------------------------------------------------------------

export async function einstellung<T>(name: string): Promise<T | null> {
  try {
    const felder = await hole<{ name: string; wert: unknown }[]>("/einstellungen");
    return (felder.find((f) => f.name === name)?.wert as T) ?? null;
  } catch {
    return null;
  }
}
