<script lang="ts">
  // Alle Dateien der Kellerwolke als Quelle (Entwurf mockups/verbund.html 6b am Rechner, 6e am Telefon): blättern wie
  // dort, wählbar sind Ton und Video ohne Transkript. Die App sieht hier nur Namen; erst die Wahl stellt je Datei eine
  // Anfrage, mit deren Recht der Auftrag die Datei liest und das Transkript daneben legt. Transkribierte öffnet "Öffnen"
  // über eine Anfrage zum Ansehen und Bearbeiten. Begleiter erscheinen nicht als eigene Zeilen, nur als Stand der Datei.
  import { onMount } from "svelte";
  import { Auswahl, beiAuftrag, daneben, gehe, geraet, groesse, hole, istMedium, navigation, SPRACHEN, waehlen,
           wahl, wann, type Auftrag, type Seite, type WahlEintrag, type WahlSeite } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { ANZAHL_OPTIONEN, SPRECHER_WEGE, type SprecherWeg } from "../lib/sprecherwahl";

  // `ordner`: der gezeigte Ordner (null: "Meine Dateien"); `kette` meldet den Weg dorthin an die Seite (Chips, Hoch).
  let { ordner, suche = "", kette = $bindable([]) }: { ordner: string | null; suche?: string; kette?: WahlSeite["kette"] } = $props();

  let seite = $state<WahlSeite | null>(null);
  let laufend = $state<Record<string, Auftrag>>({});   // Aufnahme -> laufender Auftrag zum Transkribieren
  let gewaehlt = $state<string[]>([]);
  let sprache = $state("de");
  let sprecher = $state<SprecherWeg>("ohne");
  let anzahl = $state<number | null>(null);
  let fehler = $state("");
  let meldung = $state("");
  let startet = $state(false);
  const SEITE = 100;   // Zeilen je Seite; ein Ordner kann groß sein
  let ab = $state(0);

  const sprachOptionen = Object.entries(SPRACHEN).map(([wert, titel]) => ({ wert, titel }));

  async function laden() {
    fehler = "";
    try {
      seite = await wahl(ordner);
      kette = seite.kette;
      if (geraet.mobil) navigation.titel = seite.kette.length > 1 ? seite.kette.at(-1)!.name : "Meine Dateien";
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  async function laufendeLaden() {
    const offen = await hole<Seite<Auftrag>>("/auftraege?zustand=wartet&zustand=laeuft&grenze=200");
    laufend = Object.fromEntries(offen.eintraege.filter((a) => a.art === "transkribieren").map((a) => [String(a.eingabe.quelle_id), a]));
  }

  onMount(() => {
    if (geraet.mobil) navigation.kennzeichen = { symbol: "fa-cloud", text: "Kellerwolke" };
    void laden();
    void laufendeLaden().catch(() => {});
    void (async () => {
      sprache = (await api.einstellung<string>("sprache")) ?? "de";
      sprecher = (await api.einstellung<SprecherWeg>("sprecher_weg")) ?? "ohne";
    })().catch(() => {});
    return beiAuftrag((a) => {
      if (a.art !== "transkribieren") return;
      const quelle = String(a.eingabe.quelle_id);
      if (a.zustand === "wartet" || a.zustand === "laeuft") laufend = { ...laufend, [quelle]: a };
      else if (laufend[quelle]) {
        const { [quelle]: _fertig, ...rest } = laufend;
        laufend = rest;
        if (!Object.keys(rest).length) meldung = "";      // "wird transkribiert" stimmt nicht mehr
        void laden().then(() => {
          if (a.zustand !== "fertig") fehler = a.fehler ?? "Transkribieren gescheitert";
        });
      }
    });
  });

  // Begleiter je Hauptdatei (aus derselben Liste; sie liegen im selben Ordner)
  const begleiter = $derived.by(() => {
    const je: Record<string, WahlEintrag[]> = {};
    for (const e of seite?.eintraege ?? []) if (e.haupt_id) (je[e.haupt_id] ??= []).push(e);
    return je;
  });
  const sichtbar = $derived((seite?.eintraege ?? []).filter((e) => !e.haupt_id && (!suche.trim() || e.name.toLowerCase().includes(suche.trim().toLowerCase()))));
  const zeilen = $derived(sichtbar.slice(ab, ab + SEITE));
  const ordnerZeilen = $derived(zeilen.filter((e) => e.typ === "ordner"));
  const dateien = $derived(zeilen.filter((e) => e.typ === "datei"));
  const medien = $derived(dateien.filter((e) => istMedium(e.inhaltstyp)));

  let letzteSuche = "";
  $effect(() => {
    if (suche !== letzteSuche) {
      letzteSuche = suche;
      ab = 0;
    }
  });

  type Stand = "ohne" | "laeuft" | "transkribiert";
  function stand(e: WahlEintrag): Stand {
    if (laufend[e.id]) return "laeuft";
    return (begleiter[e.id] ?? []).some((b) => b.rolle === "transkript") ? "transkribiert" : "ohne";
  }

  function standText(e: WahlEintrag): string {
    const s = stand(e);
    if (s === "transkribiert") return "transkribiert";
    if (s === "laeuft") {
      const a = laufend[e.id];
      return a.zustand === "wartet" ? "wartet" : `${a.schritt?.split(",")[0] || "läuft"}${a.fortschritt != null ? ` ${Math.round(a.fortschritt * 100)} %` : ""}`;
    }
    return "ohne Transkript";
  }

  function metazeile(e: WahlEintrag): string {
    if (e.typ === "ordner") return ["Ordner", e.kinder_anzahl != null ? `${e.kinder_anzahl} ${e.kinder_anzahl === 1 ? "Eintrag" : "Einträge"}` : ""].filter(Boolean).join(" · ");
    if (!istMedium(e.inhaltstyp)) return ["kein Ton", groesse(e.groesse)].filter(Boolean).join(" · ");
    const format = e.name.includes(".") ? e.name.slice(e.name.lastIndexOf(".") + 1).toUpperCase() : "";
    return [format, groesse(e.groesse), wann(e.geaendert_am), daneben((begleiter[e.id] ?? []).map((b) => b.rolle))].filter(Boolean).join(" · ");
  }

  function symbol(e: WahlEintrag): string {
    const typ = e.inhaltstyp ?? "";
    if (e.typ === "ordner") return "fa-folder";
    if (typ.startsWith("video/")) return "fa-file-video";
    if (typ.startsWith("audio/")) return "fa-file-audio";
    if (typ.startsWith("image/")) return "fa-file-image";
    return typ.startsWith("text/") ? "fa-file-lines" : "fa-file";
  }

  const hinein = (e: WahlEintrag) => gehe(`aufnahmen/kellerwolke/${e.id}`);

  function umschalten(e: WahlEintrag) {
    if (stand(e) !== "ohne") return;
    gewaehlt = gewaehlt.includes(e.id) ? gewaehlt.filter((x) => x !== e.id) : [...gewaehlt, e.id];
  }

  async function oeffnen(e: WahlEintrag) {
    fehler = "";
    try {
      const { anfrage } = await waehlen(e.id, "oeffnen");
      gehe(`anfrage/${anfrage.id}`);
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  // Zeile antippen (Telefon) oder anklicken: Ordner hinein, transkribierte öffnen, sonst wählen
  function antippen(e: WahlEintrag) {
    if (e.typ === "ordner") hinein(e);
    else if (stand(e) === "transkribiert") void oeffnen(e);
    else umschalten(e);
  }

  async function transkribieren() {
    startet = true;
    fehler = "";
    try {
      const zahl = gewaehlt.length;
      await api.ausKellerwolke({ knoten_ids: gewaehlt, sprache, sprecher, anzahl: sprecher !== "ohne" ? anzahl : null });
      meldung = `${zahl} ${zahl === 1 ? "Datei wird" : "Dateien werden"} transkribiert; das Transkript kommt jeweils neben die Datei.`;
      gewaehlt = [];
      await laufendeLaden();
    } catch (f) {
      fehler = (f as Error).message;
    } finally {
      startet = false;
    }
  }
</script>

{#snippet pille(e: WahlEintrag)}
  {@const s = stand(e)}
  <span class="stand-pille {s === 'transkribiert' ? 'fertig' : s === 'laeuft' ? 'laeuft' : 'offen'}">
    {#if s === "laeuft"}<i class="fa-solid fa-circle-notch fa-spin"></i>{/if} {standText(e)}</span>
{/snippet}

{#snippet seitenzeile()}
  {#if sichtbar.length > SEITE}
    <div class="seitenzeile"><span>{ab + 1} bis {Math.min(ab + SEITE, sichtbar.length)} von {sichtbar.length}</span>
      <button class="knopf" disabled={ab === 0} onclick={() => (ab = Math.max(0, ab - SEITE))}><i class="fa-solid fa-chevron-left"></i> Zurück</button>
      <button class="knopf" disabled={ab + SEITE >= sichtbar.length} onclick={() => (ab += SEITE)}>Weiter <i class="fa-solid fa-chevron-right"></i></button>
    </div>
  {/if}
{/snippet}

{#if geraet.mobil}
  <div class="t-ansicht">
    <div class="hinweis-band"><i class="fa-solid fa-shield-halved"></i><span>Lesen darf die App nur, was du wählst, und nur für den Auftrag.</span></div>
    {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
    {#if meldung}<p class="leer" style="padding:6px 4px">{meldung}</p>{/if}
    {#if ordnerZeilen.length}
      <div class="t-gruppe">Ordner</div>
      <div class="t-liste">
        {#each ordnerZeilen as e (e.id)}
          <button class="t-zeile" onclick={() => hinein(e)}><i class="fa-solid fa-folder"></i>
            <span class="t-text"><span class="t-name">{e.name}</span><span class="t-meta">{metazeile(e).replace(/^Ordner · /, "")}</span></span>
            <i class="fa-solid fa-chevron-right" style="color:var(--text-3)"></i></button>
        {/each}
      </div>
    {/if}
    <div class="t-gruppe">Ton und Video</div>
    <div class="t-liste">
      {#each medien as e (e.id)}
        {@const s = stand(e)}
        <button class="t-zeile" class:gewaehlt={gewaehlt.includes(e.id)} onclick={() => antippen(e)}>
          {#if gewaehlt.includes(e.id)}<i class="fa-solid fa-circle-check" style="color:var(--akzent)"></i>
          {:else}<i class="fa-solid {symbol(e)}"></i>{/if}
          <span class="t-text"><span class="t-name">{e.name}</span>
            <span class="t-meta">{[groesse(e.groesse), s === "transkribiert" ? "transkribiert, antippen öffnet" : standText(e)].filter(Boolean).join(" · ")}</span></span>
          {#if s === "transkribiert"}<i class="fa-solid fa-chevron-right" style="color:var(--text-3)"></i>
          {:else if s === "laeuft"}<span class="stand-pille laeuft"><i class="fa-solid fa-circle-notch fa-spin"></i></span>{/if}
        </button>
      {:else}
        <div class="leer">{seite ? "Hier liegt kein Ton und kein Video." : "Lädt ..."}</div>
      {/each}
    </div>
    {@render seitenzeile()}
    {#if gewaehlt.length}
      <div class="t-spieler t-wahlleiste">
        <b>{gewaehlt.length} gewählt</b>
        <button class="knopf primaer" onclick={transkribieren} disabled={startet}>
          <i class="fa-solid {startet ? 'fa-circle-notch fa-spin' : 'fa-play'}"></i> Transkribieren</button>
      </div>
    {/if}
  </div>
{:else}
  <div class="hinweis-band"><i class="fa-solid fa-shield-halved"></i>
    <span>Hier siehst du nur Namen. Lesen darf die App eine Datei erst, wenn du sie zum Transkribieren wählst, und nur bis der
      Auftrag fertig ist. Das Transkript liegt dann neben der Datei.</span></div>
  {#if meldung}<p class="leer" style="padding:6px 4px 14px; text-align:left">{meldung}</p>{/if}
  {#if fehler}<div class="fehlertext" style="margin-bottom:12px">{fehler}</div>{/if}
  {#if gewaehlt.length}
    <div class="optionen">
      <span class="titel"><i class="fa-solid fa-closed-captioning"></i> {gewaehlt.length} gewählt</span>
      <label>Sprache <Auswahl bind:wert={sprache} optionen={sprachOptionen} /></label>
      <label>Sprecher <Auswahl bind:wert={sprecher} optionen={SPRECHER_WEGE} /></label>
      {#if sprecher !== "ohne"}<label>Anzahl <Auswahl bind:wert={anzahl} optionen={ANZAHL_OPTIONEN} /></label>{/if}
      <span class="knopfzeile" style="margin-left:auto">
        <button class="knopf still" onclick={() => (gewaehlt = [])}>Auswahl aufheben</button>
        <button class="knopf primaer" onclick={transkribieren} disabled={startet}>
          <i class="fa-solid {startet ? 'fa-circle-notch fa-spin' : 'fa-play'}"></i> Transkribieren</button>
      </span>
    </div>
  {/if}
  {#each zeilen as e (e.id)}
    {#if e.typ === "ordner"}
      <div class="zeile ordner-zeile" role="button" tabindex="0" onclick={() => hinein(e)} onkeydown={(k) => k.key === "Enter" && hinein(e)}>
        <span class="art"><i class="fa-solid fa-folder"></i></span>
        <div style="min-width:0"><div class="name">{e.name}</div><div class="meta">{metazeile(e)}</div></div>
        <span></span><i class="fa-solid fa-chevron-right" style="color:var(--text-3); padding-right:10px"></i>
      </div>
    {:else if istMedium(e.inhaltstyp)}
      <div class="zeile" class:gewaehlt={gewaehlt.includes(e.id)} role="button" tabindex="0"
           onclick={() => umschalten(e)} onkeydown={(k) => k.key === "Enter" && umschalten(e)}>
        <span class="art"><i class="fa-solid {symbol(e)}"></i></span>
        <div style="min-width:0"><div class="name">{e.name}</div><div class="meta">{metazeile(e)}</div></div>
        {@render pille(e)}
        {#if stand(e) === "transkribiert"}
          <button class="knopf still" title="In der App öffnen" onclick={(k) => { k.stopPropagation(); void oeffnen(e); }}>
            <i class="fa-solid fa-up-right-from-square"></i> Öffnen</button>
        {:else}<span></span>{/if}
      </div>
    {:else}
      <div class="zeile nicht-waehlbar" title="Nur Ton und Video lassen sich transkribieren">
        <span class="art"><i class="fa-solid {symbol(e)}"></i></span>
        <div style="min-width:0"><div class="name">{e.name}</div><div class="meta">{metazeile(e)}</div></div>
        <span></span><span></span>
      </div>
    {/if}
  {:else}
    {#if seite}<p class="leer">{suche ? "Nichts gefunden." : "Dieser Ordner ist leer."}</p>{:else if !fehler}<p class="leer">Lädt ...</p>{/if}
  {/each}
  {#if medien.some((e) => stand(e) === "ohne")}
    <p class="leer" style="padding:14px">Ton und Video ohne Transkript anklicken, um sie zum Transkribieren zu wählen.</p>
  {/if}
  {@render seitenzeile()}
{/if}
