<script lang="ts">
  // Altbestand der alten App (Entwurf 1d): deine eigenen Aufnahmen mit ihren Ständen, nur lesend. Übernommen wird nur,
  // was du wählst: Zielordner (vorhanden oder neu), Name, auf Wunsch neu transkribieren; die Vorschau sagt vorher, wo
  // alles landet und welche Versionen entstehen. Übernommene führen zur Aufnahme.
  import { onMount } from "svelte";
  import { Auswahl, beiAuftrag, gehe } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { SPRECHER_WEGE, type SprecherWeg } from "../lib/sprecherwahl";
  import type { AltbestandSeite, AltEintrag } from "../lib/typen";
  import { groesse, marke } from "../lib/zeit";

  const NEU = "+neu";

  let { suche = "" }: { suche?: string } = $props();

  let seite = $state<AltbestandSeite | null>(null);
  let fehler = $state("");
  let meldung = $state("");
  let gewaehlt = $state<AltEintrag | null>(null);
  let unterordner = $state<string[]>([]);
  let zielordner = $state("");
  let neuerOrdner = $state("");
  let name = $state("");
  let neu = $state(true);
  let sprecher = $state<SprecherWeg>("ohne");
  let startet = $state(false);

  const ziel = $derived((zielordner === NEU ? neuerOrdner : zielordner).trim().replace(/^\/+|\/+$/g, ""));
  const ordnerOptionen = $derived([
    { wert: "", titel: "Aufnahmen (oben)" },
    ...unterordner.map((u) => ({ wert: u, titel: `Aufnahmen/${u}` })),
    { wert: NEU, titel: "Neuer Ordner ..." },
  ]);
  const sichtbar = $derived((seite?.eintraege ?? []).filter((e) => !suche.trim() || e.name.toLowerCase().includes(suche.trim().toLowerCase())));
  const vorschau = $derived.by(() => {
    if (!gewaehlt || gewaehlt.unvollstaendig) return "";
    const ort = ziel ? `/${ziel}` : "";
    const n = gewaehlt.staende.length;
    const versionen = n === 1 ? "der alte Stand wird die Version 1" : `die ${n} alten Stände werden die Versionen 1 bis ${n}`;
    return { datei: `Aufnahmen${ort}/${name.trim() || gewaehlt.vorschlag}${gewaehlt.endung}`, transkripte: `Transkripte${ort}`,
             versionen: neu ? `${versionen}, die neue Transkription die Version ${n + 1}` : versionen };
  });

  async function laden() {
    fehler = "";
    try {
      seite = await api.altbestand();
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  onMount(() => {
    void laden();
    void (async () => {
      try {
        const eigen = (await api.ordnerListe())[0];
        if (eigen) unterordner = (await api.aufnahmen({ ordner: eigen.id, anzahl: 1 })).unterordner.map((o) => o.name);
      } catch {
        // dann nur oben und neu
      }
    })();
    return beiAuftrag((a) => {
      if ((a.art === "uebernehmen" || a.art === "transkribieren") && !["wartet", "laeuft"].includes(a.zustand)) void laden();
      if (a.art === "uebernehmen" && a.zustand === "fehler") fehler = a.fehler ?? "Übernahme gescheitert";
    });
  });

  function waehlen(e: AltEintrag) {
    if (e.uebernommen) {
      gehe(`aufnahmen/${e.uebernommen.aufnahme_id}`);
      return;
    }
    if (e.auftrag_id) return;
    gewaehlt = gewaehlt?.schluessel === e.schluessel ? null : e;
    name = e.unvollstaendig ? (e.unvollstaendig.pfad.split("/").pop() ?? e.vorschlag).replace(/\.[^.]+$/, "") : e.vorschlag;
  }

  async function uebernehmen() {
    if (!gewaehlt) return;
    startet = true;
    fehler = "";
    try {
      await api.altUebernehmen({ schluessel: gewaehlt.schluessel, zielordner: ziel, name: name.trim() || gewaehlt.vorschlag,
                                 neu_transkribieren: neu, sprecher });
      meldung = `${name.trim() || gewaehlt.vorschlag} wird übernommen; der Stand steht hier und unter Aufträge.`;
      if (ziel && !unterordner.includes(ziel)) unterordner = [...unterordner, ziel].sort();
      gewaehlt = null;
      await laden();
    } catch (f) {
      fehler = (f as Error).message;
    } finally {
      startet = false;
    }
  }

  const datum = (iso: string) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  };
  const meta = (e: AltEintrag) => {
    const n = e.staende.length;
    const woerter = e.staende.at(-1)?.mit_woertern ? "mit Wortzeiten" : "ohne Wortzeiten";
    return [marke(e.dauer_s), e.endung.replace(".", "").toUpperCase(), groesse(e.groesse), `vom ${datum(e.staende.at(-1)?.erstellt_am ?? "")}`,
            `${n === 1 ? "1 Stand" : `${n} Stände`}, ${woerter}`].filter(Boolean).join(" · ");
  };
</script>

{#if fehler}<div class="fehlertext" style="margin-bottom:12px">{fehler}</div>{/if}
{#if meldung}<p class="leer" style="padding:6px 4px 14px; text-align:left">{meldung}</p>{/if}

{#if gewaehlt?.unvollstaendig}
  <div class="optionen">
    <span class="titel"><i class="fa-solid fa-box-archive"></i> Übernahme fortsetzen</span>
    <label>Neu transkribieren <button class="schalter" class:an={neu} aria-label="Neu transkribieren" aria-pressed={neu}
                                      onclick={() => (neu = !neu)}></button></label>
    {#if neu}<label>Sprecher <Auswahl bind:wert={sprecher} optionen={SPRECHER_WEGE} /></label>{/if}
    <span class="knopfzeile" style="margin-left:auto">
      <button class="knopf still" onclick={() => (gewaehlt = null)}>Auswahl aufheben</button>
      <button class="knopf primaer" onclick={uebernehmen} disabled={startet}>
        <i class="fa-solid {startet ? 'fa-circle-notch fa-spin' : 'fa-file-import'}"></i> Fortsetzen</button>
    </span>
    <span class="vorschau-ziel">Die Aufnahme liegt schon in <code>{gewaehlt.unvollstaendig.pfad}</code>; es fehlen noch Stände. Fortsetzen
      übernimmt die fehlenden, nichts wird doppelt hochgeladen.</span>
  </div>
{:else if gewaehlt}
  <div class="optionen">
    <span class="titel"><i class="fa-solid fa-box-archive"></i> 1 gewählt</span>
    <label>Zielordner <Auswahl bind:wert={zielordner} optionen={ordnerOptionen} /></label>
    {#if zielordner === NEU}
      <label class="eingabe" style="height:38px; min-width:200px"><input bind:value={neuerOrdner} placeholder="Name des Ordners"
             aria-label="Name des neuen Ordners" /></label>
    {/if}
    <label>Name <span class="eingabe" style="height:38px; min-width:260px"><input bind:value={name} aria-label="Name der Aufnahme" /></span></label>
    <label>Neu transkribieren <button class="schalter" class:an={neu} aria-label="Neu transkribieren" aria-pressed={neu}
                                      onclick={() => (neu = !neu)}></button></label>
    {#if neu}<label>Sprecher <Auswahl bind:wert={sprecher} optionen={SPRECHER_WEGE} /></label>{/if}
    <span class="knopfzeile" style="margin-left:auto">
      <button class="knopf still" onclick={() => (gewaehlt = null)}>Auswahl aufheben</button>
      <button class="knopf primaer" onclick={uebernehmen} disabled={startet || (zielordner === NEU && !neuerOrdner.trim())}>
        <i class="fa-solid {startet ? 'fa-circle-notch fa-spin' : 'fa-file-import'}"></i> Übernehmen</button>
    </span>
    {#if vorschau}
      <span class="vorschau-ziel">Ziel: <code>{vorschau.datei}</code>, Transkript in <code>{vorschau.transkripte}</code>; {vorschau.versionen}.
        Die alte App bleibt unverändert.</span>
    {/if}
  </div>
{/if}

{#each sichtbar as e (e.schluessel)}
  <div class="zeile" class:gewaehlt={gewaehlt?.schluessel === e.schluessel} role="button" tabindex="0"
       onclick={() => waehlen(e)} onkeydown={(k) => k.key === "Enter" && waehlen(e)}>
    <span class="art"><i class="fa-solid fa-file-audio"></i></span>
    <div style="min-width:0"><div class="name">{e.name}</div><div class="meta">{meta(e)}</div></div>
    {#if e.uebernommen}
      <span class="stand-pille fertig">übernommen</span><i class="fa-solid fa-chevron-right" style="color:var(--text-3); padding-right:10px"></i>
    {:else if e.auftrag_id}
      <span class="stand-pille laeuft"><i class="fa-solid fa-circle-notch fa-spin"></i> wird übernommen</span><span></span>
    {:else if e.unvollstaendig}
      <span class="stand-pille warn" title="angefangen, aber nicht fertig; anklicken zum Fortsetzen">unvollständig</span><span></span>
    {:else}
      <span class="stand-pille offen">offen</span><span></span>
    {/if}
  </div>
{:else}
  {#if seite && suche.trim()}<p class="leer">Nichts gefunden.</p>
  {:else if seite}<p class="leer">In der alten App gibt es keine eigenen Aufnahmen.</p>{:else if !fehler}<p class="leer">Lädt ...</p>{/if}
{/each}
{#if seite?.eintraege.length}
  <p class="leer" style="padding:14px">Nur deine eigenen Tonaufnahmen der alten App; Tonspuren von Videos und Ergebnisse der Sprachausgabe
    gehören nicht hierher.</p>
{/if}
