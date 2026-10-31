// Mitlesen beim Abspielen, eine Wahrheit für die Transkript-Ansicht und den Vergleich der Fassungen: welcher Beitrag
// gerade läuft. Das Mitrollen zur gesprochenen Stelle (unter festen Köpfen und Leisten) kommt aus dem Appkern (HELF-91).
import type { Segment } from "./typen";

// Der Beitrag, der zur Zeit `zeit` läuft (bis 1,5 s nach seinem Ende), sonst -1. `segmente` sind nach Beginn sortiert.
export function aktiverBeitrag(segmente: Segment[], zeit: number): number {
  let lo = 0;
  let hi = segmente.length - 1;
  let gefunden = -1;
  while (lo <= hi) {
    const mitte = (lo + hi) >> 1;
    if (segmente[mitte].start <= zeit) {
      gefunden = mitte;
      lo = mitte + 1;
    } else hi = mitte - 1;
  }
  return gefunden >= 0 && zeit < segmente[gefunden].ende + 1.5 ? gefunden : -1;
}
