<script lang="ts" generics="T extends string | number | null">
  // Auswahl als Knopf mit aufklappender Liste (statt nativer Auswahlfelder): zeigt immer die Beschriftung, nie den Wert.
  let {
    wert = $bindable(),
    optionen,
    symbol = "",
    titel = "",
    onwahl,
  }: {
    wert: T;
    optionen: { wert: T; titel: string }[];
    symbol?: string;
    titel?: string;
    onwahl?: (w: T) => void;
  } = $props();

  let offen = $state(false);
  let wurzel: HTMLElement;
  const anzeige = $derived(optionen.find((o) => o.wert === wert)?.titel ?? "");

  function waehlen(w: T) {
    wert = w;
    offen = false;
    onwahl?.(w);
  }

  function draussen(e: MouseEvent) {
    if (offen && wurzel && !wurzel.contains(e.target as Node)) offen = false;
  }
</script>

<svelte:window onclick={draussen} onkeydown={(e) => e.key === "Escape" && (offen = false)} />

<span class="auswahl" bind:this={wurzel}>
  <button class="ordnerwahl" type="button" title={titel} aria-expanded={offen} onclick={() => (offen = !offen)}>
    {#if symbol}<i class="fa-solid {symbol}"></i>{/if}<span class="auswahl-text">{anzeige}</span><i class="fa-solid fa-chevron-down"></i>
  </button>
  {#if offen}
    <span class="auswahl-liste" role="listbox">
      {#each optionen as o (o.wert)}
        <button type="button" role="option" aria-selected={o.wert === wert} class:aktiv={o.wert === wert} onclick={() => waehlen(o.wert)}>{o.titel}</button>
      {/each}
    </span>
  {/if}
</span>
