<script lang="ts">
  // Vergleich zweier Fassungen derselben Aufnahme (verschiedene Hördienste): nebeneinander, am Telefon untereinander,
  // auf einer Zeitachse. Die Beiträge stehen in Zeilen, die zur selben Zeit beginnen, so steht dieselbe Stelle auf
  // gleicher Höhe (am Telefon folgen die beiden Fassungen einer Stelle direkt aufeinander). Ein Spieler für beide: je
  // Fassung hebt das Mitlesen den laufenden Beitrag hervor und rollt mit; ausgeschaltet bleibt die Fassung reiner Text.
  // Laufender Beitrag und Mitrollen kommen aus lib/mitlesen (dieselbe Wahrheit wie die Transkript-Ansicht).
  import { Auswahl } from "appkern-oberflaeche";
  import { aktiverBeitrag, type Mitrollen } from "../lib/mitlesen.svelte";
  import type { Gezeigt } from "../lib/hoerdienste.svelte";
  import type { Segment } from "../lib/typen";
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
      <Beitrag seg={f.segmente[i]} sprecher={f.sprecher} jetzt={i === aktiv ? zeit : null} mobil onspringen={springen} />
    {/each}
  </div>
{/snippet}

<div class="vergleich" class:mobil>
  <div class="v-kopf">
    {@render wahl("links", a)}
    {@render wahl("rechts", b)}
  </div>
  {#each plan.zeilen as z, n (n)}
    <div class="v-zeile" data-z={n}>
      {@render zelle("links", a, z.links, aktivLinks)}
      {@render zelle("rechts", b, z.rechts, aktivRechts)}
    </div>
  {/each}
  {#if !plan.zeilen.length}<p class="leer">In beiden Fassungen wurde nichts gehört.</p>{/if}
</div>
