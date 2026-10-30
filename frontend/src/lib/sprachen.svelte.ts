// Sprachen zur Wahl: was der Hördienst laut seinem Steckbrief kann, mit deutschem Namen (GET /sprachen, eine Wahrheit
// im Backend). Einmal je Sitzung geladen; bis dahin und ohne Antwort gilt nur "Erkennen". Ein Kürzel ohne Eintrag (etwa
// die Sprache eines alten Transkripts) zeigt sich als Name des Browsers oder als Kürzel.
import * as api from "./api";

export const sprachen = $state<{ liste: { code: string; name: string }[] }>({ liste: [{ code: "auto", name: "Erkennen" }] });
let geladen: Promise<void> | null = null;

export function sprachenLaden(): Promise<void> {
  geladen ??= api.sprachen().then((l) => { if (l.length) sprachen.liste = l; }).catch(() => { geladen = null; });
  return geladen;
}

// Optionen für eine Auswahl; ohne "Erkennen", wo nur gesprochene Sprachen passen (Filter der Liste)
export function sprachOptionen(mitErkennen = true): { wert: string; titel: string }[] {
  void sprachenLaden();
  return sprachen.liste.filter((s) => mitErkennen || s.code !== "auto").map((s) => ({ wert: s.code, titel: s.name }));
}

const browser = (() => {
  try {
    return new Intl.DisplayNames(["de"], { type: "language" });
  } catch {
    return null;
  }
})();

export function spracheName(code: string): string {
  const eintrag = sprachen.liste.find((s) => s.code === code);
  if (eintrag) return eintrag.name;
  try {
    return browser?.of(code) ?? code.toUpperCase();
  } catch {
    return code.toUpperCase();
  }
}
