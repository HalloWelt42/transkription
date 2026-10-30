<script lang="ts">
  // Aufnehmen mit dem Rekorder des Appkerns: die Aufnahme kommt nach Aufnahmen; danach entscheidet der Nutzer, ob sie
  // transkribiert wird, der Live-Text das Transkript wird, sie nur liegen bleibt oder in den Papierkorb geht.
  import { aufnahme, Auswahl, Rekorder, Rueckfrage, type NachDerAufnahme } from "appkern-oberflaeche";
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

<Rekorder {kompakt} {onfertig} ort="Aufnahmen" ablegen={async (fertig) => (await api.aufnahmeAblegen(fertig.daten, fertig.info)).id}
          liveHinweis="Der Text erscheint während der Aufnahme; genauer wird er beim Transkribieren.">
  {#snippet danach(d)}
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
  {/snippet}
</Rekorder>
