// Aufrufe der Schnittstelle der Transkription (über `hole` der Schale: Anmeldung, Fehler, Verbindungsstand).
import type { ErkennenWeg, SprecherWeg } from "./sprecherwahl";
import { hochladen, hole, json, type Auftrag, type Gespeichert } from "appkern-oberflaeche";
import type {
  AltbestandSeite, Aufnahme, Bisher, AufnahmenSeite, ExportFormat, Ordner, Profil, TranskriptAntwort, Verzeichnis, Version, Vorlage, Vorschlag,
  Hoerdienst, Marker, Segment, Transkript, Umzugsplan, WoerterbuchStand,
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

// Eine Datei aus der Kellerwolke (über eine Anfrage geöffnet): jeder Aufruf nennt die Anfrage, mit deren Recht die App
// liest und schreibt. Ohne Anfrage gilt der eigene Zweig der App.
export type AnfrageId = string | null | undefined;
function mit(pfad: string, anfrage: AnfrageId): string {
  return anfrage ? `${pfad}${pfad.includes("?") ? "&" : "?"}anfrage=${encodeURIComponent(anfrage)}` : pfad;
}

// --- Aufnahmen --------------------------------------------------------------------------------------------------

// Hochladen mit Fortschritt (Liste der laufenden: `uploads` aus dem Appkern)
export const aufnahmeHochladen = (daten: Blob, name: string) =>
  hochladen<Aufnahme>(`/api/v1/aufnahmen?name=${encodeURIComponent(name)}`, daten, name);

export const ordnerListe = () => hole<Ordner[]>("/aufnahmen/ordner");

export const aufnahmen = (o: { ordner?: string | null; filter?: string; suche?: string; ab?: number; anzahl?: number }) =>
  hole<AufnahmenSeite>(`/aufnahmen${abfrage(o)}`);

export const transkribieren = (e: { quelle_id: string; name?: string; sprache?: string; sprecher?: SprecherWeg; anzahl?: number | null;
                                    hoerdienst?: string | null }) =>
  hole<Auftrag>("/transkribieren", { method: "POST", ...json(e) });

// Sprachen zur Wahl: was der Hördienst (ohne Angabe der eingestellte) laut Steckbrief kann (mit "auto" zum Erkennen)
export const sprachen = (dienst?: string | null) => hole<{ code: string; name: string }[]>(`/sprachen${abfrage({ dienst })}`);

// Hördienste zur Wahl je Auftrag: was die Leitstelle dieser App anbietet, der eingestellte als Vorgabe
export const hoerdienste = () => hole<Hoerdienst[]>("/hoerdienste");

// Mitlesen: was ein laufender Auftrag schon gehört hat und wie lange er noch braucht
export const bisher = (auftrag: string) => hole<Bisher>(`/transkribieren/${encodeURIComponent(auftrag)}/bisher`);

// --- Transkripte ------------------------------------------------------------------------------------------------

export const verzeichnis = (o: { suche?: string; sprache?: string | null; sprecher?: string[]; ab?: number; anzahl?: number }) =>
  hole<Verzeichnis>(`/transkripte${abfrage(o)}`);

export const sprecherNamen = () => hole<string[]>("/transkripte/sprecher-namen");

export const ausMitschrift = (e: { quelle_id: string; name: string; sprache: string; stuecke: { start: number; ende: number; text: string }[] }) =>
  hole<TranskriptAntwort>("/transkripte", { method: "POST", ...json(e) });

export const transkript = (id: string, anfrage?: AnfrageId) => hole<TranskriptAntwort>(mit(`/transkripte/${id}`, anfrage));

export interface Aenderungen {
  stand: string;
  name?: string;
  segmente?: Segment[];
  sprecher?: { kennung: string; name: string }[];
  marker?: Marker[];
  was?: string;
  vorschlaege?: { id: string; zustand: "uebernommen" | "verworfen" }[];
}

export const aendern = (id: string, a: Aenderungen, anfrage?: AnfrageId) =>
  hole<TranskriptAntwort>(mit(`/transkripte/${id}`, anfrage), { method: "PATCH", ...json(a) });

export const loeschen = (id: string, anfrage?: AnfrageId) => hole<void>(mit(`/transkripte/${id}`, anfrage), { method: "DELETE" });

export const versionen = (id: string, anfrage?: AnfrageId) => hole<Version[]>(mit(`/transkripte/${id}/versionen`, anfrage));
export const version = (id: string, v: string, anfrage?: AnfrageId) =>
  hole<Transkript>(mit(`/transkripte/${id}/versionen/${v}`, anfrage));
export const zurueckholen = (id: string, v: string, stand: string, anfrage?: AnfrageId) =>
  hole<TranskriptAntwort>(mit(`/transkripte/${id}/versionen/${v}/zurueck`, anfrage), { method: "POST", ...json({ stand }) });

// Eine Fassung eines anderen Hördienstes wird Hauptfassung (Bearbeiten, Suche, Export); die bisherige bleibt daneben
export const hauptfassung = (id: string, fassung_id: string, stand: string, anfrage?: AnfrageId) =>
  hole<TranskriptAntwort>(mit(`/transkripte/${id}/hauptfassung`, anfrage), { method: "POST", ...json({ stand, fassung_id }) });

export const exportAblegen = (id: string, format: ExportFormat, anfrage?: AnfrageId) =>
  hole<{ id: string; pfad: string; name: string }>(mit(`/transkripte/${id}/export`, anfrage), { method: "POST", ...json({ format }) });

export const exportAdresse = (id: string, format: ExportFormat, anfrage?: AnfrageId) =>
  mit(`/api/v1/inhalt/transkripte/${id}/export?format=${format}`, anfrage);
export const aufnahme = (id: string, anfrage?: AnfrageId) => hole<Aufnahme>(mit(`/aufnahmen/${id}`, anfrage));
export const aufnahmeLoeschen = (id: string, mitTranskripten: boolean) =>
  hole<void>(`/aufnahmen/${id}?mit_transkripten=${mitTranskripten}`, { method: "DELETE" });
export const aufnahmeMarker = (id: string, marker: { zeit: number; titel: string }[]) =>
  hole<{ zeit: number; titel: string }[]>(`/aufnahmen/${id}/marker`, { method: "PUT", ...json(marker) });
// Eine Aufnahme aus dem Browser ablegen: hochladen, dann ihre Marker
export async function aufnahmeAblegen(daten: Blob, info: Gespeichert): Promise<Aufnahme> {
  const datei = await aufnahmeHochladen(daten, info.name);
  if (info.marker.length) await aufnahmeMarker(datei.id, info.marker);
  return datei;
}
export const aufnahmeTonAdresse = (id: string, anfrage?: AnfrageId) => mit(`/api/v1/inhalt/aufnahmen/${id}/ton`, anfrage);
export const wellenform = (aufnahmeId: string, anfrage?: AnfrageId) =>
  hole<number[]>(mit(`/inhalt/aufnahmen/${aufnahmeId}/wellenform`, anfrage));
export const tonAdresse = (id: string, anfrage?: AnfrageId) => mit(`/api/v1/inhalt/transkripte/${id}/ton`, anfrage);
export const aufnahmeAdresse = (id: string, anfrage?: AnfrageId) => mit(`/api/v1/inhalt/aufnahmen/${id}`, anfrage);

export const vorschlaege = (id: string) => hole<Vorschlag[]>(`/transkripte/${id}/vorschlaege`);

export const profilZuordnen = (id: string, kennung: string, z: { stand: string; profil_id?: string; name?: string },
                              anfrage?: AnfrageId) =>
  hole<TranskriptAntwort>(mit(`/transkripte/${id}/sprecher/${kennung}/profil`, anfrage), { method: "POST", ...json(z) });

export const sprecherErkennen = (id: string, weg: ErkennenWeg, anzahl: number | null, anfrage?: AnfrageId) =>
  hole<Auftrag>(mit(`/transkripte/${id}/sprecher-erkennen`, anfrage), { method: "POST", ...json({ weg, anzahl }) });
export const korrigieren = (id: string, anfrage?: AnfrageId) =>
  hole<Auftrag>(mit(`/transkripte/${id}/korrigieren`, anfrage), { method: "POST" });
export const auswerten = (id: string, vorlage: Vorlage, anfrage?: AnfrageId) =>
  hole<Auftrag>(mit(`/transkripte/${id}/auswerten`, anfrage), { method: "POST", ...json({ vorlage }) });

// --- Sprecherprofile --------------------------------------------------------------------------------------------

export const profile = () => hole<Profil[]>("/sprecher");

// --- Fachwörter-Wörterbuch ------------------------------------------------------------------------------------
export const woerterbuch = () => hole<WoerterbuchStand>("/woerterbuch");
export const woerterbuchSetzen = (woerter: string[]) => hole<WoerterbuchStand>("/woerterbuch", { method: "PUT", ...json({ woerter }) });
export const woerterAufnehmen = (woerter: string[]) =>
  hole<WoerterbuchStand & { neu: string[] }>("/woerterbuch/woerter", { method: "POST", ...json({ woerter }) });
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

// --- Altbestand der alten App ------------------------------------------------------------------------------------
export const altbestand = () => hole<AltbestandSeite>("/altbestand");
export const altUebernehmen = (e: { schluessel: string; zielordner: string; name: string; neu_transkribieren: boolean;
  sprache?: string; sprecher?: SprecherWeg }) => hole<Auftrag>("/altbestand/uebernehmen", { method: "POST", ...json(e) });

// --- Kellerwolke: alle eigenen Dateien als Quelle, eine Ablage --------------------------------------------------

// In der App gewählte Dateien aus der ganzen Kellerwolke mit Optionen transkribieren (je Datei eine Anfrage, Recht nur
// für diesen Auftrag); liefert die Aufträge.
export const ausKellerwolke = (e: { knoten_ids: string[]; sprache?: string; sprecher?: SprecherWeg; anzahl?: number | null;
                                    hoerdienst?: string | null }) =>
  hole<string[]>("/kellerwolke/transkribieren", { method: "POST", ...json(e) });

export const zusammenfuehrenPlan = () => hole<Umzugsplan>("/ablage/zusammenfuehren");
export const zusammenfuehren = () => hole<Auftrag>("/ablage/zusammenfuehren", { method: "POST" });
