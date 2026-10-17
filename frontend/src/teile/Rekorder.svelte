<script lang="ts">
  // Aufnehmen: Zeit, Pegel, Anhalten, Beenden, Marker; Mikrofon wählbar (auch während der Aufnahme), Live-Mitschrift
  // auf Wunsch. Nach dem Beenden liegt die Aufnahme in Aufnahmen (mit ihren Markern); transkribiert wird erst, wenn
  // der Nutzer es entscheidet: genau mit Sprechern, aus der Live-Mitschrift, oder gar nicht.
  import { Auswahl, hole, json } from "appkern-oberflaeche";
  import { tick } from "svelte";
  import * as api from "../lib/api";
  import { ANZAHL_OPTIONEN, SPRECHER_WEGE, type SprecherWeg } from "../lib/sprecherwahl";
  import { aufnahme, beenden, markerSetzen, pause, quelleWechseln, tonFortsetzen, verwerfen } from "../lib/aufnahme.svelte";
  import { hochladen } from "../lib/hochladen.svelte";
  import { marke, SPRACHEN } from "../lib/zeit";

  let { kompakt = false, onfertig }: { kompakt?: boolean; onfertig?: (meldung: string) => void } = $props();

  let name = $state(aufnahme.name);
  let fehler = $state("");
  let sendet = $state(false);
  let sprache = $state("de");
  let sprecher = $state<SprecherWeg>("ohne");
  let anzahl = $state<number | null>(null);
  let textfeld = $state<HTMLElement>();

  const geraete = $derived([{ wert: "", titel: "Standard des Systems" }, ...aufnahme.geraete
    .filter((g) => g.id && g.id !== "default").map((g) => ({ wert: g.id, titel: g.name }))]);
  const sprachOptionen = Object.entries(SPRACHEN).map(([wert, titel]) => ({ wert, titel }));

  $effect(() => {
    void aufnahme.mitschrift.length;
    void tick().then(() => textfeld?.scrollTo({ top: textfeld.scrollHeight }));
  });

  async function stopp() {
    sendet = true;
    fehler = "";
    try {
      const fertig = await beenden(name);
      if (!fertig) return;
      const datei = await hochladen(fertig.daten, fertig.info.name);
      if (fertig.info.marker.length) await hole(`/aufnahmen/${datei.id}/marker`, { method: "PUT", ...json(fertig.info.marker) });
      await verwerfen(fertig.info.id);
      aufnahme.danach = { id: datei.id, name: name.trim() || aufnahme.name, dauer_s: fertig.info.dauer_ms / 1000,
                          mitschrift: [...aufnahme.mitschrift] };
    } catch (f) {
      fehler = `${(f as Error).message}. Die Aufnahme bleibt auf diesem Gerät und lässt sich später hochladen.`;
    } finally {
      sendet = false;
    }
  }

  async function entscheiden(wie: "genau" | "live" | "fertig") {
    const d = aufnahme.danach;
    if (!d) return;
    sendet = true;
    fehler = "";
    try {
      if (wie === "genau") {
        await api.transkribieren({ quelle_id: d.id, name: d.name, sprache, sprecher, anzahl: sprecher !== "ohne" ? anzahl : null });
        onfertig?.(`${d.name} wird transkribiert; der Stand steht in der Liste und unter Aufträge.`);
      } else if (wie === "live") {
        await api.ausMitschrift({ quelle_id: d.id, name: d.name, sprache: sprache === "auto" ? "de" : sprache, stuecke: d.mitschrift });
        onfertig?.(`${d.name}: Transkript aus der Live-Mitschrift angelegt.`);
      } else {
        onfertig?.(`${d.name} liegt in Aufnahmen.`);
      }
      aufnahme.danach = null;
    } catch (f) {
      fehler = (f as Error).message;
    } finally {
      sendet = false;
    }
  }
</script>

