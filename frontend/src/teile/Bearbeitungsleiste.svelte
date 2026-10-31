<script lang="ts">
  // Feste Leiste oben im Bearbeiten (ein Modus für Text, Sprecher und Marker): kurze Anleitung, wie viel noch nicht
  // gespeichert ist, Verwerfen, Speichern und Fertig; die Sprecher als Knöpfe für die gewählten Beiträge (am Rechner,
  // Ziffer als Taste); der Schalter "am Ende des Beitrags anhalten" mit Erklärung. Die Knöpfe stehen immer an derselben
  // Stelle und sind nur gesperrt, wenn sie nichts tun können. Nach dem Speichern stehen hier die korrigierten Wörter
  // als Vorschlag fürs Fachwörter-Wörterbuch: jedes einzeln an- und abwählbar, aufgenommen wird nur auf Klick.
  import { farbe, fest } from "appkern-oberflaeche";
  import type { Sprecher } from "../lib/typen";

  let {
    mobil = false,
    aenderungen,
    speichert = false,
    anhalten = $bindable(),
    sprecher,
    gewaehlt,
    onzuweisen,
    onneuerSprecher,
    onverwerfen,
    onspeichern,
    onfertig,
    woerter = [],
    wortMeldung = "",
    onaufnehmen,
    onnichtaufnehmen,
  }: {
    mobil?: boolean;
    aenderungen: number;
    speichert?: boolean;
    anhalten: boolean;
    sprecher: Sprecher[];
    gewaehlt: number;          // Zahl der gewählten Beiträge
    onzuweisen: (kennung: string) => void;
    onneuerSprecher: () => void;
    onverwerfen: () => void;
    onspeichern: () => void;
    onfertig: () => void;
    woerter?: string[];         // Vorschlag fürs Wörterbuch nach dem Speichern
    wortMeldung?: string;
    onaufnehmen?: (woerter: string[]) => void;
    onnichtaufnehmen?: () => void;
  } = $props();

  let abgewaehlt = $state<Set<string>>(new Set());
  $effect(() => {
    void woerter;
    abgewaehlt = new Set();
  });
  const gewaehlteWoerter = $derived(woerter.filter((w) => !abgewaehlt.has(w)));

  function umschalten(w: string) {
    const neu = new Set(abgewaehlt);
    if (neu.has(w)) neu.delete(w);
    else neu.add(w);
    abgewaehlt = neu;
  }

  const stand = $derived(aenderungen === 0 ? "Keine Änderungen" : aenderungen === 1 ? "1 Änderung nicht gespeichert"
    : `${aenderungen} Änderungen nicht gespeichert`);
  const ERKLAERUNG = "Hält die Wiedergabe am Ende des geöffneten oder gewählten Beitrags an; nochmal Abspielen läuft weiter.";
</script>

<div class="bearbeitungsleiste" role="toolbar" aria-label="Bearbeiten" use:fest={"oben"}>
  <div class="bl-zeile">
    <span class="bl-titel"><i class="fa-solid fa-pen"></i> Bearbeiten</span>
    <span class="bl-stand" class:offen={aenderungen > 0} aria-live="polite">{stand}</span>
    <span class="bl-knoepfe">
      <button class="knopf still" disabled={!aenderungen || speichert} onclick={onverwerfen}
              title="Alle ungespeicherten Änderungen verwerfen">Verwerfen</button>
      <button class="knopf primaer" disabled={!aenderungen || speichert} onclick={onspeichern}
              title="Legt eine neue Version an; die jetzige bleibt unter Versionen abrufbar">
        <i class="fa-solid {speichert ? 'fa-circle-notch fa-spin' : 'fa-floppy-disk'}"></i> Speichern</button>
      <button class="knopf" disabled={aenderungen > 0} onclick={onfertig}
              title={aenderungen > 0 ? "Erst speichern oder verwerfen" : "Bearbeiten beenden"}>Fertig</button>
    </span>
  </div>
  {#if !mobil}
    <div class="bl-zeile">
      <span class="bl-was">{gewaehlt === 0 ? "Sprecher für" : gewaehlt === 1 ? "Sprecher für 1 Beitrag" : `Sprecher für ${gewaehlt} Beiträge`}</span>
      {#each sprecher as s, n (s.kennung)}
        <button class="sprecher-knopf" disabled={!gewaehlt} onclick={() => onzuweisen(s.kennung)}
                title={gewaehlt ? `${s.name} zuordnen` : "Erst einen Beitrag wählen"}>
          <span class="punkt" style="background:{farbe(s.kennung)}"></span>{s.name}{#if n < 9}<kbd class="taste">{n + 1}</kbd>{/if}</button>
      {/each}
      <button class="sprecher-knopf" onclick={onneuerSprecher} title="Legt einen Sprecher an und ordnet ihn den gewählten Beiträgen zu">
        <i class="fa-solid fa-user-plus"></i>Neuer Sprecher<kbd class="taste">N</kbd></button>
    </div>
  {/if}
  {#if woerter.length}
    <div class="bl-zeile bl-woerter">
      <span class="bl-was"><i class="fa-solid fa-book"></i> Ins Wörterbuch aufnehmen?</span>
      {#each woerter as w (w)}
        <button class="wort-wahl" class:an={!abgewaehlt.has(w)} aria-pressed={!abgewaehlt.has(w)} onclick={() => umschalten(w)}
                title="Antippen wählt ab oder wieder an"><i class="fa-solid {abgewaehlt.has(w) ? 'fa-square' : 'fa-square-check'}"></i>{w}</button>
      {/each}
      <span class="bl-knoepfe">
        <button class="knopf still" onclick={() => onnichtaufnehmen?.()}>Nein</button>
        <button class="knopf" disabled={!gewaehlteWoerter.length} onclick={() => onaufnehmen?.(gewaehlteWoerter)}
                title="Diese Wörter gehen künftig dem Hördienst als Hinweis mit">Aufnehmen</button>
      </span>
    </div>
  {:else if wortMeldung}
    <p class="bl-anleitung"><i class="fa-solid fa-book"></i> {wortMeldung}</p>
  {/if}
  <label class="schalter-zeile bl-anhalten" title={ERKLAERUNG}>
    <button class="schalter" class:an={anhalten} aria-pressed={anhalten} aria-label="Am Ende des Beitrags anhalten"
            onclick={() => (anhalten = !anhalten)}></button>
    <span><b>Am Ende des Beitrags anhalten</b> <span class="bl-erklaerung">{ERKLAERUNG}</span></span>
  </label>
  <p class="bl-anleitung">
    {#if mobil}
      Tippe einen Beitrag an, um Text, Sprecher und Zeiten zu ändern. Speichern legt eine neue Version an.
    {:else}
      Klick öffnet einen Beitrag. Umschalt-Klick wählt einen Bereich, Befehl-Klick einzelne. Ziffer ordnet den Sprecher zu,
      Leertaste spielt, Escape schließt. Marker setzt du am Beitrag oder rechts. Speichern legt eine neue Version an.
    {/if}
  </p>
</div>
