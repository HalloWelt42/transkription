<script lang="ts">
  // Ein Beitrag (Segment): Zeit, Sprecher, Text. Beim Mitlesen bekommt nur der laufende Beitrag die Zeit (`jetzt`),
  // so zeichnen die übrigen bei jedem Takt nicht neu. Klick auf ein Wort oder die Zeit springt dorthin. Im
  // Bearbeiten: Textfeld, Sprecher, Zeiten, am Cursor teilen, mit dem nächsten zusammenführen, Marker. Beim Zuordnen der
  // Sprecher ist der Beitrag wählbar: ein Klick wählt ihn (auch auf ein Wort), nur die Zeit springt in den Ton.
  import { Auswahl } from "appkern-oberflaeche";
  import type { Segment, Sprecher } from "../lib/typen";
  import { farbe, genau, lesen, marke } from "../lib/zeit";

  let {
    seg,
    sprecher,
    jetzt = null,
    suche = "",
    mobil = false,
    offen = false,
    bearbeiten = false,
    geaendert = false,
    waehlbar = false,
    gewaehlt = false,
    onspringen,
    onwaehlen,
    onoeffnen,
    onschliessen,
    onaendern,
    onteilen,
    onzusammen,
    onmarker,
  }: {
    seg: Segment;
    sprecher: Sprecher[];
    jetzt?: number | null;
    suche?: string;
    mobil?: boolean;
    offen?: boolean;
    bearbeiten?: boolean;
    geaendert?: boolean;
    waehlbar?: boolean;
    gewaehlt?: boolean;
    onspringen: (t: number) => void;
    onwaehlen?: (e: MouseEvent) => void;
    onoeffnen?: () => void;
    onschliessen?: () => void;
    onaendern?: (s: Segment) => void;
    onteilen?: (position: number) => void;
    onzusammen?: () => void;
    onmarker?: () => void;
  } = $props();

  let feld = $state<HTMLTextAreaElement>();
  let zeitenOffen = $state(false);
  let vonText = $state("");
  let bisText = $state("");

  const name = $derived(sprecher.find((s) => s.kennung === seg.sprecher)?.name ?? "");
  // Wörter nur, wenn sie zum Text passen (nach einer ungespeicherten Änderung zeigt der Beitrag den Text).
  const mitWoertern = $derived(seg.woerter.length > 0 && seg.woerter.map((w) => w.wort).join(" ") === seg.text.trim().split(/\s+/).join(" "));
  const sprecherOptionen = $derived(sprecher.map((s) => ({ wert: s.kennung as string | null, titel: s.name })));

  function teileMitTreffer(text: string): { t: string; treffer: boolean }[] {
    if (!suche.trim()) return [{ t: text, treffer: false }];
    const klein = text.toLowerCase();
    const begriff = suche.trim().toLowerCase();
    const aus: { t: string; treffer: boolean }[] = [];
    let pos = 0;
    for (let i = klein.indexOf(begriff); i >= 0; i = klein.indexOf(begriff, i + begriff.length)) {
      if (i > pos) aus.push({ t: text.slice(pos, i), treffer: false });
      aus.push({ t: text.slice(i, i + begriff.length), treffer: true });
      pos = i + begriff.length;
    }
    if (pos < text.length) aus.push({ t: text.slice(pos), treffer: false });
    return aus;
  }

  function wortKlasse(i: number): string {
    if (jetzt == null) return "wort";
    const w = seg.woerter[i];
    if (jetzt >= w.start && jetzt < w.ende) return "wort jetzt";
    return jetzt >= w.ende ? "wort gehoert" : "wort";
  }

  function zeitenUebernehmen() {
    const von = lesen(vonText);
    const bis = lesen(bisText);
    if (von == null || bis == null || bis < von) return;
    onaendern?.({ ...seg, start: von, ende: bis });
    zeitenOffen = false;
  }

  $effect(() => {
    if (offen && feld) feld.focus();
  });
