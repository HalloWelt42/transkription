<script lang="ts">
  // Vergleich zweier Fassungen derselben Aufnahme (verschiedene Hördienste): nebeneinander, am Telefon untereinander,
  // auf einer Zeitachse. Die Beiträge stehen in Zeilen, die zur selben Zeit beginnen, so steht dieselbe Stelle auf
  // gleicher Höhe (am Telefon folgen die beiden Fassungen einer Stelle direkt aufeinander). Ein Spieler für beide: je
  // Fassung hebt das Mitlesen den laufenden Beitrag hervor und rollt mit; ausgeschaltet bleibt die Fassung reiner Text.
  // Laufender Beitrag und Mitrollen kommen aus lib/mitlesen (dieselbe Wahrheit wie die Transkript-Ansicht).
  // Abweichungen (HELF-79): je Zeile werden die Wörter beider Fassungen abgeglichen (lib/wortvergleich); andere Wörter
  // sind stark markiert, nur Groß und Klein oder Satzzeichen schwach. Vor und zurück springt von Stelle zu Stelle (nur
  // die starken) und spielt sie ab; am Telefon dieselbe Markierung untereinander.
  import { Auswahl } from "appkern-oberflaeche";
  import { aktiverBeitrag, type Mitrollen } from "../lib/mitlesen.svelte";
  import type { Gezeigt } from "../lib/hoerdienste.svelte";
  import type { Segment } from "../lib/typen";
  import { abgleichen, type Abw } from "../lib/wortvergleich";
  import Beitrag from "./Beitrag.svelte";

  let { fassungen, links = $bindable(), rechts = $bindable(), zeit, mobil = false, rollfeld, mitrollen, onspringen }: {
    fassungen: Gezeigt[];
    links: string;
    rechts: string;
    zeit: number;
    mobil?: boolean;
    rollfeld: HTMLElement | undefined;
    mitrollen: Mitrollen;
    onspringen: (t: number) => void;
  } = $props();

  let mitlesen = $state({ links: true, rechts: true });

  const optionen = $derived(fassungen.map((f) => ({ wert: f.id, titel: f.name })));
  const a = $derived(fassungen.find((f) => f.id === links) ?? fassungen[0]);
  const b = $derived(fassungen.find((f) => f.id === rechts) ?? fassungen[1] ?? fassungen[0]);

  interface Zeile {
    links: number[];
    rechts: number[];
  }

  // Zeilen auf der Zeitachse: eine neue Zeile beginnt, sobald ein Beitrag (gleich welcher Seite) erst nach dem Ende
  // aller bisherigen der Zeile anfängt; überlappende Beiträge beider Seiten teilen sich eine Zeile.
  function zeilenBilden(l: Segment[], r: Segment[]): { zeilen: Zeile[]; zeileVon: { links: number[]; rechts: number[] } } {
    const alle = [...l.map((s, i) => ({ s, i, seite: "links" as const })), ...r.map((s, i) => ({ s, i, seite: "rechts" as const }))]
      .sort((x, y) => x.s.start - y.s.start || x.s.ende - y.s.ende);
    const zeilen: Zeile[] = [];
    const zeileVon = { links: new Array<number>(l.length), rechts: new Array<number>(r.length) };
    let ende = -Infinity;
    for (const e of alle) {
      if (!zeilen.length || e.s.start >= ende - 0.05) {
        zeilen.push({ links: [], rechts: [] });
        ende = e.s.ende;
      } else ende = Math.max(ende, e.s.ende);
      zeilen[zeilen.length - 1][e.seite].push(e.i);
      zeileVon[e.seite][e.i] = zeilen.length - 1;
    }
    return { zeilen, zeileVon };
  }

  const plan = $derived(zeilenBilden(a.segmente, b.segmente));
  const aktivLinks = $derived(mitlesen.links ? aktiverBeitrag(a.segmente, zeit) : -1);
  const aktivRechts = $derived(mitlesen.rechts ? aktiverBeitrag(b.segmente, zeit) : -1);

  // Mitrollen: zur Zeile des laufenden Beitrags (links zuerst, sonst rechts)
  $effect(() => {
    const zeile = aktivLinks >= 0 ? plan.zeileVon.links[aktivLinks] : aktivRechts >= 0 ? plan.zeileVon.rechts[aktivRechts] : -1;
    if (zeile >= 0) mitrollen.zeigen(rollfeld, `[data-z="${zeile}"]`);
  });

  function springen(t: number) {
    mitrollen.folgen();
    onspringen(t);
  }

  // ── Abweichungen ────────────────────────────────────────────────────────────────────────────────────────────
  let markieren = $state(true);
  // Die gezeigte Stelle folgt der Spielerzeit (ohne eigenen Zustand): die letzte, die bis kurz nach jetzt beginnt.
  // Springen setzt den Spieler kurz vor eine Stelle; vor und zurück zählen von dort.
  const VORLAUF_S = 0.3;

  interface Stelle { zeile: number; zeit: number; }
  interface Markierung { links: Map<number, Abw[]>; rechts: Map<number, Abw[]>; stellen: Stelle[]; schwach: number;
                         stelleVon: { links: Map<number, number[]>; rechts: Map<number, number[]> }; }

  const woerter = (s: Segment) => s.text.trim().split(/\s+/).filter(Boolean);

  // Beginn eines Worts: mit Wortzeiten genau, sonst der Beginn des Beitrags
  function wortZeit(s: Segment, i: number): number {
    const passt = s.woerter.length > 0 && s.woerter.map((w) => w.wort).join(" ") === woerter(s).join(" ");
    return passt ? s.woerter[i].start : s.start;
  }

  function markierungBilden(): Markierung {
    const m: Markierung = { links: new Map(), rechts: new Map(), stellen: [], schwach: 0,
                            stelleVon: { links: new Map(), rechts: new Map() } };
    plan.zeilen.forEach((z, n) => {
      // die Wörter einer Zeile je Seite, mit Herkunft (Beitrag, Wort)
      const seite = (segs: Segment[], idx: number[]) => idx.flatMap((i) => woerter(segs[i]).map((w, k) => ({ w, i, k })));
      const l = seite(a.segmente, z.links);
      const r = seite(b.segmente, z.rechts);
      const erg = abgleichen(l.map((x) => x.w), r.map((x) => x.w));
      const eintragen = (karte: Map<number, Abw[]>, liste: typeof l, arten: Abw[]) => liste.forEach((x, j) => {
        if (!karte.has(x.i)) karte.set(x.i, []);
        karte.get(x.i)![x.k] = arten[j];
      });
      eintragen(m.links, l, erg.links);
      eintragen(m.rechts, r, erg.rechts);
      m.schwach += erg.links.filter((x) => x === "schwach").length;
      for (const st of erg.stellen) {
        const nr = m.stellen.length;
        const zeit = st.links >= 0 ? wortZeit(a.segmente[l[st.links].i], l[st.links].k) : wortZeit(b.segmente[r[st.rechts].i], r[st.rechts].k);
        m.stellen.push({ zeile: n, zeit });
        // jedes starke Wort kennt seine Stelle (für die Hervorhebung der gezeigten)
        const merken = (karte: Map<number, number[]>, liste: typeof l, arten: Abw[], ab: number) => {
          for (let j = ab; j >= 0 && j < liste.length && arten[j] === "stark"; j++) {
            if (!karte.has(liste[j].i)) karte.set(liste[j].i, []);
            karte.get(liste[j].i)![liste[j].k] = nr;
          }
        };
        if (st.links >= 0) merken(m.stelleVon.links, l, erg.links, st.links);
        if (st.rechts >= 0) merken(m.stelleVon.rechts, r, erg.rechts, st.rechts);
      }
    });
    return m;                                      // Stellen in Zeilenfolge, also nach der Zeit
  }

  const markierung = $derived(markieren ? markierungBilden() : null);
  const stelleNr = $derived(markierung ? markierung.stellen.map((s) => s.zeit <= zeit + VORLAUF_S + 0.05).lastIndexOf(true) : -1);

  function klassen(seite: "links" | "rechts", i: number): string[] | null {
    if (!markierung) return null;
    const arten = markierung[seite].get(i);
    if (!arten) return null;
    const nr = markierung.stelleVon[seite].get(i);
    return arten.map((x, k) => x === "gleich" ? "" : `abw-${x}${stelleNr >= 0 && nr?.[k] === stelleNr ? " abw-gewaehlt" : ""}`);
  }

  function stelleZeigen(schritt: 1 | -1) {
    const st = markierung?.stellen ?? [];
    if (!st.length) return;
    let nr = schritt > 0 ? st.findIndex((s) => s.zeit > zeit + VORLAUF_S + 0.05)
      : st.map((s) => s.zeit < zeit + VORLAUF_S - 0.05).lastIndexOf(true);
    if (nr < 0) nr = schritt > 0 ? 0 : st.length - 1;
    springen(Math.max(0, st[nr].zeit - VORLAUF_S));
  }
