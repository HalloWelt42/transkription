<script lang="ts">
  // Aufnehmen mit dem Rekorder des Appkerns: die Aufnahme kommt nach Aufnahmen; danach entscheidet der Nutzer, ob sie
  // transkribiert wird, der Live-Text das Transkript wird, sie nur liegen bleibt oder in den Papierkorb geht.
  // Läuft sie als weiterer Teil eines Gesprächs (HELF-154, lib/fortsetzung), kommt sie neben dessen erste Aufnahme und
  // wird gleich transkribiert und unten angehängt; eine Entscheidung gibt es dann nicht.
  import { aufnahme, Auswahl, gehe, marke, Rekorder, Rueckfrage, type Gespeichert, type NachDerAufnahme } from "appkern-oberflaeche";
  import { fortsetzung } from "../lib/fortsetzung.svelte";
  import { sprachOptionen as sprachWahl } from "../lib/sprachen.svelte";
  import * as api from "../lib/api";
  import { ANZAHL_OPTIONEN, SPRECHER_WEGE, type SprecherWeg } from "../lib/sprecherwahl";

  let { kompakt = false, onfertig }: { kompakt?: boolean; onfertig?: (meldung: string) => void } = $props();

  let fehler = $state("");
  let sendet = $state(false);
  let sprache = $state("de");
  let sprecher = $state<SprecherWeg>("ohne");
  let anzahl = $state<number | null>(null);
  let verwerfenFrage = $state(false);
  const sprachOptionen = $derived(sprachWahl());
  const ziel = $derived(fortsetzung.ziel);

  async function ablegen(fertig: { daten: Blob; info: Gespeichert }): Promise<string> {
    if (!ziel) return (await api.aufnahmeAblegen(fertig.daten, fertig.info)).id;
    return (await api.teilAblegen(ziel.hauptId, fertig.daten, fertig.info)).teil.id;
  }

  // verworfen, solange sie lief: es entsteht kein Teil, die nächste Aufnahme ist wieder eine eigene
  function beendet(meldung: string) {
    if (!aufnahme.laeuft && !aufnahme.danach) fortsetzung.ziel = null;
    onfertig?.(meldung);
  }

  function zumGespraech() {
    const z = fortsetzung.ziel;
    aufnahme.danach = null;
    fortsetzung.ziel = null;
    if (z) gehe(`transkripte/${z.transkriptId}`);
  }

  async function verwerfenJetzt(d: NachDerAufnahme) {
    sendet = true;
    fehler = "";
    try {
      await api.aufnahmeLoeschen(d.id, false);
      aufnahme.danach = null;
      verwerfenFrage = false;
      onfertig?.(`${d.name} verworfen; sie liegt im Papierkorb der Kellerwolke.`);
    } catch (f) {
      fehler = (f as Error).message;
    } finally {
      sendet = false;
    }
  }

  async function entscheiden(d: NachDerAufnahme, wie: "genau" | "live" | "fertig") {
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

{#if ziel}
  <div class="hinweis-band fortsetzung-band"><i class="fa-solid fa-link"></i>
    <span><b>Teil {ziel.nummer} zu {ziel.name}</b>, schließt bei {marke(ziel.ab_s)} an</span></div>
{/if}
<Rekorder {kompakt} onfertig={beendet} ort={ziel ? ziel.name : "Aufnahmen"} {ablegen}
          liveHinweis="Der Text erscheint während der Aufnahme; genauer wird er beim Transkribieren.">
  {#snippet danach(d)}
    {#if ziel}
      <div class="entscheidung">
        <div>Teil {ziel.nummer} ({marke(d.dauer_s)}) hängt an <b>{ziel.name}</b> und wird jetzt transkribiert; der Text
          kommt unten an das Transkript.</div>
        <div class="knopfzeile"><button class="knopf primaer" onclick={zumGespraech}><i class="fa-solid fa-file-lines"></i> Zum Transkript</button></div>
      </div>
    {:else}
    <div class="entscheidung">
      <div class="entscheidung-optionen">
        <label>Sprache <Auswahl bind:wert={sprache} optionen={sprachOptionen} /></label>
        <label>Sprecher <Auswahl bind:wert={sprecher} optionen={SPRECHER_WEGE} /></label>
        {#if sprecher !== "ohne"}<label>Anzahl <Auswahl bind:wert={anzahl} optionen={ANZAHL_OPTIONEN} /></label>{/if}
      </div>
      <div class="knopfzeile">
        <button class="knopf primaer" disabled={sendet} onclick={() => entscheiden(d, "genau")}><i class="fa-solid fa-closed-captioning"></i> Transkribieren</button>
        {#if d.mitschrift.length}
          <button class="knopf" disabled={sendet} onclick={() => entscheiden(d, "live")} title="Ohne neues Hören, ohne Sprecher">
            <i class="fa-solid fa-file-lines"></i> Live-Text als Transkript speichern</button>
        {/if}
        <button class="knopf still" disabled={sendet} onclick={() => entscheiden(d, "fertig")}>Nur speichern</button>
        <button class="knopf still gefahr" style="margin-left:auto" disabled={sendet} onclick={() => (verwerfenFrage = true)}>
          <i class="fa-solid fa-trash-can"></i> Verwerfen</button>
      </div>
    </div>
    {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
    {#if verwerfenFrage}
      <Rueckfrage frage="Aufnahme verwerfen?" hinweis="Sie landet im Papierkorb der Kellerwolke und lässt sich dort zurückholen."
                  knopf="Verwerfen" beschaeftigt={sendet} onabbrechen={() => (verwerfenFrage = false)} onja={() => verwerfenJetzt(d)} />
    {/if}
    {/if}
  {/snippet}
</Rekorder>
