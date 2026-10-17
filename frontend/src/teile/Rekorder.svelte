<script lang="ts">
  // Laufende Aufnahme: Zeit, Pegel, Anhalten, Beenden, Marker; Name und "danach transkribieren" gleich darunter.
  // Nach dem Beenden geht die Aufnahme nach Aufnahmen, ihre Marker hängen an ihr, und auf Wunsch beginnt der Auftrag.
  import { hole, json } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { aufnahme, beenden, markerSetzen, pause, verwerfen } from "../lib/aufnahme.svelte";
  import { hochladen } from "../lib/hochladen.svelte";
  import { marke } from "../lib/zeit";

  let { kompakt = false, onfertig }: { kompakt?: boolean; onfertig?: (meldung: string) => void } = $props();

  let name = $state(aufnahme.name);
  let danach = $state(true);
  let fehler = $state("");
  let sendet = $state(false);

  async function stopp() {
    sendet = true;
    fehler = "";
    try {
      const fertig = await beenden(name);
      if (!fertig) return;
      const datei = await hochladen(fertig.daten, fertig.info.name);
      if (fertig.info.marker.length) await hole(`/aufnahmen/${datei.id}/marker`, { method: "PUT", ...json(fertig.info.marker) });
      if (danach) await api.transkribieren({ quelle_id: datei.id, name: name.trim() || undefined });
      await verwerfen(fertig.info.id);
      onfertig?.(danach ? `${datei.name} liegt in Aufnahmen und wird transkribiert.` : `${datei.name} liegt in Aufnahmen.`);
    } catch (f) {
      fehler = `${(f as Error).message}. Die Aufnahme bleibt auf diesem Gerät und lässt sich später hochladen.`;
    } finally {
      sendet = false;
    }
  }
</script>

<div class="rekorder" class:kompakt>
  <div class="t-uhr">{marke(aufnahme.dauer_ms / 1000)}</div>
  <p class="rekorder-stand">
    <i class="fa-solid fa-circle" style="color:var(--gefahr); font-size:10px"></i>
    {aufnahme.pausiert ? "angehalten" : "nimmt auf"} · wird laufend auf diesem Gerät gesichert
  </p>
  <div class="t-pegel">
    {#each aufnahme.pegel as p, i (i)}<span style="height:{Math.max(4, p)}%"></span>{/each}
  </div>
  <div class="t-steuer">
    <button class="rund" title={aufnahme.pausiert ? "Weiter aufnehmen" : "Anhalten"} onclick={pause} disabled={sendet}>
      <i class="fa-solid {aufnahme.pausiert ? 'fa-play' : 'fa-pause'}"></i></button>
    <button class="stopp" title="Beenden und hochladen" onclick={stopp} disabled={sendet}>
      <i class="fa-solid {sendet ? 'fa-circle-notch fa-spin' : 'fa-stop'}"></i></button>
    <button class="rund" title="Marker setzen" onclick={markerSetzen} disabled={sendet}><i class="fa-solid fa-flag"></i></button>
  </div>
  {#if aufnahme.marker.length}
    <p class="rekorder-stand">{aufnahme.marker.length} Marker: {aufnahme.marker.map((m) => marke(m.zeit)).join(", ")}</p>
  {/if}
  <div class="t-liste">
    <label class="t-zeile"><i class="fa-solid fa-pen"></i><span class="t-text"><span class="t-meta">Name</span>
      <input class="eingabe-roh" bind:value={name} /></span></label>
    <div class="t-zeile"><i class="fa-solid fa-closed-captioning"></i>
      <span class="t-text"><span class="t-name">Danach transkribieren</span><span class="t-meta">mit den Vorgaben aus den Einstellungen</span></span>
      <button class="schalter" class:an={danach} aria-label="Danach transkribieren" aria-pressed={danach} onclick={() => (danach = !danach)}></button>
    </div>
  </div>
  {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
</div>
