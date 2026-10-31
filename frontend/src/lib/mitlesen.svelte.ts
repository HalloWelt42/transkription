// Mitlesen beim Abspielen, eine Wahrheit für die Transkript-Ansicht und den Vergleich der Fassungen: welcher Beitrag
// gerade läuft und das Mitrollen, das eine Weile ruht, sobald man selbst rollt.
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

const RUHE_MS = 8000;

// Folgt der Wiedergabe, außer man rollt selbst: dann ruht es `RUHE_MS` lang.
export class Mitrollen {
  an = $state(true);
  #pause: ReturnType<typeof setTimeout> | undefined;

  selbstGerollt = () => {
    this.an = false;
    clearTimeout(this.#pause);
    this.#pause = setTimeout(() => (this.an = true), RUHE_MS);
  };

  folgen = () => {
    clearTimeout(this.#pause);
    this.an = true;
  };

  // Das Element in die Mitte des Rollfelds, wenn das Mitrollen gerade folgt
  zeigen(feld: HTMLElement | undefined, selektor: string) {
    if (!this.an || !feld) return;
    feld.querySelector(selektor)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}
