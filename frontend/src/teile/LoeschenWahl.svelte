<script lang="ts">
  // Löschen eines Gesprächs mit Wahl (HELF-154, Entwurf mockups/fortsetzen-loeschen.html, 5 und 6): ganz, nur das
  // Transkript oder nur die Aufnahme. Angeboten wird nur, was es gibt; alles landet im Papierkorb der
  // Kellerwolke. Im Ablauf statt als Fenster, wie die Rückfrage des Appkerns.
  import type { LoeschenWas } from "../lib/typen";

  let { transkript, aufnahme, beschaeftigt = false, nebeneinander = false, onabbrechen, onja }: {
    transkript: boolean; aufnahme: boolean; beschaeftigt?: boolean; nebeneinander?: boolean;
    onabbrechen: () => void; onja: (was: LoeschenWas) => void;
  } = $props();

  const wahlen = $derived([
    ...(transkript && aufnahme ? [{ was: "ganz" as const, titel: "Gespräch ganz", unter: "Transkript und Aufnahme" }] : []),
    ...(transkript ? [{ was: "transkript" as const, titel: aufnahme ? "Nur das Transkript" : "Das Transkript",
                        unter: aufnahme ? "Die Aufnahme bleibt und lässt sich neu transkribieren" : "" }] : []),
    ...(aufnahme ? [{ was: "aufnahme" as const, titel: transkript ? "Nur die Aufnahme" : "Die Aufnahme",
                      unter: transkript ? "Der Text bleibt ohne Ton stehen" : "" }] : []),
  ]);
  let gewaehlt = $state<LoeschenWas | null>(null);
  const wahl = $derived(gewaehlt && wahlen.some((w) => w.was === gewaehlt) ? gewaehlt : wahlen[0]?.was ?? null);
</script>

<div class="rueckfrage loeschen-wahl" class:nebeneinander role="alertdialog" aria-label="Was soll in den Papierkorb?">
  <span class="frage">Was soll in den Papierkorb?</span>
  {#if wahlen.length > 1}
    <div class="wahl" role="radiogroup" aria-label="Was in den Papierkorb kommt">
      {#each wahlen as w (w.was)}
        <button role="radio" aria-checked={wahl === w.was} class:an={wahl === w.was} onclick={() => (gewaehlt = w.was)}>
          <i class="{wahl === w.was ? 'fa-solid fa-circle-dot' : 'fa-regular fa-circle'}"></i>
          <span>{w.titel}{#if w.unter && !nebeneinander}<span class="unter">{w.unter}</span>{/if}</span></button>
      {/each}
    </div>
  {/if}
  <span class="hinweis">Im Papierkorb der Kellerwolke lässt sich alles zurückholen.</span>
  <span class="aktionen">
    <button class="knopf still" onclick={onabbrechen} disabled={beschaeftigt}>Abbrechen</button>
    <button class="knopf gefahr" onclick={() => wahl && onja(wahl)} disabled={beschaeftigt || !wahl}>
      <i class="fa-solid {beschaeftigt ? 'fa-circle-notch fa-spin' : 'fa-trash-can'}"></i> In den Papierkorb</button>
  </span>
</div>

<style>
  .loeschen-wahl { flex-direction: column; align-items: stretch; }
  .loeschen-wahl .aktionen { margin-left: 0; justify-content: flex-end; }
  .loeschen-wahl.nebeneinander { flex-direction: row; flex-wrap: wrap; align-items: center; }
  .loeschen-wahl.nebeneinander .aktionen { margin-left: auto; }
  .loeschen-wahl.nebeneinander .wahl { display: flex; flex-wrap: wrap; }
  .wahl { display: grid; gap: 6px; }
  .wahl button { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 8px 12px; border: 0; border-radius: var(--r2);
                 background: var(--flaeche); color: var(--text); font: inherit; text-align: left; cursor: pointer; box-shadow: 0 0 0 1px var(--rand); }
  .wahl button.an { box-shadow: 0 0 0 2px var(--akzent); }
  .wahl button i { flex: none; color: var(--text-3); }
  .wahl button.an i { color: var(--akzent); }
  .unter { display: block; font-size: var(--klein); color: var(--text-3); }
  .hinweis { color: var(--text-2); }
</style>
