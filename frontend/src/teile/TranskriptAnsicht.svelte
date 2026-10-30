<script lang="ts">
  // Ein Transkript: Spieler, Text zum Mitlesen (Wort für Wort, folgt der Wiedergabe, bis man selbst rollt), Suche im
  // Text, rechts die Leiste. Bearbeiten ist ein Modus für Text, Sprecher und Marker, am Rechner wie am Telefon: oben
  // steht fest die Bearbeitungsleiste (Anleitung, Zahl der Änderungen, Verwerfen, Speichern), Änderungen sammeln sich
  // in einem Entwurf, Vorschläge der KI-Korrektur stehen unter ihrem Beitrag, Speichern legt eine neue Version an (nur
  // mit dem gelesenen Stand; sonst neu laden). Entwurf: mockups/transkription.html (3, 3b, 3c, 4), transkription-mobil.html (3).
  import { onMount, tick } from "svelte";
  import { AnfrageBand, arbeit, farbe, gehe, geraet, Leiste, leisteOeffnen, marke, navigation, Spieler,
           zurueckZurKellerwolke } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { neueKennung } from "../lib/kennung";
  import type { Marker, Segment, Transkript, TranskriptAntwort, Vorschlag } from "../lib/typen";
  import Beitrag from "./Beitrag.svelte";
  import Bearbeitungsleiste from "./Bearbeitungsleiste.svelte";
  import TranskriptLeiste from "./TranskriptLeiste.svelte";

  // `anfrage`: aus der Kellerwolke geöffnet (Datei außerhalb der App); alles geht dann mit dem Recht dieser Anfrage.
  let { id, beginn = null, anfrage = null }: { id: string; beginn?: number | null; anfrage?: string | null } = $props();

  function zurueck() {
    if (anfrage) zurueckZurKellerwolke(antwort ? herkunft(antwort) : "", "aufnahmen/kellerwolke");
    else gehe("transkripte");
  }
  const herkunft = (a: TranskriptAntwort) => a.transkript.quelle?.pfad ?? a.pfad;
  const ANHALTEN_SCHLUESSEL = "transkription.anhalten";

  let antwort = $state<TranskriptAntwort | null>(null);
  let fehler = $state("");
  let konflikt = $state(false);
  let zeit = $state(0);
  let laeuft = $state(false);
  let spieler = $state<Spieler>();
  let rollfeld = $state<HTMLElement>();
  let mitlaufen = $state(true);
  let suche = $state("");
  let trefferNr = $state(-1);       // der zuletzt angesprungene Treffer (Stelle in `passend`)
  let bearbeiten = $state(false);
  let entwurf = $state<Transkript | null>(null);
  let offen = $state<number | null>(null);
  let vorschlaege = $state<Vorschlag[]>([]);
  let entscheidungen = $state<Record<string, "uebernommen" | "verworfen">>({});
  let speichert = $state(false);
  let mehr = $state(false);
  let gewaehlt = $state<number[]>([]);
  let anker = $state<number | null>(null);
  let anhalten = $state(gemerktesAnhalten());
  let angehaltenBei = $state<number | null>(null);
  let welle = $state<number[] | null>(null);
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
  const gewaehltMenge = $derived(new Set(gewaehlt));
  const sprecherGeaendert = $derived(!!entwurf && !!antwort && JSON.stringify(entwurf.sprecher.map((s) => [s.kennung, s.name]))
    !== JSON.stringify(antwort.transkript.sprecher.map((s) => [s.kennung, s.name])));
  const markerGeaendert = $derived(!!entwurf && !!antwort && JSON.stringify(entwurf.marker) !== JSON.stringify(antwort.transkript.marker));
  const anzahlAenderungen = $derived(geaendert.size + (entwurf && antwort && entwurf.segmente.length !== antwort.transkript.segmente.length ? 1 : 0) + (markerGeaendert ? 1 : 0) + (sprecherGeaendert ? 1 : 0));
  const offeneVorschlaege = $derived(vorschlaege.filter((v) => !entscheidungen[v.id]));
  const verworfen = $derived(Object.values(entscheidungen).filter((z) => z === "verworfen").length);
  const ungespeichert = $derived(anzahlAenderungen + verworfen);

  // "Am Ende des Beitrags anhalten": hält einmal am Ende der Auswahl; nochmal Abspielen läuft weiter, zurück in den
  // Beitrag gilt es wieder. Die Wahl merkt sich das Gerät.
  const auswahlEnde = $derived(gewaehlt.length ? segmente[gewaehlt[gewaehlt.length - 1]]?.ende ?? null : null);
  const stoppBei = $derived(bearbeiten && anhalten && auswahlEnde != null && angehaltenBei !== auswahlEnde ? auswahlEnde : null);
  $effect(() => {
    if (stoppBei != null && !laeuft && zeit >= stoppBei - 0.05) angehaltenBei = stoppBei;
    else if (angehaltenBei != null && zeit < angehaltenBei - 0.3) angehaltenBei = null;
  });
  $effect(() => {
    try {
      localStorage.setItem(ANHALTEN_SCHLUESSEL, anhalten ? "1" : "0");
    } catch {
      // ohne Speicher im Browser gilt die Wahl nur bis zum Neuladen
    }
  });

  function gemerktesAnhalten(): boolean {
    try {
      return localStorage.getItem(ANHALTEN_SCHLUESSEL) !== "0";
    } catch {
      return true;
    }
  }

  $effect(() => {
    arbeit.ungespeichert = ungespeichert > 0 || Object.keys(entscheidungen).length > 0;
    return () => (arbeit.ungespeichert = false);
  });

  async function laden() {
    fehler = "";
    konflikt = false;
    try {
      antwort = await api.transkript(id, anfrage);
      navigation.titel = antwort.transkript.name;
      // die Wellenform kommt aus dem Ton selbst (gleich für alte und neue Transkripte); bis dahin die gespeicherte
      const quelle = antwort.transkript.quelle?.knoten_id;
      if (quelle) void api.wellenform(quelle, anfrage).then((w) => (welle = w)).catch(() => {});
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

  // Suche im Text: die Zahl der Treffer steht schon beim Tippen da, Eingabe springt zum nächsten (mit Umschalt zum
  // vorigen), reihum; der Treffer rückt in die Mitte und der Spieler an seinen Anfang.
  const passend = $derived.by(() => {
    const begriff = suche.trim().toLowerCase();
    return begriff ? segmente.flatMap((s, i) => (s.text.toLowerCase().includes(begriff) ? [i] : [])) : [];
  });
  $effect(() => {
    void suche;
    trefferNr = -1;
  });

  function weiterSuchen(rueckwaerts = false) {
    if (!passend.length) return;
    trefferNr = rueckwaerts ? (trefferNr <= 0 ? passend.length - 1 : trefferNr - 1) : (trefferNr + 1) % passend.length;
    const i = passend[trefferNr];
    selbstGerollt();
    spieler?.springe(segmente[i].start);
    rollfeld?.querySelector(`[data-i="${i}"]`)?.scrollIntoView({ block: "center" });
  }

  function suchTaste(e: KeyboardEvent) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    weiterSuchen(e.shiftKey);
  }

  // --- Bearbeiten: ein Modus für Text, Sprecher und Marker ------------------------------------------------------
  // Jede Änderung landet im Entwurf (auch ein Marker aus der Leiste oder ein übernommener Vorschlag öffnet ihn);
  // erst Speichern legt eine neue Version an. Klick öffnet einen Beitrag, Umschalt- und Befehl-Klick wählen mehrere
  // für die Sprecher; Ziffer ordnet zu und geht zum nächsten, Leertaste spielt die Auswahl.

  function bearbeitenBeginnen() {
    if (!antwort || bearbeiten) return;
    entwurf = structuredClone($state.snapshot(antwort.transkript)) as Transkript;
    bearbeiten = true;
    entscheidungen = {};
  }

  function verwerfen() {
    if (!antwort) return;
    entwurf = structuredClone($state.snapshot(antwort.transkript)) as Transkript;
    entscheidungen = {};
    offen = null;
    gewaehlt = [];
  }

  function bearbeitenBeenden() {
    entwurf = null;
    bearbeiten = false;
    offen = null;
    gewaehlt = [];
    anker = null;
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
    oeffnen(i + 1);
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
    entwurf.marker = [...entwurf.marker, { id: neueKennung(), zeit: s.start,
      titel: s.text.split(/\s+/).slice(0, 4).join(" ") || "Marker", farbe: "gelb" as const }].sort((a, b) => a.zeit - b.zeit);
  }

  // Marker aus der Leiste: wie jede Änderung in den Entwurf (öffnet Bearbeiten, falls nötig)
  async function markerSpeichern(liste: Marker[]) {
    bearbeitenBeginnen();
    if (entwurf) entwurf.marker = liste.sort((a, b) => a.zeit - b.zeit);
  }

  function vorschlagIndex(v: Vorschlag): number {
    return segmente.findIndex((s) => Math.abs(s.start - v.start) < 0.01);
  }

  function entscheiden(v: Vorschlag, zustand: "uebernommen" | "verworfen") {
    bearbeitenBeginnen();
    if (zustand === "uebernommen" && entwurf) {
      const i = vorschlagIndex(v);
      if (i >= 0) entwurf.segmente[i] = { ...entwurf.segmente[i], text: v.neu };
    }
    entscheidungen = { ...entscheidungen, [v.id]: zustand };
  }

  // --- Auswahl und Sprecher -----------------------------------------------------------------------------------

  function zeigen(i: number) {
    void tick().then(() => rollfeld?.querySelector(`[data-i="${i}"]`)?.scrollIntoView({ block: "nearest" }));
  }

  // Öffnen: der Beitrag wird die Auswahl, der Spieler springt an seinen Anfang (spielt weiter, wenn er lief)
  function oeffnen(i: number) {
    offen = i;
    gewaehlt = [i];
    anker = i;
    spieler?.springe(segmente[i].start, laeuft);
    zeigen(i);
  }

  function beitragKlick(i: number, e: MouseEvent) {
    if (e.shiftKey && anker != null) {
      const [a, b] = anker < i ? [anker, i] : [i, anker];
      gewaehlt = Array.from({ length: b - a + 1 }, (_, n) => a + n);
      offen = null;
      return;
    }
    if (e.metaKey || e.ctrlKey) {
      gewaehlt = gewaehltMenge.has(i) ? gewaehlt.filter((x) => x !== i) : [...gewaehlt, i].sort((x, y) => x - y);
      anker = i;
      offen = null;
      return;
    }
    oeffnen(i);
  }

  function zuweisen(kennung: string) {
    if (!entwurf || !gewaehlt.length) return;
    for (const i of gewaehlt) entwurf.segmente[i] = { ...entwurf.segmente[i], sprecher: kennung };
  }

  // per Taste: ein einzelner Beitrag geht danach zum nächsten, damit man beim Anhören nur Ziffern tippt
  function zuweisenUndWeiter(kennung: string) {
    zuweisen(kennung);
    if (!entwurf || gewaehlt.length !== 1 || gewaehlt[0] + 1 >= entwurf.segmente.length) return;
    waehleEinzeln(gewaehlt[0] + 1);
    if (laeuft) spieler?.springe(segmente[gewaehlt[0]].start, true);
  }

  function waehleEinzeln(i: number) {
    gewaehlt = [i];
    anker = i;
    offen = null;
    zeigen(i);
  }

  function neuerSprecher(): string | null {
    if (!entwurf) return null;
    const n = Math.max(0, ...entwurf.sprecher.map((s) => Number(s.kennung.slice(1)) || 0)) + 1;
    const kennung = `s${n}`;
    entwurf.sprecher = [...entwurf.sprecher, { kennung, name: `Sprecher ${n}` }];
    return kennung;
  }

  function neuerSprecherFuerAuswahl() {
    const k = neuerSprecher();
    if (k && gewaehlt.length) zuweisen(k);
  }

  function sprecherUmbenennen(kennung: string, name: string) {
    if (!entwurf || !name.trim()) return;
    entwurf.sprecher = entwurf.sprecher.map((s) => (s.kennung === kennung ? { ...s, name: name.trim() } : s));
  }

  function zusammenfuehren(von: string, nach: string) {
    if (!entwurf || von === nach) return;
    entwurf.segmente = entwurf.segmente.map((s) => (s.sprecher === von ? { ...s, sprecher: nach } : s));
    entwurf.sprecher = entwurf.sprecher.filter((s) => s.kennung !== von);
  }

  function auswahlAbspielen() {
    if (gewaehlt.length) spieler?.springe(segmente[gewaehlt[0]].start, true);
  }

  // Tasten im Bearbeiten (nicht beim Schreiben in Feldern): Ziffer, N, Pfeile, Leertaste, Eingabe, Escape
  function bearbeitenTasten(e: KeyboardEvent) {
    if (!bearbeiten || !entwurf || geraet.mobil) return;
    const ziel = e.target as HTMLElement;
    if (ziel.closest("input, textarea, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
    if (/^[1-9]$/.test(e.key)) {
      const s = entwurf.sprecher[Number(e.key) - 1];
      if (s && gewaehlt.length) {
        e.preventDefault();
        zuweisenUndWeiter(s.kennung);
      }
    } else if ((e.key === "n" || e.key === "N") && gewaehlt.length) {
      e.preventDefault();
      const k = neuerSprecher();
      if (k) zuweisenUndWeiter(k);
    } else if (e.key === "Escape") {
      if (offen != null) offen = null;
      else gewaehlt = [];
    } else if (e.key === "Enter" && gewaehlt.length === 1 && offen == null) {
      e.preventDefault();
      oeffnen(gewaehlt[0]);
    } else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && gewaehlt.length === 1) {
      e.preventDefault();
      waehleEinzeln(Math.max(0, Math.min(segmente.length - 1, gewaehlt[0] + (e.key === "ArrowDown" ? 1 : -1))));
    } else if (e.key === " " && gewaehlt.length) {
      // vor dem Spieler: mit Auswahl spielt die Leertaste die gewählten Beiträge ab
      e.preventDefault();
      e.stopPropagation();
      if (laeuft) spieler?.umschalten();
      else auswahlAbspielen();
    }
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
        sprecher: sprecherGeaendert ? entwurf.sprecher.map(({ kennung, name }) => ({ kennung, name })) : undefined,
        vorschlaege: Object.entries(entscheidungen).map(([vid, zustand]) => ({ id: vid, zustand })),
      }, anfrage);
      vorschlaege = await api.vorschlaege(id);
      entwurf = structuredClone($state.snapshot(antwort.transkript)) as Transkript;
      entscheidungen = {};
      offen = null;
      gewaehlt = [];
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

{#snippet trefferStand()}
  {#if suche.trim()}
    {#if passend.length}
      <span class="treffer-stand" title="Eingabe: nächster Treffer, Umschalt und Eingabe: voriger">{trefferNr >= 0 ? `${trefferNr + 1}/` : ""}{passend.length}</span>
      <button class="knopf still treffer-knopf" aria-label="Nächster Treffer" title="Nächster Treffer (Eingabe)"
              onclick={(e) => { e.preventDefault(); weiterSuchen(); }}><i class="fa-solid fa-chevron-down"></i></button>
    {:else}<span class="treffer-stand keiner">keine Treffer</span>{/if}
  {/if}
{/snippet}

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
      <Beitrag seg={s} sprecher={t?.sprecher ?? []} jetzt={i === aktiv ? zeit : null} {suche} mobil={geraet.mobil} {bearbeiten}
               offen={bearbeiten && offen === i} gewaehlt={bearbeiten && gewaehltMenge.has(i)} geaendert={bearbeiten && geaendert.has(i)}
               spielerzeit={bearbeiten && offen === i ? zeit : null}
               onspringen={springen} onklick={(e) => beitragKlick(i, e)} onschliessen={() => (offen = null)}
               onaendern={(neu) => segmentAendern(i, neu)} onteilen={(p) => teilen(i, p)} onzusammen={() => zusammen(i)}
               onmarker={() => markerAmBeitrag(i)} onneuerSprecher={neuerSprecher} />
    </div>
    {#if bearbeiten}
      {#each passendVorschlag(s) as v (v.id)}{@render vorschlagBox(v, s)}{/each}
    {/if}
  {/each}
  {#each markerVor[segmente.length] ?? [] as m (m.id)}
    <div class="marker-zeile"><i class="fa-solid fa-flag"></i>{marke(m.zeit)} {m.titel}</div>
  {/each}
{/snippet}

{#snippet suchfeld(mobil: boolean)}
  <label class="suche text-suche" class:mobil-suche={mobil}><i class="fa-solid fa-magnifying-glass"></i>
    <input class="eingabe-roh" placeholder="Im Text suchen" enterkeyhint="next" bind:value={suche} onkeydown={suchTaste} />
    {@render trefferStand()}</label>
{/snippet}

{#snippet oberhalbText()}
  {#if bearbeiten && entwurf}
    <Bearbeitungsleiste mobil={geraet.mobil} aenderungen={ungespeichert} {speichert} bind:anhalten sprecher={entwurf.sprecher}
                        gewaehlt={gewaehlt.length} onzuweisen={zuweisen} onneuerSprecher={neuerSprecherFuerAuswahl}
                        onverwerfen={verwerfen} onspeichern={speichern} onfertig={bearbeitenBeenden} />
  {/if}
  {#if fehler}
    <div class="fehlertext" style="margin-bottom:12px">{fehler}
      {#if konflikt}<button class="knopf klein" style="margin-left:10px" onclick={() => { bearbeitenBeenden(); void laden(); }}>Neu laden (eigene Änderungen verwerfen)</button>{/if}</div>
  {/if}
  {#if bearbeiten && offeneVorschlaege.length}
    <div class="optionen" style="margin-bottom:12px">
      <span class="titel"><i class="fa-solid fa-wand-magic-sparkles"></i> KI-Korrektur</span>
      <span style="font-size:var(--klein); color:var(--text-2)">{vorschlaege.length} Vorschläge: {Object.values(entscheidungen).filter((z) => z === "uebernommen").length} übernommen,
        {Object.values(entscheidungen).filter((z) => z === "verworfen").length} verworfen, {offeneVorschlaege.length} offen</span>
      <span class="knopfzeile" style="margin-left:auto">
        <button class="knopf" onclick={() => offeneVorschlaege.forEach((v) => entscheiden(v, "uebernommen"))}>Alle offenen übernehmen</button>
        <button class="knopf still" onclick={() => offeneVorschlaege.forEach((v) => entscheiden(v, "verworfen"))}>Alle verwerfen</button>
      </span>
    </div>
  {/if}
{/snippet}

{#snippet leiste(a: TranskriptAntwort)}
  <TranskriptLeiste antwort={a} {anfrage} {zeit} {bearbeiten} vorschlaege={bearbeiten ? 0 : offeneVorschlaege.length} onspringen={springen}
                    entwurf={bearbeiten ? entwurf : null} {ungespeichert} onzuordnen={bearbeitenBeginnen}
                    zuordnung={bearbeiten ? { neu: neuerSprecher, umbenennen: sprecherUmbenennen, zusammenfuehren } : null}
                    onneu={(a) => { antwort = a; if (bearbeiten) entwurf = structuredClone($state.snapshot(a.transkript)) as Transkript; }}
                    onmarker={markerSpeichern} onvorschlaege={() => api.vorschlaege(id).then((v) => (vorschlaege = v))}
                    onansehen={() => { bearbeitenBeginnen(); mehr = false; }} />
{/snippet}

{#if !antwort}
  {#if fehler}
    <div class="seiten-kopf"><button class="knopf still" onclick={zurueck}><i class="fa-solid fa-chevron-left"></i> {anfrage ? "Kellerwolke" : "Transkripte"}</button></div>
    <div class="rollfeld"><div class="fehlertext">{fehler}</div></div>
  {:else}<div class="leer">Lädt ...</div>{/if}
{:else if geraet.mobil}
  <!-- über die ganze Höhe: der Spieler steht immer unten über den Reitern, auch bei wenig Text -->
  <div class="t-ansicht">
  {#if anfrage}<AnfrageBand {anfrage} pfad={herkunft(antwort)} />{/if}
  <div class="knopfzeile" style="margin-bottom:8px">
    {@render suchfeld(true)}
    {#if !bearbeiten}
      <button class="rund" aria-label="Bearbeiten" title="Bearbeiten" onclick={bearbeitenBeginnen}><i class="fa-solid fa-pen"></i></button>
    {/if}
    <button class="rund" aria-label="Mehr" class:aktiv={mehr} onclick={() => (mehr = !mehr)}><i class="fa-solid fa-ellipsis-vertical"></i></button>
  </div>
  {#if mehr}
    <div class="karte" style="padding:0; margin-bottom:10px">{@render leiste(antwort)}</div>
  {/if}
  {@render oberhalbText()}
  <div bind:this={rollfeld} ontouchmove={selbstGerollt} onwheel={selbstGerollt} role="region" aria-label="Text">{@render text()}</div>
  <Spieler bind:this={spieler} src={api.tonAdresse(id, anfrage)} dauer={antwort.transkript.dauer_s} wellenform={welle ?? antwort.transkript.wellenform}
           {spur} marker={(t?.marker ?? []).map((m) => m.zeit)} bind:zeit bind:laeuft {stoppBei} kompakt />
  </div>
{:else}
  <div class="geruest-innen">
    <section class="seite">
      <div class="seiten-kopf">
        <button class="knopf still" style="padding:0 6px" onclick={zurueck}><i class="fa-solid fa-chevron-left"></i> {anfrage ? "Kellerwolke" : "Transkripte"}</button>
        <h1 class="titel-lang" title={antwort.transkript.name}>{antwort.transkript.name}</h1>
        {@render suchfeld(false)}
        {#if !bearbeiten}
          <button class="knopf" onclick={bearbeitenBeginnen} title="Text, Sprecher, Zeiten und Marker ändern"><i class="fa-solid fa-pen"></i> Bearbeiten</button>
        {/if}
        <button class="knopf nur-schmal" title="Sprecher, Marker, Export, KI, Versionen" onclick={leisteOeffnen}>
          <i class="fa-solid fa-table-columns"></i> Leiste</button>
      </div>
      {#if anfrage}<div style="padding:0 22px"><AnfrageBand {anfrage} pfad={herkunft(antwort)} /></div>{/if}
      <Spieler bind:this={spieler} src={api.tonAdresse(id, anfrage)} dauer={antwort.transkript.dauer_s} wellenform={welle ?? antwort.transkript.wellenform}
               {spur} marker={(t?.marker ?? []).map((m) => m.zeit)} bind:zeit bind:laeuft {stoppBei} />
      <div class="rollfeld" style="padding-top:14px" bind:this={rollfeld} onwheel={selbstGerollt} ontouchmove={selbstGerollt}
           role="region" aria-label="Text">
        <div class="text-flaeche">
          {@render oberhalbText()}
          {@render text()}
          {#if !segmente.length}<p class="leer">In dieser Aufnahme wurde nichts gesprochen.</p>{/if}
        </div>
      </div>
    </section>
    <Leiste>{@render leiste(antwort)}</Leiste>
  </div>
{/if}

<svelte:window onkeydowncapture={bearbeitenTasten} />
