<script lang="ts">
  // Leiste eines Transkripts: Sprecher (Anteil, Profilvorschlag übernehmen, umbenennen als Profil oder nur hier, neu
  // erkennen), Marker, Export (Download, auf Wunsch auch als Datei daneben), KI über die Leitstelle, Versionen.
  // Laufende Aufträge zu diesem Transkript stehen in ihrem Abschnitt; fertige laden das Transkript neu.
  import { onMount } from "svelte";
  import { beiAuftrag, wann, type Auftrag } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import type { ExportFormat, Marker, Profil, TranskriptAntwort, Version, Vorlage } from "../lib/typen";
  import { farbe, marke } from "../lib/zeit";
  import Auswahl from "./Auswahl.svelte";

  let {
    antwort,
    zeit,
    bearbeiten = false,
    onspringen,
    onneu,
    onmarker,
    onvorschlaege,
  }: {
    antwort: TranskriptAntwort;
    zeit: number;
    bearbeiten?: boolean;
    onspringen: (t: number) => void;
    onneu: (a: TranskriptAntwort) => void;
    onmarker: (liste: Marker[]) => Promise<void>;
    onvorschlaege: () => void;
  } = $props();

  const t = $derived(antwort.transkript);
  let profile = $state<Profil[]>([]);
  let versionen = $state<Version[] | null>(null);
  let alleVersionen = $state(false);
  let fehler = $state("");
  let meldung = $state("");
  let umbenennen = $state<string | null>(null);
  let neuerName = $state("");
  let markerTitel = $state("");
  let markerOffen = $state(false);
  let ablegen = $state(false);
  let vorlage = $state<Vorlage>("protokoll");
  let anzahl = $state<number | null>(null);
  let laufend = $state<Record<string, Auftrag>>({});
  let zurueckFrage = $state<string | null>(null);

  const anteile = $derived.by(() => {
    const summe: Record<string, number> = {};
    let gesamt = 0;
    for (const s of t.segmente) {
      if (!s.sprecher) continue;
      summe[s.sprecher] = (summe[s.sprecher] ?? 0) + (s.ende - s.start);
      gesamt += s.ende - s.start;
    }
    return Object.fromEntries(Object.entries(summe).map(([k, v]) => [k, gesamt ? Math.round((v / gesamt) * 100) : 0]));
  });

  async function versionenLaden() {
    try {
      versionen = await api.versionen(antwort.id);
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  onMount(() => {
    api.profile().then((p) => (profile = p)).catch(() => {});
    void versionenLaden();
    return beiAuftrag((a) => {
      if (a.eingabe.transkript_id !== antwort.id) return;
      if (a.zustand === "wartet" || a.zustand === "laeuft") {
        laufend = { ...laufend, [a.art]: a };
        return;
      }
      const { [a.art]: _, ...rest } = laufend;
      laufend = rest;
      if (a.zustand !== "fertig") {
        fehler = a.fehler ?? `${a.titel}: ${a.zustand}`;
        return;
      }
      if (a.art === "sprecher_erkennen") void neuLaden("Sprecher neu erkannt.");
      if (a.art === "korrigieren") {
        meldung = `${a.ergebnis?.vorschlaege ?? 0} Vorschläge der KI-Korrektur.`;
        onvorschlaege();
      }
      if (a.art === "auswerten") meldung = `Auswertung liegt in der Kellerwolke: ${a.ergebnis?.pfad}`;
    });
  });

  $effect(() => {
    void antwort.stand;
    void versionenLaden();
  });

  async function neuLaden(text = "") {
    onneu(await api.transkript(antwort.id));
    meldung = text;
  }

  async function machen(arbeit: () => Promise<unknown>) {
    fehler = "";
    meldung = "";
    try {
      await arbeit();
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  const profilName = (id: string | null | undefined) => profile.find((p) => p.id === id)?.name ?? "einem Profil";

  function uebernehmen(kennung: string, profil_id: string) {
    void machen(async () => onneu(await api.profilZuordnen(antwort.id, kennung, { stand: antwort.stand, profil_id })));
  }

  function benennen(kennung: string, alsProfil: boolean) {
    const name = neuerName.trim();
    if (!name) return;
    void machen(async () => {
      if (alsProfil) onneu(await api.profilZuordnen(antwort.id, kennung, { stand: antwort.stand, name }));
      else onneu(await api.aendern(antwort.id, { stand: antwort.stand, sprecher: t.sprecher.map((s) => ({
        kennung: s.kennung, name: s.kennung === kennung ? name : s.name })) }));
      umbenennen = null;
      profile = await api.profile();
    });
  }

  function markerHinzu() {
    const titel = markerTitel.trim();
    if (!titel) return;
    void machen(async () => {
      await onmarker([...t.marker, { id: crypto.getRandomValues(new Uint32Array(4)).join("-"), zeit: Math.round(zeit * 10) / 10,
        titel, farbe: "gelb" as const }]);
      markerTitel = "";
      markerOffen = false;
    });
  }

  function exportieren(format: ExportFormat) {
    const a = document.createElement("a");
    a.href = api.exportAdresse(antwort.id, format);
    a.download = "";
    a.click();
    if (ablegen) void machen(async () => (meldung = `Liegt auch in der Kellerwolke: ${(await api.exportAblegen(antwort.id, format)).pfad}`));
  }

  function zurueck(v: Version) {
    if (zurueckFrage !== v.id) {
      zurueckFrage = v.id;
      return;
    }
    zurueckFrage = null;
    void machen(async () => onneu(await api.zurueckholen(antwort.id, v.id, antwort.stand)));
  }

  const FORMATE: [ExportFormat, string][] = [["txt", "Text"], ["md", "Markdown"], ["srt", "Untertitel SRT"], ["vtt", "WebVTT"],
    ["docx", "DOCX"], ["json", "JSON"]];
  const VORLAGEN = [{ wert: "protokoll" as Vorlage, titel: "Protokoll" }, { wert: "zusammenfassung" as Vorlage, titel: "Zusammenfassung" },
    { wert: "aufgaben" as Vorlage, titel: "Aufgaben" }];
  const ANZAHL = [{ wert: null as number | null, titel: "Anzahl von selbst" }, ...[2, 3, 4, 5, 6].map((n) => ({ wert: n as number | null, titel: `${n} Sprecher` }))];
  const lauf = (art: string) => laufend[art] ? `${laufend[art].zustand === "wartet" ? "wartet" : laufend[art].schritt || "läuft"}${laufend[art].fortschritt != null ? ` (${Math.round(laufend[art].fortschritt! * 100)} %)` : ""}` : "";
</script>

<div class="rollfeld" style="padding:0">
  {#if fehler}<div class="gruppe"><div class="fehlertext" style="margin:0">{fehler}</div></div>{/if}
  {#if meldung}<div class="gruppe" style="font-size:var(--klein); color:var(--text-2)"><i class="fa-solid fa-circle-info" style="color:var(--akzent)"></i> {meldung}</div>{/if}

  <div class="gruppe">
    <h3>Sprecher</h3>
    {#each t.sprecher as s (s.kennung)}
      <div class="sprecher-zeile">
        <span class="sprecher"><span class="punkt" style="background:{farbe(s.kennung)}"></span>{s.name}
          {#if s.profil_id}<i class="fa-solid fa-user-check" style="color:var(--text-3)" title="Profil bestätigt"></i>{/if}</span>
        <span class="anteil">{anteile[s.kennung] ?? 0} %</span>
        {#if s.vorschlag_id && !s.profil_id}
          <div class="vorschlag-chip"><i class="fa-solid fa-user-check" style="color:var(--akzent)"></i>
            <span>klingt wie <b>{profilName(s.vorschlag_id)}</b> (ähnlich {String(s.vorschlag_aehnlichkeit ?? "").replace(".", ",")})</span>
            <button class="knopf klein" style="margin-left:auto" onclick={() => uebernehmen(s.kennung, s.vorschlag_id!)}>Übernehmen</button></div>
        {/if}
        {#if umbenennen === s.kennung}
          <div class="vorschlag-chip" style="flex-wrap:wrap">
            <input class="eingabe-roh" style="flex:1 1 140px" list="profilnamen" placeholder="Name" bind:value={neuerName}
                   onkeydown={(e) => e.key === "Enter" && benennen(s.kennung, true)} />
            <button class="knopf klein" onclick={() => benennen(s.kennung, true)} title="Als Sprecherprofil merken: wird künftig erkannt">Als Profil</button>
            <button class="knopf klein still" onclick={() => benennen(s.kennung, false)}>Nur hier</button>
          </div>
        {/if}
      </div>
    {:else}
      <p class="leer" style="padding:4px 0; text-align:left">Ohne Sprecher transkribiert.</p>
    {/each}
    <datalist id="profilnamen">{#each profile as p (p.id)}<option value={p.name}></option>{/each}</datalist>
    <div class="knopfreihe" style="margin-top:8px">
      {#if t.sprecher.length}
        <Auswahl wert={umbenennen} optionen={t.sprecher.map((s) => ({ wert: s.kennung as string | null, titel: `${s.name} umbenennen` }))}
                 symbol="fa-pen" onwahl={(k) => { umbenennen = k; neuerName = ""; }} />
      {/if}
      <Auswahl bind:wert={anzahl} optionen={ANZAHL} />
      <button class="knopf klein still" disabled={!!laufend.sprecher_erkennen || bearbeiten}
              onclick={() => machen(() => api.sprecherErkennen(antwort.id, anzahl))}><i class="fa-solid fa-rotate"></i> Neu erkennen</button>
    </div>
    {#if laufend.sprecher_erkennen}<p class="rekorder-stand" style="text-align:left; margin-top:6px"><i class="fa-solid fa-circle-notch fa-spin"></i> {lauf("sprecher_erkennen")}</p>{/if}
  </div>

  <div class="gruppe">
    <h3>Marker</h3>
    <div class="liste-klein">
      {#each t.marker as m (m.id)}
        <div><button class="zeit" style="border:0;background:none;cursor:pointer;padding:0;font:inherit" onclick={() => onspringen(m.zeit)}>{marke(m.zeit)}</button>
          <span style="flex:1"><i class="fa-solid fa-flag" style="color:var(--warn)"></i> {m.titel}</span>
          <button class="knopf still" style="height:auto;padding:0 4px" title="Marker entfernen"
                  onclick={() => machen(() => onmarker(t.marker.filter((x) => x.id !== m.id)))}><i class="fa-solid fa-xmark"></i></button></div>
      {:else}
        <p class="leer" style="padding:4px 0; text-align:left">Noch keine Marker.</p>
      {/each}
    </div>
    {#if markerOffen}
      <div class="vorschlag-chip" style="margin-top:6px">
        <input class="eingabe-roh" placeholder="Titel" bind:value={markerTitel} onkeydown={(e) => e.key === "Enter" && markerHinzu()} />
        <button class="knopf klein" onclick={markerHinzu}>Setzen</button></div>
    {:else}
      <button class="knopf klein still" style="margin-top:6px" onclick={() => (markerOffen = true)}><i class="fa-solid fa-plus"></i> Marker bei {marke(zeit)}</button>
    {/if}
  </div>

  <div class="gruppe">
    <h3>Export</h3>
    <div class="knopfreihe">{#each FORMATE as [f, titel] (f)}<button class="knopf klein" onclick={() => exportieren(f)}>{titel}</button>{/each}</div>
    <label style="display:flex; align-items:center; gap:10px; margin-top:10px; font-size:var(--klein); color:var(--text-2)">
      <button class="schalter" class:an={ablegen} aria-label="Auch als Datei ablegen" aria-pressed={ablegen} onclick={() => (ablegen = !ablegen)}></button>
      zusätzlich neben das Transkript legen</label>
  </div>

  <div class="gruppe">
    <h3>KI über die Leitstelle</h3>
    <div class="knopfreihe">
      <button class="knopf klein" disabled={!!laufend.korrigieren} onclick={() => machen(() => api.korrigieren(antwort.id))}>
        <i class="fa-solid fa-wand-magic-sparkles"></i> Korrigieren</button>
      <Auswahl bind:wert={vorlage} optionen={VORLAGEN} />
      <button class="knopf klein" disabled={!!laufend.auswerten} onclick={() => machen(() => api.auswerten(antwort.id, vorlage))}>
        <i class="fa-solid fa-list-ul"></i> Auswerten</button>
    </div>
    {#each ["korrigieren", "auswerten"] as art (art)}
      {#if laufend[art]}<p class="rekorder-stand" style="text-align:left; margin-top:6px"><i class="fa-solid fa-circle-notch fa-spin"></i> {lauf(art)}</p>{/if}
    {/each}
    <p style="margin:8px 0 0; font-size:var(--klein); color:var(--text-3)">Korrigieren macht Vorschläge je Beitrag; übernommen wird nur, was du bestätigst.</p>
  </div>

  <div class="gruppe" style="border-bottom:0">
    <h3>Versionen</h3>
    <div class="liste-klein">
      {#each (alleVersionen ? versionen : versionen?.slice(0, 3)) ?? [] as v, i (v.id)}
        <div>
          <span class="zeit">{new Date(v.erstellt_am).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}</span>
          <span style="flex:1"><b>{(versionen?.length ?? 0) - i}</b> {wann(v.erstellt_am).replace(/^heute |^gestern /, "")} · {v.notiz?.was ?? "geändert"}{v.notiz?.wer ? ` (${v.notiz.wer})` : ""}</span>
          {#if !v.aktuell && !bearbeiten}
            <button class="knopf klein still" onclick={() => zurueck(v)}>{zurueckFrage === v.id ? "Wirklich?" : "Zurückholen"}</button>
          {/if}
        </div>
      {/each}
    </div>
    {#if (versionen?.length ?? 0) > 3}
      <button class="knopf klein still" style="margin-top:6px" onclick={() => (alleVersionen = !alleVersionen)}>
        <i class="fa-solid fa-clock-rotate-left"></i> {alleVersionen ? "Weniger" : `Alle ${versionen?.length} Versionen`}</button>
    {/if}
  </div>
</div>
