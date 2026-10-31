// Hördienste zur Wahl je Auftrag: was die Leitstelle dieser App mit der Fähigkeit hoeren anbietet (GET /hoerdienste,
// eine Wahrheit im Backend), der eingestellte als Vorgabe. Einmal je Sitzung geladen. Welcher rechnet, wählt die App
// bzw. der Mensch; die Leitstelle entscheidet nur, ob und wann.
import { marke } from "appkern-oberflaeche";
import * as api from "./api";
import type { ErzeugtMit, Hoerdienst, Hoerfassung, Segment, Sprecher, Transkript } from "./typen";

export const hoerdienste = $state<{ liste: Hoerdienst[] }>({ liste: [] });
let geladen: Promise<void> | null = null;

export function hoerdiensteLaden(): Promise<void> {
  geladen ??= api.hoerdienste().then((l) => { hoerdienste.liste = l; }).catch(() => { geladen = null; });
  return geladen;
}

export function hoerdienstOptionen(): { wert: string; titel: string }[] {
  void hoerdiensteLaden();
  return hoerdienste.liste.map((d) => ({ wert: d.kennung, titel: d.name }));
}

export function vorgabeHoerdienst(): string | null {
  return hoerdienste.liste.find((d) => d.vorgabe)?.kennung ?? null;
}

// Name eines Modells für Reiter und Vergleich: wie der Hördienst sein Modell nennt, sonst wie die Leitstelle den Dienst;
// ein Ausschnitt nennt seinen Bereich und eine gewählte Abschnittslänge
export function modellName(e: ErzeugtMit | null | undefined): string {
  if (!e) return "Ohne Angabe";
  const name = e.modell || hoerdienste.liste.find((d) => d.kennung === e.dienst)?.name || e.dienst;
  const zusatz = [e.bereich ? `${marke(e.bereich[0])} bis ${marke(e.bereich[1])}` : "",
                  e.abschnitt_s ? `Abschnitte ${e.abschnitt_s} s` : ""].filter(Boolean).join(", ");
  return zusatz ? `${name} (${zusatz})` : name;
}

// Eine Fassung zum Zeigen: die Hauptfassung (Felder des Transkripts, Kennung "haupt") oder eine weitere
export interface Gezeigt {
  id: string;
  name: string;
  erzeugt_mit: ErzeugtMit | null;
  sprecher: Sprecher[];
  segmente: Segment[];
}

export const HAUPT = "haupt";

export function alleFassungen(t: Transkript): Gezeigt[] {
  const haupt: Gezeigt = { id: HAUPT, name: modellName(t.erzeugt_mit), erzeugt_mit: t.erzeugt_mit ?? null,
                           sprecher: t.sprecher, segmente: t.segmente };
  return [haupt, ...(t.fassungen ?? []).map((f: Hoerfassung) => ({ id: f.id, name: modellName(f.erzeugt_mit),
    erzeugt_mit: f.erzeugt_mit, sprecher: f.sprecher, segmente: f.segmente }))];
}

// Rechenzeit des Hörens für den Hinweis am Reiter
export function tempo(e: ErzeugtMit | null | undefined, dauer: number): string {
  if (!e?.hoeren_s) return "";
  const minuten = Math.floor(e.hoeren_s / 60);
  const sekunden = Math.round(e.hoeren_s % 60);
  const faktor = dauer > 0 ? `, ${(dauer / e.hoeren_s).toLocaleString("de-DE", { maximumFractionDigits: 1 })}-mal Echtzeit` : "";
  return `gehört in ${minuten}:${String(sekunden).padStart(2, "0")} min${faktor}`;
}