</script>

{#snippet text()}
  {#if mitWoertern && !suche.trim()}
    {#each seg.woerter as w, i (i)}<span class={wortKlasse(i)} role="button" tabindex="-1"
        onclick={(e) => { if (waehlbar) return; e.stopPropagation(); onspringen(w.start); }} onkeydown={() => {}}>{w.wort}</span>{" "}{/each}
  {:else}
    {#each teileMitTreffer(seg.text) as stueck, i (i)}{#if stueck.treffer}<mark>{stueck.t}</mark>{:else}{stueck.t}{/if}{/each}
  {/if}
{/snippet}

{#if offen}
  <div class="beitrag bearbeiten">
    <span class="zeit">{genau(seg.start)}<br />{genau(seg.ende)}</span>
    <span><Auswahl wert={seg.sprecher} optionen={sprecherOptionen} onwahl={(k) => onaendern?.({ ...seg, sprecher: k })} /></span>
    <div>
      <textarea class="feld-text" rows="3" bind:this={feld} value={seg.text}
                oninput={(e) => onaendern?.({ ...seg, text: e.currentTarget.value })}></textarea>
      {#if zeitenOffen}
        <div class="werkzeuge">
          <label class="eingabe" style="width:150px">von <input bind:value={vonText} /></label>
          <label class="eingabe" style="width:150px">bis <input bind:value={bisText} /></label>
          <button class="knopf klein" onclick={zeitenUebernehmen}>Übernehmen</button>
          <button class="knopf klein still" onclick={() => (zeitenOffen = false)}>Abbrechen</button>
        </div>
      {/if}
      <div class="werkzeuge">
        <button class="knopf klein" title="Teilt den Beitrag an der Stelle des Cursors" onclick={() => onteilen?.(feld?.selectionStart ?? 0)}>
          <i class="fa-solid fa-scissors"></i> Am Cursor teilen</button>
        <button class="knopf klein" onclick={() => onzusammen?.()}><i class="fa-solid fa-object-group"></i> Mit nächstem zusammen</button>
        <button class="knopf klein" onclick={() => { vonText = genau(seg.start); bisText = genau(seg.ende); zeitenOffen = !zeitenOffen; }}>
          <i class="fa-solid fa-clock"></i> Zeiten</button>
        <button class="knopf klein" onclick={() => onmarker?.()}><i class="fa-solid fa-flag"></i> Marker</button>
        <button class="knopf klein still" style="margin-left:auto" onclick={() => onschliessen?.()}>Fertig</button>
      </div>
    </div>
  </div>
{:else if mobil}
  <div class="t-beitrag" class:jetzt={jetzt != null}>
    <div class="wer">{#if seg.sprecher}<span class="punkt" style="width:10px;height:10px;border-radius:5px;background:{farbe(seg.sprecher)}"></span>{name}{/if}
      <button class="zeit" onclick={() => onspringen(seg.start)}>{marke(seg.start)}</button></div>
    <div class="text">{@render text()}</div>
  </div>
{:else}
  <div class="beitrag" class:jetzt={jetzt != null} class:geaendert class:waehlbar class:gewaehlt role="button" tabindex="-1"
       aria-pressed={waehlbar ? gewaehlt : undefined} onmousedown={(e) => waehlbar && e.preventDefault()}
       onclick={(e) => (waehlbar ? onwaehlen?.(e) : bearbeiten ? onoeffnen?.() : onspringen(seg.start))}
       onkeydown={(e) => e.key === "Enter" && !waehlbar && onoeffnen?.()}>
    <button class="zeit" onclick={(e) => { e.stopPropagation(); onspringen(seg.start); }}>{marke(seg.start)}</button>
    <span class="sprecher">{#if seg.sprecher}<span class="punkt" style="background:{farbe(seg.sprecher)}"></span>{name}{/if}</span>
    <div class="text">{@render text()}</div>
  </div>
{/if}
