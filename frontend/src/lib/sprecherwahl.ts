// Wahl der Sprecher beim Transkribieren und beim späteren Erkennen: ein Ort für Wege und Anzahl.
// Ab Werk ohne Sprecher; die automatische Zuordnung ist nicht bei jeder Aufnahme sauber.

export type SprecherWeg = "ohne" | "stimmen" | "trennung";
export type ErkennenWeg = Exclude<SprecherWeg, "ohne">;

export const SPRECHER_WEGE: { wert: SprecherWeg; titel: string }[] = [
  { wert: "ohne", titel: "Ohne Sprecher" },
  { wert: "stimmen", titel: "Stimmen gruppieren" },
  { wert: "trennung", titel: "Mit Sprechertrennung" },
];

export const ERKENNEN_WEGE = SPRECHER_WEGE.filter((w): w is { wert: ErkennenWeg; titel: string } => w.wert !== "ohne");

export const ANZAHL_OPTIONEN = [{ wert: null as number | null, titel: "von selbst" },
  ...[2, 3, 4, 5, 6].map((n) => ({ wert: n as number | null, titel: `${n} Sprecher` }))];
