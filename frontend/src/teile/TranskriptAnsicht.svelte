<script lang="ts">
  // Ein Transkript: Spieler, Text zum Mitlesen (Wort für Wort, folgt der Wiedergabe, bis man selbst rollt), Suche im
  // Text, rechts die Leiste. Bearbeiten: Änderungen sammeln sich in einem Entwurf, Vorschläge der KI-Korrektur stehen
  // unter ihrem Beitrag, Speichern legt eine neue Version an (nur mit dem gelesenen Stand; sonst neu laden).
  // Entwurf: mockups/transkription.html (3, 4) und transkription-mobil.html (3).
  import { onMount, tick } from "svelte";
  import { gehe, geraet, navigation } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { arbeit } from "../lib/arbeit.svelte";
  import type { Marker, Segment, Transkript, TranskriptAntwort, Vorschlag } from "../lib/typen";
  import { farbe, marke } from "../lib/zeit";
  import Beitrag from "./Beitrag.svelte";
  import Spieler from "./Spieler.svelte";
  import TranskriptLeiste from "./TranskriptLeiste.svelte";

  let { id, beginn = null }: { id: string; beginn?: number | null } = $props();

  let antwort = $state<TranskriptAntwort | null>(null);
  let fehler = $state("");
  let konflikt = $state(false);
  let zeit = $state(0);
  let laeuft = $state(false);
  let spieler = $state<Spieler>();
  let rollfeld = $state<HTMLElement>();
  let mitlaufen = $state(true);
  let suche = $state("");
  let treffer = $state(0);
  let bearbeiten = $state(false);
  let entwurf = $state<Transkript | null>(null);
  let offen = $state<number | null>(null);
  let nurBeitrag = $state(false);
  let vorschlaege = $state<Vorschlag[]>([]);
  let entscheidungen = $state<Record<string, "uebernommen" | "verworfen">>({});
  let speichert = $state(false);
  let mehr = $state(false);
  let ruhePause: ReturnType<typeof setTimeout>;

  const t = $derived(entwurf ?? antwort?.transkript ?? null);
  const segmente = $derived(t?.segmente ?? []);
  const aktiv = $derived.by(() => {
    let lo = 0;
    let hi = segmente.length - 1;
    let gefunden = -1;
    while (lo <= hi) {
      const mitte = (lo + hi) >> 1;
      if (segmente[mitte].start <= zeit) {
        gefunden = mitte;
        lo = mitte + 1;
      } else hi = mitte - 1;
    }
    return gefunden >= 0 && zeit < segmente[gefunden].ende + 1.5 ? gefunden : -1;
  });
  const spur = $derived.by(() => {
    const aus: { von: number; bis: number; farbe: string }[] = [];
    for (const s of segmente) {
      const letzte = aus.at(-1);
      if (letzte && letzte.farbe === farbe(s.sprecher) && s.start - letzte.bis < 3) letzte.bis = s.ende;
      else aus.push({ von: s.start, bis: s.ende, farbe: farbe(s.sprecher) });
    }
    return aus;
  });
  const markerVor = $derived.by(() => {
    // Marker gehören vor den ersten Beitrag, der nach ihnen beginnt
    const zu: Record<number, Marker[]> = {};
    for (const m of t?.marker ?? []) {
      const i = segmente.findIndex((s) => s.start >= m.zeit);
      (zu[i < 0 ? segmente.length : i] ??= []).push(m);
    }
    return zu;
  });
  const geaendert = $derived.by(() => {
    if (!entwurf || !antwort) return new Set<number>();
    const alt = new Map(antwort.transkript.segmente.map((s) => [`${s.start}|${s.text}|${s.ende}|${s.sprecher}`, true]));
    return new Set(entwurf.segmente.flatMap((s, i) => (alt.has(`${s.start}|${s.text}|${s.ende}|${s.sprecher}`) ? [] : [i])));
  });
  const markerGeaendert = $derived(!!entwurf && !!antwort && JSON.stringify(entwurf.marker) !== JSON.stringify(antwort.transkript.marker));
  const anzahlAenderungen = $derived(geaendert.size + (entwurf && antwort && entwurf.segmente.length !== antwort.transkript.segmente.length ? 1 : 0) + (markerGeaendert ? 1 : 0));
  const offeneVorschlaege = $derived(vorschlaege.filter((v) => !entscheidungen[v.id]));
  const verworfen = $derived(Object.values(entscheidungen).filter((z) => z === "verworfen").length);
  const ungespeichert = $derived(anzahlAenderungen + verworfen);

  $effect(() => {
    arbeit.ungespeichert = ungespeichert > 0 || Object.keys(entscheidungen).length > 0;
    return () => (arbeit.ungespeichert = false);
  });

  async function laden() {
    fehler = "";
    konflikt = false;
    try {
      antwort = await api.transkript(id);
      navigation.titel = antwort.transkript.name;
      vorschlaege = await api.vorschlaege(id);
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  onMount(() => {
    void laden().then(async () => {
      if (beginn != null) {
        await tick();
        springen(beginn);
        gehe(`transkripte/${id}`, true);
      }
    });
  });

  // Dem laufenden Beitrag folgen, außer man rollt selbst (dann eine Weile nicht).
  $effect(() => {
    const i = aktiv;
    if (i < 0 || !mitlaufen || !rollfeld || bearbeiten) return;
    rollfeld.querySelector(`[data-i="${i}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  });

  function selbstGerollt() {
    mitlaufen = false;
    clearTimeout(ruhePause);
    ruhePause = setTimeout(() => (mitlaufen = true), 8000);
  }

  function springen(s: number) {
    mitlaufen = true;
    spieler?.springe(s, true);
  }

  function weiterSuchen() {
    const begriff = suche.trim().toLowerCase();
    if (!begriff) return;
    const passend = segmente.map((s, i) => (s.text.toLowerCase().includes(begriff) ? i : -1)).filter((i) => i >= 0);
    if (!passend.length) {
      treffer = 0;
      return;
    }
    const naechster = passend.find((i) => segmente[i].start > zeit + 0.5) ?? passend[0];
    treffer = passend.length;
    mitlaufen = true;
    spieler?.springe(segmente[naechster].start);
    rollfeld?.querySelector(`[data-i="${naechster}"]`)?.scrollIntoView({ block: "center" });
  }

  // --- Bearbeiten -----------------------------------------------------------------------------------------------

  function bearbeitenBeginnen() {
    if (!antwort) return;
    entwurf = structuredClone($state.snapshot(antwort.transkript)) as Transkript;
    bearbeiten = true;
    entscheidungen = {};
  }

  function bearbeitenBeenden() {
    entwurf = null;
    bearbeiten = false;
    offen = null;
    entscheidungen = {};
  }

  function segmentAendern(i: number, s: Segment) {
    if (!entwurf) return;
    entwurf.segmente[i] = s;
  }

  function teilen(i: number, position: number) {
    if (!entwurf) return;
    const s = entwurf.segmente[i];
    const vorne = s.text.slice(0, position).trim();
    const hinten = s.text.slice(position).trim();
    if (!vorne || !hinten) return;
    const n = vorne.split(/\s+/).length;
    const passend = s.woerter.length === s.text.trim().split(/\s+/).length;
    const schnitt = passend && s.woerter[n] ? s.woerter[n].start : s.start + ((s.ende - s.start) * vorne.length) / s.text.length;
    entwurf.segmente.splice(i, 1,
      { ...s, ende: schnitt, text: vorne, woerter: passend ? s.woerter.slice(0, n) : [] },
      { ...s, start: schnitt, text: hinten, woerter: passend ? s.woerter.slice(n) : [] });
    offen = i + 1;
  }

  function zusammen(i: number) {
    if (!entwurf || i + 1 >= entwurf.segmente.length) return;
    const a = entwurf.segmente[i];
    const b = entwurf.segmente[i + 1];
    entwurf.segmente.splice(i, 2, { ...a, ende: b.ende, text: `${a.text} ${b.text}`.trim(), woerter: [...a.woerter, ...b.woerter] });
  }

  function markerAmBeitrag(i: number) {
    if (!entwurf) return;
    const s = entwurf.segmente[i];
    entwurf.marker = [...entwurf.marker, { id: crypto.getRandomValues(new Uint32Array(4)).join("-"), zeit: s.start,
      titel: s.text.split(/\s+/).slice(0, 4).join(" ") || "Marker", farbe: "gelb" as const }].sort((a, b) => a.zeit - b.zeit);
  }

  async function markerSpeichern(liste: Marker[]) {
    if (bearbeiten && entwurf) {
      entwurf.marker = liste.sort((a, b) => a.zeit - b.zeit);
      return;
    }
    if (!antwort) return;
    antwort = await api.aendern(id, { stand: antwort.stand, marker: liste });
  }

  function vorschlagIndex(v: Vorschlag): number {
    return segmente.findIndex((s) => Math.abs(s.start - v.start) < 0.01);
  }

  function entscheiden(v: Vorschlag, zustand: "uebernommen" | "verworfen") {
    if (!entwurf) bearbeitenBeginnen();
    if (zustand === "uebernommen" && entwurf) {
      const i = vorschlagIndex(v);
      if (i >= 0) entwurf.segmente[i] = { ...entwurf.segmente[i], text: v.neu };
    }
    entscheidungen = { ...entscheidungen, [v.id]: zustand };
  }

  async function speichern() {
    if (!antwort || !entwurf) return;
    speichert = true;
    fehler = "";
    try {
      antwort = await api.aendern(id, {
        stand: antwort.stand,
        segmente: $state.snapshot(entwurf.segmente) as Segment[],
        marker: markerGeaendert ? ($state.snapshot(entwurf.marker) as Marker[]) : undefined,
        vorschlaege: Object.entries(entscheidungen).map(([vid, zustand]) => ({ id: vid, zustand })),
      });
      vorschlaege = await api.vorschlaege(id);
      entwurf = structuredClone($state.snapshot(antwort.transkript)) as Transkript;
      entscheidungen = {};
      offen = null;
    } catch (f) {
      const meldung = (f as Error).message;
      if ((f as { status?: number }).status === 409) konflikt = true;
      fehler = meldung;
    } finally {
      speichert = false;
    }
  }

  const passendVorschlag = (s: Segment) => offeneVorschlaege.filter((v) => Math.abs(v.start - s.start) < 0.01);
  const vorschlagGilt = (v: Vorschlag, s: Segment) => v.alt === (antwort?.transkript.segmente.find((x) => Math.abs(x.start - s.start) < 0.01)?.text ?? s.text);

  // Wortweiser Vergleich (längste gemeinsame Folge): was wegfällt, was neu ist, was bleibt.
  function abweichung(alt: string, neu: string): { teil: string; art: "gleich" | "weg" | "neu" }[] {
    const a = alt.split(/\s+/).filter(Boolean);
    const b = neu.split(/\s+/).filter(Boolean);
    const l = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
    for (let i = a.length - 1; i >= 0; i--)
      for (let j = b.length - 1; j >= 0; j--) l[i][j] = a[i] === b[j] ? l[i + 1][j + 1] + 1 : Math.max(l[i + 1][j], l[i][j + 1]);
    const aus: { teil: string; art: "gleich" | "weg" | "neu" }[] = [];
    const dazu = (teil: string, art: "gleich" | "weg" | "neu") => {
      const letzte = aus.at(-1);
      if (letzte && letzte.art === art) letzte.teil += ` ${teil}`;
      else aus.push({ teil, art });
    };
    let i = 0;
    let j = 0;
    while (i < a.length || j < b.length) {
      if (i < a.length && j < b.length && a[i] === b[j]) {
        dazu(a[i++], "gleich");
        j++;
      } else if (i < a.length && (j >= b.length || l[i + 1][j] >= l[i][j + 1])) dazu(a[i++], "weg");
      else dazu(b[j++], "neu");
    }
    return aus.map((x, n) => ({ ...x, teil: n < aus.length - 1 ? `${x.teil} ` : x.teil }));
  }
</script>

{#snippet vorschlagBox(v: Vorschlag, s: Segment)}
  {#if vorschlagGilt(v, s)}
    <div class="vorschlag">
      <div class="kopfzeile"><i class="fa-solid fa-wand-magic-sparkles" style="color:var(--akzent)"></i>Vorschlag
        <span class="aktionen"><button class="knopf klein" onclick={() => entscheiden(v, "uebernommen")}><i class="fa-solid fa-check"></i> Übernehmen</button>
          <button class="knopf klein still" onclick={() => entscheiden(v, "verworfen")}>Verwerfen</button></span></div>
      {#each abweichung(v.alt, v.neu) as x, i (i)}{#if x.art === "weg"}<del>{x.teil}</del>{:else if x.art === "neu"}<ins>{x.teil}</ins>{:else}{x.teil}{/if}{/each}
    </div>
  {/if}
{/snippet}

{#snippet text()}
  {#each segmente as s, i (i)}
    {#each markerVor[i] ?? [] as m (m.id)}
      <div class="marker-zeile"><i class="fa-solid fa-flag"></i>{marke(m.zeit)} {m.titel}</div>
    {/each}
    <div data-i={i}>
      <Beitrag seg={s} sprecher={t?.sprecher ?? []} jetzt={i === aktiv ? zeit : null} {suche} mobil={geraet.mobil}
               offen={bearbeiten && offen === i} {bearbeiten} geaendert={bearbeiten && geaendert.has(i)}
               onspringen={springen} onoeffnen={() => (offen = i)} onschliessen={() => (offen = null)}
               onaendern={(neu) => segmentAendern(i, neu)} onteilen={(p) => teilen(i, p)} onzusammen={() => zusammen(i)}
               onmarker={() => markerAmBeitrag(i)} />
    </div>
    {#if !geraet.mobil && (bearbeiten || offeneVorschlaege.length)}
      {#each passendVorschlag(s) as v (v.id)}{@render vorschlagBox(v, s)}{/each}
    {/if}
  {/each}
  {#each markerVor[segmente.length] ?? [] as m (m.id)}
    <div class="marker-zeile"><i class="fa-solid fa-flag"></i>{marke(m.zeit)} {m.titel}</div>
  {/each}
{/snippet}

{#if !antwort}
  {#if fehler}
    <div class="seiten-kopf"><button class="knopf still" onclick={() => gehe("transkripte")}><i class="fa-solid fa-chevron-left"></i> Transkripte</button></div>
    <div class="rollfeld"><div class="fehlertext">{fehler}</div></div>
  {:else}<div class="leer">Lädt ...</div>{/if}
{:else if geraet.mobil}
  <div class="knopfzeile" style="margin-bottom:8px">
    <label class="suche" style="flex:1; min-width:0"><i class="fa-solid fa-magnifying-glass"></i>
      <input class="eingabe-roh" placeholder="Im Text suchen" bind:value={suche} onkeydown={(e) => e.key === "Enter" && weiterSuchen()} /></label>
    <button class="rund" aria-label="Mehr" class:aktiv={mehr} onclick={() => (mehr = !mehr)}><i class="fa-solid fa-ellipsis-vertical"></i></button>
  </div>
  {#if mehr}
    <div class="karte" style="padding:0; margin-bottom:10px">
      <TranskriptLeiste {antwort} {zeit} onspringen={springen} onneu={(a) => (antwort = a)} onmarker={markerSpeichern}
                        onvorschlaege={() => api.vorschlaege(id).then((v) => (vorschlaege = v))} />
    </div>
  {/if}
  {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
  <div bind:this={rollfeld} ontouchmove={selbstGerollt} onwheel={selbstGerollt} role="region" aria-label="Text">{@render text()}</div>
  <Spieler bind:this={spieler} src={api.tonAdresse(id)} dauer={antwort.transkript.dauer_s} wellenform={antwort.transkript.wellenform}
           {spur} marker={antwort.transkript.marker.map((m) => m.zeit)} bind:zeit bind:laeuft kompakt />
{:else}
  <div class="geruest-innen">
    <section class="seite">
      <div class="seiten-kopf">
        <button class="knopf still" style="padding:0 6px" onclick={() => gehe("transkripte")}><i class="fa-solid fa-chevron-left"></i> Transkripte</button>
        <h1 class="titel-lang" title={antwort.transkript.name}>{antwort.transkript.name}</h1>
        {#if bearbeiten}
          <span class="pille aktiv"><i class="fa-solid fa-pen"></i>Bearbeiten</span>
          {#if !ungespeichert && !Object.keys(entscheidungen).length}<button class="knopf" onclick={bearbeitenBeenden}>Fertig</button>{/if}
        {:else}
          <label class="suche" style="min-width:180px"><i class="fa-solid fa-magnifying-glass"></i>
            <input class="eingabe-roh" placeholder="Im Text suchen" bind:value={suche} onkeydown={(e) => e.key === "Enter" && weiterSuchen()} />
            {#if suche && treffer}<span style="color:var(--text-3)">{treffer}</span>{/if}</label>
          <button class="knopf" onclick={bearbeitenBeginnen}><i class="fa-solid fa-pen"></i> Bearbeiten</button>
        {/if}
      </div>
      <Spieler bind:this={spieler} src={api.tonAdresse(id)} dauer={antwort.transkript.dauer_s} wellenform={antwort.transkript.wellenform}
               {spur} marker={(t?.marker ?? []).map((m) => m.zeit)} bind:zeit bind:laeuft
               stoppBei={bearbeiten && nurBeitrag && offen != null ? segmente[offen]?.ende ?? null : null} />
      {#if bearbeiten}
        <div class="knopfzeile" style="padding:8px 22px 0">
          <span class="segment"><button class:aktiv={nurBeitrag} onclick={() => (nurBeitrag = true)}>Nur diesen Beitrag</button>
            <button class:aktiv={!nurBeitrag} onclick={() => (nurBeitrag = false)}>Weiter</button></span>
        </div>
      {/if}
      <div class="rollfeld" style="padding-top:14px" bind:this={rollfeld} onwheel={selbstGerollt} ontouchmove={selbstGerollt}
           role="region" aria-label="Text">
        <div class="text-flaeche">
          {#if fehler}
            <div class="fehlertext" style="margin-bottom:12px">{fehler}
              {#if konflikt}<button class="knopf klein" style="margin-left:10px" onclick={() => { bearbeitenBeenden(); void laden(); }}>Neu laden (eigene Änderungen verwerfen)</button>{/if}</div>
          {/if}
          {#if offeneVorschlaege.length}
            <div class="optionen">
              <span class="titel"><i class="fa-solid fa-wand-magic-sparkles"></i> KI-Korrektur</span>
              <span style="font-size:var(--klein); color:var(--text-2)">{vorschlaege.length} Vorschläge: {Object.values(entscheidungen).filter((z) => z === "uebernommen").length} übernommen,
                {Object.values(entscheidungen).filter((z) => z === "verworfen").length} verworfen, {offeneVorschlaege.length} offen</span>
              <span class="knopfzeile" style="margin-left:auto">
                <button class="knopf" onclick={() => offeneVorschlaege.forEach((v) => entscheiden(v, "uebernommen"))}>Alle offenen übernehmen</button>
                <button class="knopf still" onclick={() => offeneVorschlaege.forEach((v) => entscheiden(v, "verworfen"))}>Alle verwerfen</button>
              </span>
            </div>
          {/if}
          {@render text()}
          {#if !segmente.length}<p class="leer">In dieser Aufnahme wurde nichts gesprochen.</p>{/if}
          {#if bearbeiten && (ungespeichert || Object.keys(entscheidungen).length)}
            <div class="speicherleiste" style="margin-top:14px">
              <span class="was"><b style="color:var(--text)">{ungespeichert === 1 ? "1 Änderung" : `${ungespeichert} Änderungen`}</b> noch nicht
                gespeichert. Speichern legt eine neue Version an; die jetzige bleibt abrufbar.</span>
              <button class="knopf still" onclick={() => { entwurf = structuredClone($state.snapshot(antwort!.transkript)) as Transkript; entscheidungen = {}; offen = null; }}>Verwerfen</button>
              <button class="knopf primaer" onclick={speichern} disabled={speichert}><i class="fa-solid {speichert ? 'fa-circle-notch fa-spin' : 'fa-floppy-disk'}"></i> Speichern</button>
            </div>
          {/if}
        </div>
      </div>
    </section>
    <aside class="leiste">
      <TranskriptLeiste {antwort} {zeit} {bearbeiten} onspringen={springen} onneu={(a) => { antwort = a; if (bearbeiten) entwurf = structuredClone($state.snapshot(a.transkript)) as Transkript; }}
                        onmarker={markerSpeichern} onvorschlaege={() => api.vorschlaege(id).then((v) => (vorschlaege = v))} />
    </aside>
  </div>
{/if}
