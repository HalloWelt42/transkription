<script lang="ts">
  // Mitlesen beim Transkribieren: der Text, den der Auftrag schon gehört hat (je fertigem Abschnitt), mit der Schätzung,
  // wie lange er noch braucht. Neuer Text rollt von selbst ins Bild, solange die Stecknadel steckt; ohne sie bleibt die
  // Stelle, an der man liest. Klick auf eine Zeit springt im Spieler dorthin. Wahrheit ist der Zwischenstand des
  // Auftrags (GET /transkribieren/<auftrag>/bisher), neu geholt bei jeder Meldung des Auftrags.
  import { onMount, tick } from "svelte";
  import { beiAuftrag, marke } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import type { Bisher } from "../lib/typen";

  let { auftrag, onspringen }: { auftrag: string; onspringen: (t: number) => void } = $props();

  const NADEL = "transkription_mitlesen_nadel";
  let stand = $state<Bisher | null>(null);
  let geholt = $state(Date.now());
  let jetzt = $state(Date.now());
  let feld = $state<HTMLElement>();
  let nadel = $state(nadelLesen());
  let fehler = $state("");

  function nadelLesen(): boolean {
    try {
      return localStorage.getItem(NADEL) !== "aus";
    } catch {
      return true;
    }
  }

  function nadelUmschalten() {
    nadel = !nadel;
    try {
      localStorage.setItem(NADEL, nadel ? "an" : "aus");
    } catch {
      // nur eine Bequemlichkeit dieses Geräts
    }
    if (nadel) void ansEnde();
  }

  async function ansEnde() {
    await tick();
    feld?.scrollTo({ top: feld.scrollHeight, behavior: "smooth" });
  }

  async function holen() {
    try {
      const neu = await api.bisher(auftrag);
      const mehr = neu.stuecke.length > (stand?.stuecke.length ?? 0);
      stand = neu;
      geholt = Date.now();
      fehler = "";
      if (mehr && nadel) await ansEnde();
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  onMount(() => {
    void holen();
    const uhr = setInterval(() => (jetzt = Date.now()), 5000);
    const weg = beiAuftrag((a) => {
      if (a.id === auftrag) void holen();
    });
    return () => {
      clearInterval(uhr);
      weg();
    };
  });

  // die Schätzung des Servers, seit dem Holen weitergezählt
  const rest = $derived(stand?.rest_s == null ? null : Math.max(0, stand.rest_s - (jetzt - geholt) / 1000));

  function restText(s: number): string {
    if (s < 60) return "noch unter einer Minute";
    const min = Math.round(s / 60);
    return min < 60 ? `noch etwa ${min} Min` : `noch etwa ${Math.floor(min / 60)} Std ${min % 60} Min`;
  }

  const lage = $derived.by(() => {
    if (!stand) return "";
    if (stand.zustand === "wartet") return "wartet auf einen freien Platz";
    if (!stand.abschnitte) return stand.schritt || "bereitet vor";
    if (stand.abschnitte_fertig >= stand.abschnitte) return `alles gehört; ${stand.schritt || "speichert"}`;
    return `Abschnitt ${stand.abschnitte_fertig + 1} von ${stand.abschnitte}`;
  });

  const schaetzung = $derived.by(() => {
    if (!stand || stand.abschnitte_fertig >= stand.abschnitte) return "";
    if (rest == null) return stand.abschnitte ? "Schätzung nach dem ersten Abschnitt" : "Schätzung folgt";
    return `${restText(rest)}${stand.geschaetzt_aus === "frueher" ? " (nach früheren Aufträgen)" : ""}`;
  });
</script>

<div class="mitlesen">
  <div class="mitlesen-kopf">
    <span class="mitlesen-lage"><i class="fa-solid fa-circle-notch fa-spin"></i> {lage}{#if schaetzung} · <b>{schaetzung}</b>{/if}</span>
    <button class="knopf still mitlesen-nadel" class:aktiv={nadel} aria-pressed={nadel}
            title={nadel ? "Neuer Text rollt ins Bild. Klick: an der Stelle bleiben" : "Text bleibt stehen. Klick: neuen Text ins Bild rollen"}
            onclick={nadelUmschalten}><i class="fa-solid fa-thumbtack"></i> {nadel ? "Mitrollen an" : "Mitrollen aus"}</button>
  </div>
  {#if stand?.dauer_s}
    <div class="balken" title="So weit ist der Text"><span style="width:{Math.min(100, (stand.gehoert_bis_s / stand.dauer_s) * 100)}%"></span></div>
    <div class="mitlesen-unter">{marke(stand.gehoert_bis_s)} von {marke(stand.dauer_s)} gehört</div>
  {/if}
  {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
  <div class="mitlesen-text" bind:this={feld}>
    {#each stand?.stuecke ?? [] as s, i (i)}
      <p><button class="zeit" onclick={() => onspringen(s.start)}>{marke(s.start)}</button>{s.text}</p>
    {:else}
      <p class="leer-zeile">Der Text erscheint hier Abschnitt für Abschnitt, sobald der erste gehört ist.</p>
    {/each}
  </div>
</div>
