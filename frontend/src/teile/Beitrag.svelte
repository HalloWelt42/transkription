<script lang="ts">
  // Ein Beitrag (Segment): Zeit, Sprecher, Text. Beim Mitlesen bekommt nur der laufende Beitrag die Zeit (`jetzt`),
  // so zeichnen die übrigen bei jedem Takt nicht neu. Klick auf ein Wort oder die Zeit springt dorthin.
  // Im Bearbeiten ist jeder Beitrag wählbar: der Klick (am Telefon das Antippen) meldet sich mit `onklick`, die Ansicht
  // öffnet ihn oder erweitert die Auswahl. Offen: Sprecher, Text, Beginn und Ende (auch als Spielerzeit), am Cursor
  // teilen, mit dem nächsten zusammenführen, Marker; Escape im Text schließt ihn wieder.
  import { Auswahl, farbe, genau, lesen, marke } from "appkern-oberflaeche";
  import type { Segment, Sprecher } from "../lib/typen";

  // Wahl in der Sprecherliste, die einen neuen Sprecher anlegt (keine gültige Kennung, die heißen s1, s2, ...)
  const NEUER_SPRECHER = "+neu";

  let {
    seg,
    sprecher,
    jetzt = null,
    suche = "",
    mobil = false,
    bearbeiten = false,
    offen = false,
    gewaehlt = false,
    geaendert = false,
    spielerzeit = null,
    onspringen,
    onklick,
    onschliessen,
    onaendern,
    onteilen,
    onzusammen,
    onmarker,
    onneuerSprecher,
    wortklassen = null,
  }: {
    seg: Segment;
    sprecher: Sprecher[];
    jetzt?: number | null;
    suche?: string;
    mobil?: boolean;
    bearbeiten?: boolean;
    offen?: boolean;
    gewaehlt?: boolean;
    geaendert?: boolean;
    spielerzeit?: number | null;     // nur der offene Beitrag bekommt die Zeit des Spielers
    onspringen: (t: number) => void;
    onklick?: (e: MouseEvent) => void;
    onschliessen?: () => void;
    onaendern?: (s: Segment) => void;
    onteilen?: (position: number) => void;
    onzusammen?: () => void;
    onmarker?: () => void;
    onneuerSprecher?: () => string | null;
    wortklassen?: string[] | null;     // je Wort des Texts eine Klasse dazu (Vergleich: Abweichungen markieren)
  } = $props();

  let feld = $state<HTMLTextAreaElement>();

  const name = $derived(sprecher.find((s) => s.kennung === seg.sprecher)?.name ?? "");
  // Wörter nur, wenn sie zum Text passen (nach einer ungespeicherten Änderung zeigt der Beitrag den Text).
  const mitWoertern = $derived(seg.woerter.length > 0 && seg.woerter.map((w) => w.wort).join(" ") === seg.text.trim().split(/\s+/).join(" "));
  const sprecherOptionen = $derived([{ wert: null as string | null, titel: "ohne Sprecher" },
    ...sprecher.map((s) => ({ wert: s.kennung as string | null, titel: s.name })),
    { wert: NEUER_SPRECHER as string | null, titel: "Neuer Sprecher" }]);
  const beginnMoeglich = $derived(spielerzeit != null && spielerzeit < seg.ende);
  const endeMoeglich = $derived(spielerzeit != null && spielerzeit > seg.start);

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

  function sprecherWaehlen(k: string | null) {
    const kennung = k === NEUER_SPRECHER ? onneuerSprecher?.() ?? null : k;
    if (k === NEUER_SPRECHER && !kennung) return;
    onaendern?.({ ...seg, sprecher: kennung });
  }

  // Beginn und Ende von Hand: gilt beim Verlassen des Feldes oder mit Eingabe; Unpassendes stellt das Feld zurück
  function zeitEintragen(feldname: "start" | "ende", e: Event & { currentTarget: HTMLInputElement }) {
    const wert = lesen(e.currentTarget.value);
    const neu = { ...seg, [feldname]: wert };
    if (wert == null || neu.ende <= neu.start) {
      e.currentTarget.value = genau(seg[feldname]);
      return;
    }
    onaendern?.(neu);
  }

  function spielerzeitAls(feldname: "start" | "ende") {
    if (spielerzeit == null) return;
    onaendern?.({ ...seg, [feldname]: Math.round(spielerzeit * 10) / 10 });
  }

  function textTaste(e: KeyboardEvent) {
    if (e.key !== "Escape") return;
    e.preventDefault();
    e.stopPropagation();
    onschliessen?.();
  }

  $effect(() => {
    if (offen && feld) feld.focus();
  });
</script>

