<script lang="ts">
  // Aufnehmen mit dem Rekorder des Appkerns: die Aufnahme kommt nach Aufnahmen; danach entscheidet der Nutzer, ob sie
  // transkribiert wird, der Live-Text das Transkript wird, sie nur liegen bleibt oder in den Papierkorb geht.
  // "Weiter aufnehmen" (HELF-154, lib/fortsetzung) gibt es gleich nach dem Beenden: der neue Ton kommt hinten an dieselbe
  // Tondatei; hat sie ein Transkript, wird nur der neue Text gehört und angehängt, sonst bleibt die Wahl wie nach jeder
  // Aufnahme (die Tondatei ist dann eben länger).
  import { aufnahme, Auswahl, gehe, marke, Rekorder, Rueckfrage, type Gespeichert, type NachDerAufnahme } from "appkern-oberflaeche";
  import { fortsetzung, weiterAufnehmen } from "../lib/fortsetzung.svelte";
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
    await api.fortsetzen(ziel.aufnahmeId, fertig.daten, fertig.info);
    return ziel.aufnahmeId;
  }

  // nach dem Beenden noch mehr sagen: an dieselbe Tondatei, ab ihrem jetzigen Ende
  async function weiter(d: NachDerAufnahme) {
    const vorher = fortsetzung.ziel;
    await weiterAufnehmen({ aufnahmeId: d.id, name: vorher?.name ?? d.name,
                            ab_s: vorher ? (vorher.ab_s != null ? vorher.ab_s + d.dauer_s : null) : d.dauer_s,
                            transkript: vorher?.transkript ?? false, zurueck: vorher?.zurueck ?? `aufnahmen/${d.id}` });
  }

  // verworfen, solange sie lief: es entsteht kein Teil, die nächste Aufnahme ist wieder eine eigene
  function beendet(meldung: string) {
    if (!aufnahme.laeuft && !aufnahme.danach) fortsetzung.ziel = null;
    onfertig?.(meldung);
  }

  function zurueck() {
    const z = fortsetzung.ziel;
    aufnahme.danach = null;
    fortsetzung.ziel = null;
    if (z) gehe(z.zurueck);
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
        const name = ziel?.name ?? d.name;
        await api.transkribieren({ quelle_id: d.id, name, sprache, sprecher, anzahl: sprecher !== "ohne" ? anzahl : null });
        onfertig?.(`${name} wird transkribiert; der Stand steht in der Liste und unter Aufträge.`);
      } else if (wie === "live") {
        await api.ausMitschrift({ quelle_id: d.id, name: d.name, sprache: sprache === "auto" ? "de" : sprache, stuecke: d.mitschrift });
        onfertig?.(`${d.name}: Transkript aus der Live-Mitschrift angelegt.`);
      } else {
        onfertig?.(`${d.name} liegt in Aufnahmen.`);
      }
      aufnahme.danach = null;
      fortsetzung.ziel = null;
    } catch (f) {
      fehler = (f as Error).message;
    } finally {
      sendet = false;
    }
  }
</script>

{#if ziel && !aufnahme.danach}
  <div class="hinweis-band fortsetzung-band"><i class="fa-solid fa-link"></i>
    <span><b>Weiter in {ziel.name}</b>{ziel.ab_s != null ? `, schließt bei ${marke(ziel.ab_s)} an` : ", hinten angehängt"}</span></div>
{/if}
<Rekorder {kompakt} onfertig={beendet} ort={ziel ? `${ziel.name} (hinten angehängt)` : "Aufnahmen"} {ablegen}
          liveHinweis="Der Text erscheint während der Aufnahme; genauer wird er beim Transkribieren.">
  {#snippet danach(d)}
    <div class="weiter-zeile">
      <button class="knopf weiter-knopf" disabled={sendet} onclick={() => weiter(d)}>
        <i class="fa-solid fa-microphone"></i> Weiter aufnehmen</button>
      <span class="unter">{ziel ? `${marke(d.dauer_s)} hängen an ${ziel.name}${ziel.ab_s != null ? `, jetzt ${marke(ziel.ab_s + d.dauer_s)} lang` : ""}.` : "Noch mehr sagen: kommt hinten an dieselbe Aufnahme."}</span>
    </div>
    {#if ziel?.transkript}
      <div class="entscheidung">
        <div>Der neue Text wird gehört und unten an das Transkript gehängt.</div>
        <div class="knopfzeile"><button class="knopf primaer" onclick={zurueck}><i class="fa-solid fa-file-lines"></i> Zum Transkript</button></div>
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
        {#if d.mitschrift.length && !ziel}
          <button class="knopf" disabled={sendet} onclick={() => entscheiden(d, "live")} title="Ohne neues Hören, ohne Sprecher">
            <i class="fa-solid fa-file-lines"></i> Live-Text als Transkript speichern</button>
        {/if}
        <button class="knopf still" disabled={sendet} onclick={() => { if (ziel) zurueck(); else void entscheiden(d, "fertig"); }}>Nur speichern</button>
        {#if !ziel}
          <button class="knopf still gefahr" style="margin-left:auto" disabled={sendet} onclick={() => (verwerfenFrage = true)}>
            <i class="fa-solid fa-trash-can"></i> Verwerfen</button>
        {/if}
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
