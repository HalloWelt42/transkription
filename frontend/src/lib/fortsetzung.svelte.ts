// Ein Gespräch weiterführen (HELF-154): solange eine Aufnahme als weiterer Teil läuft, steht hier, woran sie hängt.
// Eine Wahrheit für alle Ansichten: wo auch immer die Aufnahme beendet wird (Transkript, Aufnahmen), legt `Aufnehmen`
// sie als Teil dieses Gesprächs ab statt als neue Aufnahme.
import type { Transkript } from "./typen";

export interface Fortsetzung {
  hauptId: string;          // die erste Aufnahme des Gesprächs (Teil 1)
  transkriptId: string;
  name: string;             // Name des Gesprächs
  nummer: number;           // der Teil, der gerade entsteht (2, 3 ...)
  ab_s: number;             // dort schließt er in der Zeit des Transkripts an
}

export const fortsetzung = $state<{ ziel: Fortsetzung | null }>({ ziel: null });

export function fortsetzungFuer(transkriptId: string, t: Transkript): Fortsetzung | null {
  const hauptId = t.quelle?.knoten_id;
  return hauptId ? { hauptId, transkriptId, name: t.name, nummer: (t.teile?.length ?? 0) + 2, ab_s: t.dauer_s } : null;
}
