// Weiter aufnehmen (HELF-154): solange eine Aufnahme als Fortsetzung läuft, steht hier, an welche Tondatei sie kommt.
// Eine Wahrheit für alle Ansichten: wo auch immer die Aufnahme beendet wird (Aufnahmen, Aufnahme, Transkript), legt
// `Aufnehmen` sie hinten an diese Datei statt als neue Aufnahme ab.
import { aufnahme, aufnehmen } from "appkern-oberflaeche";

export interface Fortsetzung {
  aufnahmeId: string;
  name: string;
  ab_s: number | null;       // so lang ist die Aufnahme bisher (wenn bekannt); dort schließt der neue Ton an
  transkript: boolean;       // es gibt ein Transkript: der neue Text kommt unten dazu
  zurueck: string;           // wohin es danach geht (Transkript oder Aufnahme)
}

export const fortsetzung = $state<{ ziel: Fortsetzung | null }>({ ziel: null });

// Mikrofon an, die neue Aufnahme kommt an `ziel`; gibt es kein Mikrofon, bleibt alles, wie es war
export async function weiterAufnehmen(ziel: Fortsetzung): Promise<void> {
  if (aufnahme.laeuft) return;
  aufnahme.danach = null;
  fortsetzung.ziel = ziel;
  await aufnehmen();
  if (!aufnahme.laeuft) fortsetzung.ziel = null;
}
