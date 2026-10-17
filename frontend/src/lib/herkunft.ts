// Dateien aus der Kellerwolke, geöffnet über eine Anfrage (Entwurf mockups/verbund.html 6b, 6c): wo sie dort liegen und
// der Weg zurück. Einzige Stelle für Adressen in die Kellerwolke.
import { gehe, sitzung } from "appkern-oberflaeche";

// Die Datei in der Kellerwolke: ihr Ordner, die Datei darin gezeigt; leer, solange die App die Adresse nicht kennt.
export function inKellerwolke(pfad: string): string {
  const kw = sitzung.app?.kellerwolke;
  return kw ? `${kw}/dateien/${pfad.split("/").filter(Boolean).map(encodeURIComponent).join("/")}` : "";
}

// Zurück, woher die Datei kam: aus der Quelle "Kellerwolke" der App oder aus der Kellerwolke im selben Fenster über den
// Verlauf; in einem eigenen Fenster in die Kellerwolke zu der Datei.
export function zurueckZurKellerwolke(pfad: string): void {
  const ziel = inKellerwolke(pfad);
  if (history.length > 1) history.back();
  else if (ziel) location.assign(ziel);
  else gehe("aufnahmen/kellerwolke");
}

// Begleiter neben einer Datei, zum Lesen ("Transkript und Untertitel daneben"), in der Reihenfolge hier; unbekannte
// Rollen zählen nicht.
const ROLLEN: Record<string, string> = {
  transkript: "Transkript", text: "Text", markdown: "Markdown", untertitel: "Untertitel", untertitel_vtt: "Untertitel",
  daten: "Daten", dokument: "Dokument", protokoll: "Protokoll",
};

export function daneben(rollen: (string | null)[]): string {
  const da = new Set(rollen);
  const namen = [...new Set(Object.keys(ROLLEN).filter((r) => da.has(r)).map((r) => ROLLEN[r]))];
  if (!namen.length) return "";
  return `${namen.length > 1 ? `${namen.slice(0, -1).join(", ")} und ${namen.at(-1)}` : namen[0]} daneben`;
}