</script>

{#snippet wahl(seite: "links" | "rechts", f: Gezeigt)}
  <div class="v-wahl {seite}">
    <span class="v-marke" aria-hidden="true"></span>
    {#if seite === "links"}<Auswahl bind:wert={links} {optionen} />{:else}<Auswahl bind:wert={rechts} {optionen} />{/if}
    <label class="v-mitlesen" title="An: der laufende Beitrag dieser Fassung wird hervorgehoben und rollt mit. Aus: reiner Text.">
      Mitlesen
      <button class="schalter" class:an={mitlesen[seite]} aria-pressed={mitlesen[seite]} aria-label="Mitlesen {f.name}"
              onclick={() => (mitlesen[seite] = !mitlesen[seite])}></button>
    </label>
  </div>
{/snippet}

{#snippet zelle(seite: "links" | "rechts", f: Gezeigt, indizes: number[], aktiv: number)}
  <div class="v-zelle {seite}" class:leer={!indizes.length}>
    {#if mobil && indizes.length}<div class="v-name"><span class="v-marke" aria-hidden="true"></span>{f.name}</div>{/if}
    {#each indizes as i (i)}
      <Beitrag seg={f.segmente[i]} sprecher={f.sprecher} jetzt={i === aktiv ? zeit : null} mobil onspringen={springen}
               wortklassen={klassen(seite, i)} />
    {/each}
  </div>
{/snippet}

<div class="vergleich" class:mobil>
  <div class="v-kopf">
    {@render wahl("links", a)}
    {@render wahl("rechts", b)}
    <div class="v-abw">
      <label class="v-mitlesen" title="Stellen markieren, an denen die Fassungen sich unterscheiden: andere Wörter kräftig, nur Groß und Klein oder Satzzeichen schwach">
        Abweichungen
        <button class="schalter" class:an={markieren} aria-pressed={markieren} aria-label="Abweichungen markieren"
                onclick={() => (markieren = !markieren)}></button>
      </label>
      {#if markierung}
        <span class="v-zahl" title="Stellen mit anderen Wörtern; dahinter die Wörter, die nur in Schreibweise oder Satzzeichen abweichen">
          {#if stelleNr >= 0}<b>{stelleNr + 1}</b> von {/if}<b>{markierung.stellen.length}</b>
          {markierung.stellen.length === 1 ? "Stelle" : "Stellen"}, {markierung.schwach} nur Schreibweise</span>
        <button class="knopf klein ohne" onclick={() => stelleZeigen(-1)} disabled={!markierung.stellen.length}
                title="Vorige Abweichung zeigen und abspielen" aria-label="Vorige Abweichung"><i class="fa-solid fa-chevron-up"></i></button>
        <button class="knopf klein ohne" onclick={() => stelleZeigen(1)} disabled={!markierung.stellen.length}
                title="Nächste Abweichung zeigen und abspielen" aria-label="Nächste Abweichung"><i class="fa-solid fa-chevron-down"></i></button>
      {/if}
    </div>
  </div>
  {#each plan.zeilen as z, n (n)}
    <div class="v-zeile" data-z={n}>
      {@render zelle("links", a, z.links, aktivLinks)}
      {@render zelle("rechts", b, z.rechts, aktivRechts)}
    </div>
  {/each}
  {#if !plan.zeilen.length}<p class="leer">In beiden Fassungen wurde nichts gehört.</p>{/if}
</div>
