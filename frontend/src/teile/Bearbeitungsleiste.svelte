<script lang="ts">
  // Feste Leiste oben im Bearbeiten (ein Modus für Text, Sprecher und Marker): kurze Anleitung, wie viel noch nicht
  // gespeichert ist, Verwerfen, Speichern und Fertig; die Sprecher als Knöpfe für die gewählten Beiträge (am Rechner,
  // Ziffer als Taste); der Schalter "am Ende des Beitrags anhalten" mit Erklärung. Die Knöpfe stehen immer an derselben
  // Stelle und sind nur gesperrt, wenn sie nichts tun können.
  import { farbe } from "appkern-oberflaeche";
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
  } = $props();

  const stand = $derived(aenderungen === 0 ? "Keine Änderungen" : aenderungen === 1 ? "1 Änderung nicht gespeichert"
    : `${aenderungen} Änderungen nicht gespeichert`);
  const ERKLAERUNG = "Hält die Wiedergabe am Ende des geöffneten oder gewählten Beitrags an; nochmal Abspielen läuft weiter.";
</script>

<div class="bearbeitungsleiste" role="toolbar" aria-label="Bearbeiten">
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
