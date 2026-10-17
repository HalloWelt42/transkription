<script lang="ts">
  // Eine Aufnahme anhören, auch ohne Transkript (Entwurf 1b am Rechner und am Telefon): dieselbe Spieleransicht wie
  // beim Transkript (Abspielfassung, Wellenform aus dem Ton, Marker, Tasten), an der Stelle des Textes die Wahl zum
  // Transkribieren; rechts Marker, Datei und Papierkorb mit Rückfrage. Transkribiert wird nur, wenn der Nutzer startet.
  import { onMount } from "svelte";
  import { Auswahl, beiAuftrag, gehe, geraet, Leiste, leisteOeffnen, navigation, wann } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { ANZAHL_OPTIONEN, SPRECHER_WEGE, type SprecherWeg } from "../lib/sprecherwahl";
  import type { Aufnahme } from "../lib/typen";
  import { groesse, marke, SPRACHEN } from "../lib/zeit";
  import Rueckfrage from "./Rueckfrage.svelte";
  import Spieler from "./Spieler.svelte";

  let { id }: { id: string } = $props();

  let a = $state<Aufnahme | null>(null);
  let welle = $state<number[] | null>(null);
  let fehler = $state("");
  let meldung = $state("");
  let zeit = $state(0);
  let laeuft = $state(false);
  let spieler = $state<Spieler>();
  let sprache = $state("de");
  let sprecher = $state<SprecherWeg>("ohne");
  let anzahl = $state<number | null>(null);
  let startet = $state(false);
  let markerTitel = $state("");
  let markerOffen = $state(false);
  let loeschenFrage = $state(false);
  let loescht = $state(false);

  const sprachOptionen = Object.entries(SPRACHEN).map(([wert, titel]) => ({ wert, titel }));
  const ordner = $derived(a ? a.pfad.split("/").slice(0, -1).join("/") : "");
  const format = $derived(a ? (a.name.split(".").pop() ?? "").toUpperCase() : "");
  const laufend = $derived(a?.stand === "laeuft" || a?.stand === "wartet");

  async function laden() {
    fehler = "";
    try {
      a = await api.aufnahme(id);
      navigation.titel = a.name;
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  onMount(() => {
    void laden();
    void api.wellenform(id).then((w) => (welle = w)).catch(() => {});
    void (async () => {
      try {
        sprache = (await api.einstellung<string>("sprache")) ?? "de";
        sprecher = (await api.einstellung<SprecherWeg>("sprecher_weg")) ?? "ohne";
      } catch {
        // Vorgaben bleiben
      }
    })();
    return beiAuftrag((auftrag) => {
      if (auftrag.art !== "transkribieren" || String(auftrag.eingabe.quelle_id) !== id) return;
      void laden();
      if (auftrag.zustand === "fertig") meldung = "Transkript fertig.";
      else if (auftrag.zustand === "fehler") fehler = auftrag.fehler ?? "Transkribieren gescheitert";
    });
  });

  async function transkribieren() {
    if (!a) return;
    startet = true;
    fehler = "";
    try {
      await api.transkribieren({ quelle_id: a.id, sprache, sprecher, anzahl: sprecher !== "ohne" ? anzahl : null });
      meldung = "Wird transkribiert; der Stand steht hier und unter Aufträge.";
      await laden();
    } catch (f) {
      fehler = (f as Error).message;
    } finally {
      startet = false;
    }
  }

  async function markerSpeichern(liste: { zeit: number; titel: string }[]) {
    if (!a) return;
    try {
      const neu = await api.aufnahmeMarker(a.id, liste);
      a = { ...a, marker: neu };
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  function markerSetzen() {
    const titel = markerTitel.trim();
    if (!titel || !a) return;
    void markerSpeichern([...a.marker, { zeit: Math.round(zeit * 10) / 10, titel }].sort((x, y) => x.zeit - y.zeit));
    markerTitel = "";
    markerOffen = false;
  }

  async function loeschen(mitTranskripten: boolean) {
    if (!a) return;
    loescht = true;
    try {
      await api.aufnahmeLoeschen(a.id, mitTranskripten);
      gehe("aufnahmen");
    } catch (f) {
      fehler = (f as Error).message;
      loescht = false;
    }
  }

  const springen = (t: number) => spieler?.springe(t, true);
</script>

{#snippet transkriptWahl()}
  {#if a && a.transkripte.length}
    <h2>Transkribiert</h2>
    <p>Zu dieser Aufnahme gibt es {a.transkripte.length === 1 ? "ein Transkript" : `${a.transkripte.length} Transkripte`}.</p>
    <div class="knopfzeile">
      {#each a.transkripte as t (t.id)}
        <button class="knopf primaer" onclick={() => gehe(`transkripte/${t.id}`)}><i class="fa-solid fa-file-lines"></i> {t.name}</button>
      {/each}
    </div>
  {:else if a && laufend}
    <h2>Wird transkribiert</h2>
    <p><i class="fa-solid fa-circle-notch fa-spin"></i> {a.auftrag?.schritt || "wartet"}{a.auftrag?.fortschritt != null ? ` (${Math.round(a.auftrag.fortschritt * 100)} %)` : ""}</p>
  {:else}
    <h2>Noch kein Transkript</h2>
    <p>Abspielen, springen und Marker setzen geht schon. Transkribiert wird erst, wenn du es hier startest.</p>
  {/if}
{/snippet}

{#snippet markerListe()}
  <div class="liste-klein">
    {#each a?.marker ?? [] as m, i (i)}
      <div class="marker-eintrag"><button class="zeit" onclick={() => springen(m.zeit)}>{marke(m.zeit)}</button>
        <span class="marker-titel"><i class="fa-solid fa-flag" style="color:var(--warn)"></i> {m.titel}</span>
        <button class="weg" title="Marker entfernen" onclick={() => markerSpeichern((a?.marker ?? []).filter((_, n) => n !== i))}><i class="fa-solid fa-xmark"></i></button></div>
    {:else}
      <p class="leer-zeile">Noch keine Marker.</p>
    {/each}
  </div>
  {#if markerOffen}
    <label class="eingabe klein-eingabe" style="margin-top:8px"><span class="zeit-marke">{marke(zeit)}</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input bind:value={markerTitel} placeholder="Titel des Markers" aria-label="Titel des Markers" autofocus
             onkeydown={(e) => { if (e.key === "Enter") markerSetzen(); else if (e.key === "Escape") markerOffen = false; }} /></label>
    <div class="knopfreihe" style="margin-top:8px">
      <button class="knopf klein primaer" onclick={markerSetzen} disabled={!markerTitel.trim()}>Setzen</button>
      <button class="knopf klein still" onclick={() => (markerOffen = false)}>Abbrechen</button>
    </div>
  {:else}
    <button class="knopf klein still" style="margin-top:6px" onclick={() => (markerOffen = true)}><i class="fa-solid fa-plus"></i> Marker bei {marke(zeit)}</button>
  {/if}
{/snippet}

{#snippet papierkorb()}
  {#if loeschenFrage && a}
    <Rueckfrage frage={`${a.name} in den Papierkorb?`} hinweis="Landet im Papierkorb der Kellerwolke und lässt sich dort zurückholen."
                knopf="In den Papierkorb" schalter={a.transkripte.length ? "das Transkript dazu auch" : ""} beschaeftigt={loescht}
                onabbrechen={() => (loeschenFrage = false)} onja={(mit) => loeschen(mit && a!.transkripte.length > 0)} />
  {:else}
    <button class="knopf klein still" onclick={() => (loeschenFrage = true)}><i class="fa-solid fa-trash-can"></i> In den Papierkorb</button>
  {/if}
{/snippet}

{#if !a}
  {#if fehler}
    <div class="seiten-kopf"><button class="knopf still" onclick={() => gehe("aufnahmen")}><i class="fa-solid fa-chevron-left"></i> Aufnahmen</button></div>
    <div class="rollfeld"><div class="fehlertext">{fehler}</div></div>
  {:else}<div class="leer">Lädt ...</div>{/if}
{:else if geraet.mobil}
  <div class="t-ansicht">
    {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
    {#if meldung}<p class="leer" style="padding:6px 4px">{meldung}</p>{/if}
    {#if !a.transkripte.length && !laufend}
      <div class="t-gruppe">Noch kein Transkript</div>
      <div class="t-liste">
        <div class="t-zeile"><i class="fa-solid fa-language"></i><span class="t-text"><span class="t-meta">Sprache</span>
          <Auswahl bind:wert={sprache} optionen={sprachOptionen} /></span></div>
        <div class="t-zeile"><i class="fa-solid fa-user-group"></i><span class="t-text"><span class="t-meta">Sprecher</span>
          <Auswahl bind:wert={sprecher} optionen={SPRECHER_WEGE} /></span></div>
        {#if sprecher !== "ohne"}
          <div class="t-zeile"><i class="fa-solid fa-hashtag"></i><span class="t-text"><span class="t-meta">Anzahl</span>
            <Auswahl bind:wert={anzahl} optionen={ANZAHL_OPTIONEN} /></span></div>
        {/if}
      </div>
      <button class="knopf primaer t-breit" onclick={transkribieren} disabled={startet}>
        <i class="fa-solid {startet ? 'fa-circle-notch fa-spin' : 'fa-play'}"></i> Transkribieren</button>
    {:else}
      <div class="ohne-text">{@render transkriptWahl()}</div>
    {/if}
    <div class="t-gruppe">Marker</div>
    <div class="karte t-karte">{@render markerListe()}</div>
    <div class="t-loeschen">{@render papierkorb()}</div>
    <Spieler bind:this={spieler} src={api.aufnahmeTonAdresse(a.id)} dauer={a.dauer_s ?? 0} wellenform={welle}
             marker={a.marker.map((m) => m.zeit)} bind:zeit bind:laeuft kompakt />
  </div>
{:else}
  <div class="geruest-innen">
    <section class="seite">
      <div class="seiten-kopf">
        <button class="knopf still" style="padding:0 6px" onclick={() => gehe("aufnahmen")}><i class="fa-solid fa-chevron-left"></i> Aufnahmen</button>
        <h1 class="titel-lang" title={a.name}>{a.name}</h1>
        <button class="knopf nur-schmal" title="Marker, Datei, Papierkorb" onclick={leisteOeffnen}><i class="fa-solid fa-table-columns"></i> Leiste</button>
      </div>
      <Spieler bind:this={spieler} src={api.aufnahmeTonAdresse(a.id)} dauer={a.dauer_s ?? 0} wellenform={welle}
               marker={a.marker.map((m) => m.zeit)} bind:zeit bind:laeuft />
      <div class="rollfeld" style="padding-top:14px">
        {#if fehler}<div class="fehlertext" style="margin-bottom:12px">{fehler}</div>{/if}
        {#if meldung}<p class="leer" style="padding:0 4px 12px; text-align:left">{meldung}</p>{/if}
        <div class="ohne-text">
          {@render transkriptWahl()}
          {#if !a.transkripte.length && !laufend}
            <div class="optionen" style="margin:0">
              <label>Sprache <Auswahl bind:wert={sprache} optionen={sprachOptionen} /></label>
              <label>Sprecher <Auswahl bind:wert={sprecher} optionen={SPRECHER_WEGE} /></label>
              {#if sprecher !== "ohne"}<label>Anzahl <Auswahl bind:wert={anzahl} optionen={ANZAHL_OPTIONEN} /></label>{/if}
              <span class="knopfzeile" style="margin-left:auto">
                <button class="knopf primaer" onclick={transkribieren} disabled={startet}>
                  <i class="fa-solid {startet ? 'fa-circle-notch fa-spin' : 'fa-play'}"></i> Transkribieren</button>
              </span>
            </div>
          {/if}
        </div>
      </div>
    </section>
    <Leiste>
      <div class="rollfeld leiste-inhalt">
        <div class="gruppe"><h3>Marker</h3>{@render markerListe()}</div>
        <div class="gruppe">
          <h3>Datei</h3>
          <div class="liste-klein">
            <div><span class="zeit">Ordner</span><span>{ordner}</span></div>
            <div><span class="zeit">Art</span><span>{[format, a.groesse != null ? groesse(a.groesse) : "", wann(a.geaendert_am)].filter(Boolean).join(" · ")}</span></div>
          </div>
        </div>
        <div class="gruppe">
          <h3>Löschen</h3>
          {@render papierkorb()}
          {#if !loeschenFrage}<p class="leer-zeile" style="margin-top:8px">Landet im Papierkorb der Kellerwolke und lässt sich dort zurückholen.</p>{/if}
        </div>
      </div>
    </Leiste>
  </div>
{/if}
