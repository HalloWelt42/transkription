<script lang="ts">
  // Fachwörter-Wörterbuch: Wörter in ihrer richtigen Schreibweise, die dem Hördienst bei jedem Hören als Hinweis
  // mitgehen. Einsehen, hinzufügen, entfernen (jede Änderung gilt sofort). Beiläufig gepflegt wird es beim Bearbeiten
  // eines Transkripts: korrigierte Wörter schlägt die App zur Aufnahme vor, aufgenommen wird nur, was du bestätigst.
  import { onMount } from "svelte";
  import { geraet, wann } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import type { WoerterbuchStand } from "../lib/typen";

  let stand = $state<WoerterbuchStand | null>(null);
  let neu = $state("");
  let suche = $state("");
  let fehler = $state("");
  let arbeitet = $state(false);

  const sichtbar = $derived((stand?.woerter ?? []).filter((w) => !suche.trim() || w.toLowerCase().includes(suche.trim().toLowerCase())));

  async function machen(arbeit: () => Promise<WoerterbuchStand>) {
    fehler = "";
    arbeitet = true;
    try {
      stand = await arbeit();
    } catch (f) {
      fehler = (f as Error).message;
    } finally {
      arbeitet = false;
    }
  }

  onMount(() => void machen(api.woerterbuch));

  function hinzufuegen() {
    const woerter = neu.split(",").map((w) => w.trim()).filter(Boolean);
    if (!woerter.length) return;
    void machen(() => api.woerterAufnehmen(woerter)).then(() => (neu = ""));
  }

  function entfernen(wort: string) {
    if (!stand) return;
    const rest = stand.woerter.filter((w) => w !== wort);
    void machen(() => api.woerterbuchSetzen(rest));
  }
</script>

{#snippet inhalt()}
  <p class="wb-erklaerung">Wörter in ihrer richtigen Schreibweise, etwa Namen und Fachbegriffe. Sie gehen dem Hördienst bei jedem
    Hören als Hinweis mit, damit er sie so schreibt. Korrigierst du im Bearbeiten ein Wort, schlägt die App vor, es hier
    aufzunehmen; von selbst kommt nichts dazu.</p>
  <div class="knopfzeile wb-eingabe">
    <label class="eingabe wb-feld"><i class="fa-solid fa-plus"></i>
      <input placeholder="Neues Wort" title="Mehrere Wörter mit Komma trennen" bind:value={neu} enterkeyhint="done"
             onkeydown={(e) => e.key === "Enter" && hinzufuegen()} aria-label="Wort hinzufügen" /></label>
    <button class="knopf primaer" disabled={!neu.trim() || arbeitet} onclick={hinzufuegen}>Hinzufügen</button>
  </div>
  {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
  {#if stand}
    <div class="wb-woerter">
      {#each sichtbar as w (w)}
        <span class="wb-wort">{w}<button class="wb-weg" title="{w} entfernen" aria-label="{w} entfernen" disabled={arbeitet}
                                         onclick={() => entfernen(w)}><i class="fa-solid fa-xmark"></i></button></span>
      {:else}
        <p class="leer">{suche ? "Kein Wort gefunden." : "Noch keine Wörter."}</p>
      {/each}
    </div>
    <p class="hilfe-zeile">{stand.woerter.length === 1 ? "1 Wort" : `${stand.woerter.length} Wörter`}{stand.geaendert_am
      ? `, zuletzt geändert ${wann(stand.geaendert_am)}` : ", Startinhalt (noch nicht gespeichert)"}. Liegt in der Kellerwolke als Fachwörter.json.</p>
  {:else if !fehler}<p class="leer">Lädt ...</p>{/if}
{/snippet}

{#if geraet.mobil}
  <div class="wb-mobil">{@render inhalt()}</div>
{:else}
  <div class="geruest-innen">
    <section class="seite">
      <div class="seiten-kopf">
        <h1>Wörterbuch</h1>
        <label class="suche wb-suche"><i class="fa-solid fa-magnifying-glass"></i>
          <input class="eingabe-roh" placeholder="Wort suchen" bind:value={suche} /></label>
      </div>
      <div class="rollfeld"><div class="text-flaeche">{@render inhalt()}</div></div>
    </section>
  </div>
{/if}