{#snippet mitschrift(stuecke: { start: number; text: string }[], stand: string)}
  <div class="mitschrift">
    <div class="mitschrift-kopf"><i class="fa-solid fa-closed-captioning"></i> Live-Mitschrift
      {#if stand}<span class="mitschrift-stand">{stand}</span>{/if}</div>
    <div class="mitschrift-text" bind:this={textfeld}>
      {#each stuecke as s, i (i)}<p><span class="zeit">{marke(s.start)}</span>{s.text}</p>{:else}
        <p class="mitschrift-leer">Der Text erscheint nach den ersten Sätzen.</p>{/each}
    </div>
  </div>
{/snippet}

<div class="rekorder" class:kompakt>
  {#if aufnahme.danach}
    {@const d = aufnahme.danach}
    <div class="rekorder-gespeichert">
      <i class="fa-solid fa-circle-check"></i>
      <div><b>{d.name}</b> liegt in Aufnahmen ({marke(d.dauer_s)}). Was soll damit geschehen?</div>
    </div>
    {#if d.mitschrift.length}{@render mitschrift(d.mitschrift, "")}{/if}
    <div class="entscheidung">
      <div class="entscheidung-optionen">
        <label>Sprache <Auswahl bind:wert={sprache} optionen={sprachOptionen} /></label>
        <label>Sprecher <Auswahl bind:wert={sprecher} optionen={SPRECHER_WEGE} /></label>
        {#if sprecher !== "ohne"}<label>Anzahl <Auswahl bind:wert={anzahl} optionen={ANZAHL_OPTIONEN} /></label>{/if}
      </div>
      <div class="knopfzeile">
        <button class="knopf primaer" disabled={sendet} onclick={() => entscheiden("genau")}><i class="fa-solid fa-closed-captioning"></i> Transkribieren</button>
        {#if d.mitschrift.length}
          <button class="knopf" disabled={sendet} onclick={() => entscheiden("live")} title="Ohne neues Hören, ohne Sprecher">
            <i class="fa-solid fa-file-lines"></i> Live-Text als Transkript speichern</button>
        {/if}
        <button class="knopf still" disabled={sendet} onclick={() => entscheiden("fertig")}>Nur speichern</button>
      </div>
    </div>
  {:else}
    <div class="t-uhr">{marke(aufnahme.dauer_ms / 1000)}</div>
    <p class="rekorder-stand">
      <i class="fa-solid fa-circle" style="color:var(--gefahr); font-size:10px"></i>
      {aufnahme.pausiert ? "angehalten" : "nimmt auf"} · wird laufend auf diesem Gerät gesichert
    </p>
    {#if aufnahme.signal === "angehalten" && !aufnahme.pausiert}
      <p class="rekorder-warnung"><i class="fa-solid fa-triangle-exclamation"></i> Der Browser hält den Ton zurück.
        <button class="knopf klein" onclick={tonFortsetzen}>Ton freigeben</button></p>
    {:else if aufnahme.signal === "still" && !aufnahme.pausiert}
      <p class="rekorder-warnung"><i class="fa-solid fa-triangle-exclamation"></i> Seit Sekunden kommt kein Ton vom Mikrofon. Mikrofon prüfen
        oder unten ein anderes wählen.</p>
    {/if}
    <div class="t-pegel">
      {#each aufnahme.pegel as p, i (i)}<span style="height:{Math.max(4, p)}%"></span>{/each}
    </div>
    <div class="t-steuer">
      <button class="rund" title={aufnahme.pausiert ? "Weiter aufnehmen" : "Anhalten"} onclick={pause} disabled={sendet}>
        <i class="fa-solid {aufnahme.pausiert ? 'fa-play' : 'fa-pause'}"></i></button>
      <button class="stopp" title="Beenden und speichern" onclick={stopp} disabled={sendet}>
        <i class="fa-solid {sendet ? 'fa-circle-notch fa-spin' : 'fa-stop'}"></i></button>
      <button class="rund" title="Marker setzen" onclick={markerSetzen} disabled={sendet}><i class="fa-solid fa-flag"></i></button>
    </div>
    {#if aufnahme.marker.length}
      <p class="rekorder-stand">{aufnahme.marker.length} Marker: {aufnahme.marker.map((m) => marke(m.zeit)).join(", ")}</p>
    {/if}
    <div class="t-liste">
      <label class="t-zeile"><i class="fa-solid fa-pen"></i><span class="t-text"><span class="t-meta">Name</span>
        <input class="eingabe-roh" bind:value={name} /></span></label>
      <div class="t-zeile"><i class="fa-solid fa-microphone"></i>
        <span class="t-text"><span class="t-meta">Mikrofon (auch während der Aufnahme umschaltbar)</span>
          <Auswahl wert={aufnahme.geraet} optionen={geraete} onwahl={(g) => quelleWechseln(g)} /></span></div>
      <div class="t-zeile"><i class="fa-solid fa-closed-captioning"></i>
        <span class="t-text"><span class="t-name">Live mitschreiben</span><span class="t-meta">Text erscheint während der Aufnahme</span></span>
        <button class="schalter" class:an={aufnahme.live} aria-label="Live mitschreiben" aria-pressed={aufnahme.live}
                onclick={() => (aufnahme.live = !aufnahme.live)}></button></div>
    </div>
    {#if aufnahme.live}{@render mitschrift(aufnahme.mitschrift, aufnahme.liveStand)}{/if}
  {/if}
  {#if fehler || aufnahme.fehler}<div class="fehlertext">{fehler || aufnahme.fehler}</div>{/if}
</div>