{#snippet text()}
  {#if mitWoertern && !suche.trim()}
    {#each seg.woerter as w, i (i)}<span class="{wortKlasse(i)} {wortklassen?.[i] ?? ''}" role="button" tabindex="-1"
        onclick={(e) => { if (bearbeiten) return; e.stopPropagation(); onspringen(w.start); }} onkeydown={() => {}}>{w.wort}</span>{" "}{/each}
  {:else if wortklassen && !suche.trim()}
    {#each seg.text.trim().split(/\s+/) as w, i (i)}<span class={wortklassen[i] ?? ""}>{w}</span>{" "}{/each}
  {:else}
    {#each teileMitTreffer(seg.text) as stueck, i (i)}{#if stueck.treffer}<mark>{stueck.t}</mark>{:else}{stueck.t}{/if}{/each}
  {/if}
{/snippet}

{#if offen}
  <div class="beitrag bearbeiten">
    <button class="zeit" title="Hier abspielen" onclick={() => onspringen(seg.start)}>{marke(seg.start)}</button>
    <span class="b-sprecher"><Auswahl wert={seg.sprecher} optionen={sprecherOptionen} titel="Sprecher dieses Beitrags" onwahl={sprecherWaehlen} /></span>
    <div class="b-inhalt">
      <textarea class="feld-text" rows={mobil ? 5 : 3} bind:this={feld} value={seg.text} aria-label="Text des Beitrags"
                oninput={(e) => onaendern?.({ ...seg, text: e.currentTarget.value })} onkeydown={textTaste}></textarea>
      <div class="b-zeiten">
        <span class="b-zeit">
        <label class="eingabe zeit-feld" title="Beginn des Beitrags (Minuten:Sekunden)">Beginn
          <input value={genau(seg.start)} onchange={(e) => zeitEintragen("start", e)} aria-label="Beginn" /></label>
        <button class="knopf klein" disabled={!beginnMoeglich} onclick={() => spielerzeitAls("start")}
                title={spielerzeit != null ? `Beginn auf die Stelle des Spielers setzen (${genau(spielerzeit)})` : undefined}>
          <i class="fa-solid fa-arrow-right-to-bracket"></i> Spielerzeit als Beginn</button></span>
        <span class="b-zeit">
        <label class="eingabe zeit-feld" title="Ende des Beitrags (Minuten:Sekunden)">Ende
          <input value={genau(seg.ende)} onchange={(e) => zeitEintragen("ende", e)} aria-label="Ende" /></label>
        <button class="knopf klein" disabled={!endeMoeglich} onclick={() => spielerzeitAls("ende")}
                title={spielerzeit != null ? `Ende auf die Stelle des Spielers setzen (${genau(spielerzeit)})` : undefined}>
          <i class="fa-solid fa-arrow-right-from-bracket"></i> Spielerzeit als Ende</button></span>
      </div>
      <div class="werkzeuge">
        <button class="knopf klein" title="Teilt den Beitrag an der Stelle des Cursors in zwei" onclick={() => onteilen?.(feld?.selectionStart ?? 0)}>
          <i class="fa-solid fa-scissors"></i> Am Cursor teilen</button>
        <button class="knopf klein" title="Hängt den folgenden Beitrag an diesen an" onclick={() => onzusammen?.()}>
          <i class="fa-solid fa-object-group"></i> Mit nächstem zusammen</button>
        <button class="knopf klein" title="Setzt einen Marker an den Beginn dieses Beitrags" onclick={() => onmarker?.()}>
          <i class="fa-solid fa-flag"></i> Marker</button>
        <button class="knopf klein still b-schliessen" title="Beitrag schließen (Escape); die Änderung bleibt im Entwurf" onclick={() => onschliessen?.()}>
          <i class="fa-solid fa-check"></i> Schließen</button>
      </div>
    </div>
  </div>
{:else if mobil}
  <div class="t-beitrag" class:jetzt={jetzt != null} class:geaendert class:waehlbar={bearbeiten} role="button" tabindex="-1"
       onclick={(e) => bearbeiten && onklick?.(e)} onkeydown={() => {}}>
    <div class="wer">{#if seg.sprecher}<span class="punkt" style="width:10px;height:10px;border-radius:5px;background:{farbe(seg.sprecher)}"></span>{name}{/if}
      <button class="zeit" onclick={(e) => { e.stopPropagation(); onspringen(seg.start); }}>{marke(seg.start)}</button></div>
    <div class="text">{@render text()}</div>
  </div>
{:else}
  <div class="beitrag" class:jetzt={jetzt != null} class:geaendert class:waehlbar={bearbeiten} class:gewaehlt role="button" tabindex="-1"
       aria-pressed={bearbeiten ? gewaehlt : undefined} title={bearbeiten ? "Klick öffnet den Beitrag zum Ändern" : undefined}
       onmousedown={(e) => bearbeiten && (e.shiftKey || e.metaKey || e.ctrlKey) && e.preventDefault()}
       onclick={(e) => (bearbeiten ? onklick?.(e) : onspringen(seg.start))} onkeydown={() => {}}>
    <button class="zeit" title="Hier abspielen" onclick={(e) => { e.stopPropagation(); onspringen(seg.start); }}>{marke(seg.start)}</button>
    <span class="sprecher">{#if seg.sprecher}<span class="punkt" style="background:{farbe(seg.sprecher)}"></span>{name}{/if}</span>
    <div class="text">{@render text()}</div>
  </div>
{/if}
