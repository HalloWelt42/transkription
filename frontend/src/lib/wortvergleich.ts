// Wortweiser Vergleich zweier Texte und was daraus fürs Wörterbuch folgt. Der Vergleich (längste gemeinsame Folge)
// zeigt Vorschläge der KI-Korrektur; derselbe Vergleich findet nach einer Korrektur im Bearbeiten die Wörter, die der
// Nutzer an Stelle anderer geschrieben hat. Die gehen nur als Vorschlag an ihn, nie von selbst ins Wörterbuch.

export type Stueck = { teil: string; art: "gleich" | "weg" | "neu" };

export function abweichung(alt: string, neu: string): Stueck[] {
  const a = alt.split(/\s+/).filter(Boolean);
  const b = neu.split(/\s+/).filter(Boolean);
  const l = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--) l[i][j] = a[i] === b[j] ? l[i + 1][j + 1] + 1 : Math.max(l[i + 1][j], l[i][j + 1]);
  const aus: Stueck[] = [];
  const dazu = (teil: string, art: Stueck["art"]) => {
    const letzte = aus.at(-1);
    if (letzte && letzte.art === art) letzte.teil += ` ${teil}`;
    else aus.push({ teil, art });
  };
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      dazu(a[i++], "gleich");
      j++;
    } else if (i < a.length && (j >= b.length || l[i + 1][j] >= l[i][j + 1])) dazu(a[i++], "weg");
    else dazu(b[j++], "neu");
  }
  return aus.map((x, n) => ({ ...x, teil: n < aus.length - 1 ? `${x.teil} ` : x.teil }));
}

// Ein Wort ohne Satzzeichen am Rand (wie im Wörterbuch des Backends)
export const sauber = (wort: string) => wort.trim().replace(/^[.,;:!?"'()[\]{}»«]+|[.,;:!?"'()[\]{}»«]+$/g, "");
const vergleich = (text: string) => text.split(/\s+/).map(sauber).filter(Boolean).join(" ").toLowerCase();

const HOECHSTENS = 8;

// Wörter, die an Stelle anderer getreten sind (nicht nur Groß und Klein oder Satzzeichen geändert), ohne die schon im
// Wörterbuch und ohne Zahlen; je Paar alter und neuer Text eines Beitrags.
export function korrigierteWoerter(paare: { alt: string; neu: string }[], bekannt: string[]): string[] {
  const schon = new Set(bekannt.map((w) => w.toLowerCase()));
  const aus = new Map<string, string>();
  for (const { alt, neu } of paare) {
    const teile = abweichung(alt, neu);
    teile.forEach((x, n) => {
      if (x.art !== "neu") return;
      const davor = teile[n - 1];
      const weg = davor?.art === "weg" ? davor.teil : teile[n + 1]?.art === "weg" ? teile[n + 1].teil : null;
      if (weg == null || vergleich(weg) === vergleich(x.teil)) return;
      const alteWoerter = new Set(vergleich(weg).split(" "));
      for (const w of x.teil.split(/\s+/).map(sauber)) {
        const k = w.toLowerCase();
        if (w.length < 2 || /^\d+$/.test(w) || schon.has(k) || alteWoerter.has(k) || aus.has(k)) continue;
        aus.set(k, w);
      }
    });
  }
  return [...aus.values()].slice(0, HOECHSTENS);
}

// ── Abgleich zweier Fassungen (Vergleichsansicht) ────────────────────────────────────────────────────────────────
// Je Wort: gleich, schwach (nur Groß und Klein oder Satzzeichen anders) oder stark (anderes Wort, fehlt oder kommt
// dazu). Zusammenhängende starke Wörter beider Seiten bilden eine Stelle (zum Springen und Zählen).

export type Abw = "gleich" | "schwach" | "stark";

export interface Abgleich {
  links: Abw[];
  rechts: Abw[];
  stellen: { links: number; rechts: number }[];   // erstes Wort der Stelle je Seite (-1: auf dieser Seite keins)
}

const kern = (wort: string) => sauber(wort).toLowerCase();

export function abgleichen(l: string[], r: string[]): Abgleich {
  const a = l.map(kern);
  const b = r.map(kern);
  const t = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--) t[i][j] = a[i] === b[j] ? t[i + 1][j + 1] + 1 : Math.max(t[i + 1][j], t[i][j + 1]);
  const links = new Array<Abw>(a.length).fill("stark");
  const rechts = new Array<Abw>(b.length).fill("stark");
  const stellen: Abgleich["stellen"] = [];
  let offen: { links: number; rechts: number } | null = null;
  const stark = (seite: "links" | "rechts", n: number) => {
    if (!offen) stellen.push((offen = { links: -1, rechts: -1 }));
    if (offen[seite] < 0) offen[seite] = n;
  };
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      links[i] = rechts[j] = l[i] === r[j] ? "gleich" : "schwach";
      offen = null;
      i++;
      j++;
    } else if (i < a.length && (j >= b.length || t[i + 1][j] >= t[i][j + 1])) stark("links", i++);
    else stark("rechts", j++);
  }
  return { links, rechts, stellen };
}
