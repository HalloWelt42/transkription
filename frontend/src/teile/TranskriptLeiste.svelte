<script lang="ts">
  // Leiste eines Transkripts, wie im Entwurf (mockups/transkription.html, 3): Sprecher mit Anteil, Profilvorschlag zum
  // Übernehmen, Umbenennen (als Profil oder nur hier) und Neu erkennen; Marker; Export (Download, auf Wunsch auch als
  // Datei daneben); KI über die Leitstelle (Korrigieren, Auswerten nach Vorlage); Versionen. Laufende Aufträge zu
  // diesem Transkript stehen in ihrem Abschnitt; fertige laden nach.
  import { onMount } from "svelte";
  import { Auswahl, beiAuftrag, wann, type Auftrag } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { ANZAHL_OPTIONEN, ERKENNEN_WEGE, type ErkennenWeg } from "../lib/sprecherwahl";
  import type { ExportFormat, Marker, Profil, TranskriptAntwort, Version, Vorlage } from "../lib/typen";
  import { farbe, marke } from "../lib/zeit";

  let {
    antwort,
    zeit,
    bearbeiten = false,
    vorschlaege = 0,
    onspringen,
    onneu,
    onmarker,
    onvorschlaege,
    onansehen,
  }: {
    antwort: TranskriptAntwort;
    zeit: number;
    bearbeiten?: boolean;
    vorschlaege?: number;
    onspringen: (t: number) => void;
    onneu: (a: TranskriptAntwort) => void;
    onmarker: (liste: Marker[]) => Promise<void>;
    onvorschlaege: () => void;
    onansehen: () => void;
  } = $props();

  const t = $derived(antwort.transkript);
  let profile = $state<Profil[]>([]);
  let versionen = $state<Version[] | null>(null);
  let alleVersionen = $state(false);
  let fehler = $state("");
  let meldung = $state("");
  let modus = $state<"" | "umbenennen" | "erkennen" | "auswerten" | "marker">("");
  let namen = $state<Record<string, string>>({});
  let alsProfil = $state(true);
  let anzahl = $state<number | null>(null);
  let erkennenWeg = $state<ErkennenWeg>("stimmen");
  let markerTitel = $state("");
  let ablegen = $state(false);
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
      if (a.art === "sprecher_erkennen") void api.transkript(antwort.id).then((neu) => { onneu(neu); meldung = "Sprecher neu erkannt."; });
      if (a.art === "korrigieren") onvorschlaege();
      if (a.art === "auswerten") meldung = `Auswertung liegt in der Kellerwolke: ${a.ergebnis?.pfad}`;
    });
  });

  $effect(() => {
    void antwort.stand;
    void versionenLaden();
  });

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

  function umbenennenBeginnen() {
    namen = Object.fromEntries(t.sprecher.map((s) => [s.kennung, s.name]));
    modus = modus === "umbenennen" ? "" : "umbenennen";
  }

  function umbenennenSpeichern() {
    void machen(async () => {
      let aktuell = antwort;
      const geaendert = t.sprecher.filter((s) => (namen[s.kennung] ?? "").trim() && namen[s.kennung].trim() !== s.name);
      if (alsProfil) {
        for (const s of geaendert) {
          aktuell = await api.profilZuordnen(antwort.id, s.kennung, { stand: aktuell.stand, name: namen[s.kennung].trim() });
        }
      } else if (geaendert.length) {
        aktuell = await api.aendern(antwort.id, { stand: aktuell.stand, sprecher: t.sprecher.map((s) => ({
          kennung: s.kennung, name: (namen[s.kennung] ?? s.name).trim() || s.name })) });
      }
      onneu(aktuell);
      profile = await api.profile();
      modus = "";
    });
  }

  function markerSetzen() {
    const titel = markerTitel.trim();
    if (!titel) return;
    void machen(async () => {
      await onmarker([...t.marker, { id: crypto.getRandomValues(new Uint32Array(4)).join("-"), zeit: Math.round(zeit * 10) / 10,
        titel, farbe: "gelb" as const }]);
      markerTitel = "";
      modus = "";
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

  function tag(iso: string): string {
    const w = wann(iso);
    return w.startsWith("heute") ? "heute" : w.startsWith("gestern") ? "gestern" : new Date(iso).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
  }

  const uhr = (iso: string) => new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const FORMATE: [ExportFormat, string][] = [["txt", "Text"], ["md", "Markdown"], ["srt", "Untertitel SRT"], ["vtt", "WebVTT"],
    ["docx", "DOCX"], ["json", "JSON"]];
  const VORLAGEN: [Vorlage, string, string][] = [["protokoll", "Protokoll", "Zusammenfassung, Themen, Entscheidungen, Aufgaben"],
    ["zusammenfassung", "Zusammenfassung", "fünf bis zehn Sätze und Kernaussagen"], ["aufgaben", "Aufgaben", "Was, wer, bis wann"]];
  const lauf = (art: string) => {
    const a = laufend[art];
    if (!a) return "";
    return `${a.zustand === "wartet" ? "wartet" : a.schritt || "läuft"}${a.fortschritt != null ? ` (${Math.round(a.fortschritt * 100)} %)` : ""}`;
  };
</script>

<div class="rollfeld leiste-inhalt">
  {#if fehler}<div class="gruppe"><div class="fehlertext" style="margin:0">{fehler}</div></div>{/if}
  {#if meldung}<div class="gruppe hinweis-zeile"><i class="fa-solid fa-circle-info"></i> {meldung}</div>{/if}

  <div class="gruppe">
    <h3>Sprecher</h3>
    {#each t.sprecher as s (s.kennung)}
      <div class="sprecher-zeile">
        {#if modus === "umbenennen"}
          <label class="eingabe klein-eingabe"><span class="punkt" style="width:10px;height:10px;border-radius:5px;background:{farbe(s.kennung)}"></span>
            <input bind:value={namen[s.kennung]} list="profilnamen" aria-label="Name von {s.name}" /></label>
        {:else}
          <span class="sprecher"><span class="punkt" style="background:{farbe(s.kennung)}"></span>{s.name}
            {#if s.profil_id}<i class="fa-solid fa-user-check" style="color:var(--text-3)" title="als Profil bestätigt"></i>{/if}</span>
        {/if}
        <span class="anteil">{anteile[s.kennung] ?? 0} %</span>
        {#if s.vorschlag_id && !s.profil_id && modus !== "umbenennen"}
          <div class="vorschlag-chip"><i class="fa-solid fa-user-check" style="color:var(--akzent)"></i>
            <span>klingt wie <b>{profilName(s.vorschlag_id)}</b> ({Math.round((s.vorschlag_aehnlichkeit ?? 0) * 100)} % ähnlich)</span>
            <button class="knopf klein" style="margin-left:auto"
                    onclick={() => machen(async () => onneu(await api.profilZuordnen(antwort.id, s.kennung, { stand: antwort.stand, profil_id: s.vorschlag_id! })))}>Übernehmen</button></div>
        {/if}
      </div>
    {:else}
      <p class="leer-zeile">Ohne Sprecher transkribiert.</p>
    {/each}
    <datalist id="profilnamen">{#each profile as p (p.id)}<option value={p.name}></option>{/each}</datalist>
    {#if modus === "umbenennen"}
      <label class="schalter-zeile"><button class="schalter" class:an={alsProfil} aria-label="Als Profil merken" aria-pressed={alsProfil}
             onclick={() => (alsProfil = !alsProfil)}></button>als Profil merken (wird künftig wiedererkannt)</label>
      <div class="knopfreihe"><button class="knopf klein primaer" onclick={umbenennenSpeichern}>Speichern</button>
        <button class="knopf klein still" onclick={() => (modus = "")}>Abbrechen</button></div>
    {:else if modus === "erkennen"}
      <div class="knopfreihe"><span class="beschriftung">Weg</span><Auswahl bind:wert={erkennenWeg} optionen={ERKENNEN_WEGE} klein /></div>
      <div class="knopfreihe"><span class="beschriftung">Anzahl</span><Auswahl bind:wert={anzahl} optionen={ANZAHL_OPTIONEN} klein />
        <button class="knopf klein primaer" onclick={() => machen(async () => { await api.sprecherErkennen(antwort.id, erkennenWeg, anzahl); modus = ""; })}>Starten</button>
        <button class="knopf klein still" onclick={() => (modus = "")}>Abbrechen</button></div>
    {:else}
      <div class="knopfreihe">
        {#if t.sprecher.length}<button class="knopf klein still" onclick={umbenennenBeginnen} disabled={bearbeiten}><i class="fa-solid fa-pen"></i> Umbenennen</button>{/if}
        <button class="knopf klein still" onclick={() => (modus = "erkennen")} disabled={!!laufend.sprecher_erkennen || bearbeiten}>
          <i class="fa-solid fa-rotate"></i> Neu erkennen</button>
      </div>
    {/if}
    {#if laufend.sprecher_erkennen}<p class="lauf-zeile"><i class="fa-solid fa-circle-notch fa-spin"></i> {lauf("sprecher_erkennen")}</p>{/if}
  </div>

  <div class="gruppe">
    <h3>Marker</h3>
    <div class="liste-klein">
      {#each t.marker as m (m.id)}
        <div class="marker-eintrag"><button class="zeit" onclick={() => onspringen(m.zeit)}>{marke(m.zeit)}</button>
          <span class="marker-titel"><i class="fa-solid fa-flag" style="color:var(--warn)"></i> {m.titel}</span>
          <button class="weg" title="Marker entfernen" onclick={() => machen(() => onmarker(t.marker.filter((x) => x.id !== m.id)))}><i class="fa-solid fa-xmark"></i></button></div>
      {:else}
        <p class="leer-zeile">Noch keine Marker.</p>
      {/each}
    </div>
    {#if modus === "marker"}
      <div class="knopfreihe"><label class="eingabe klein-eingabe" style="flex:1"><input placeholder="Titel des Markers bei {marke(zeit)}" bind:value={markerTitel}
             onkeydown={(e) => e.key === "Enter" && markerSetzen()} /></label>
        <button class="knopf klein primaer" onclick={markerSetzen}>Setzen</button>
        <button class="knopf klein still" onclick={() => (modus = "")}>Abbrechen</button></div>
    {:else}
      <button class="knopf klein still" onclick={() => (modus = "marker")}><i class="fa-solid fa-plus"></i> Marker bei {marke(zeit)}</button>
    {/if}
  </div>

  <div class="gruppe">
    <h3>Export</h3>
    <div class="knopfreihe">{#each FORMATE as [f, titel] (f)}<button class="knopf klein" onclick={() => exportieren(f)}>{titel}</button>{/each}</div>
    <label class="schalter-zeile"><button class="schalter" class:an={ablegen} aria-label="Auch als Datei ablegen" aria-pressed={ablegen}
           onclick={() => (ablegen = !ablegen)}></button>zusätzlich neben das Transkript legen</label>
  </div>

  <div class="gruppe">
    <h3>KI über die Leitstelle</h3>
    {#if vorschlaege}
      <div class="vorschlag-chip" style="margin-bottom:10px"><i class="fa-solid fa-wand-magic-sparkles" style="color:var(--akzent)"></i>
        <span>{vorschlaege} {vorschlaege === 1 ? "Vorschlag wartet" : "Vorschläge warten"}</span>
        <button class="knopf klein" style="margin-left:auto" onclick={onansehen}>Ansehen</button></div>
    {/if}
    {#if modus === "auswerten"}
      <div class="vorlagen">
        {#each VORLAGEN as [v, titel, inhalt] (v)}
          <button class="vorlage" onclick={() => machen(async () => { await api.auswerten(antwort.id, v); modus = ""; })}>
            <b>{titel}</b><span>{inhalt}</span></button>
        {/each}
        <button class="knopf klein still" onclick={() => (modus = "")}>Abbrechen</button>
      </div>
    {:else}
      <div class="knopfreihe">
        <button class="knopf klein" disabled={!!laufend.korrigieren} onclick={() => machen(() => api.korrigieren(antwort.id))}>
          <i class="fa-solid fa-wand-magic-sparkles"></i> Korrigieren</button>
        <button class="knopf klein" disabled={!!laufend.auswerten} onclick={() => (modus = "auswerten")}><i class="fa-solid fa-list-ul"></i> Auswerten</button>
      </div>
    {/if}
    {#each ["korrigieren", "auswerten"] as art (art)}
      {#if laufend[art]}<p class="lauf-zeile"><i class="fa-solid fa-circle-notch fa-spin"></i> {art === "korrigieren" ? "Korrektur" : "Auswertung"}: {lauf(art)}</p>{/if}
    {/each}
    <p class="hilfe-zeile">Korrigieren macht Vorschläge je Beitrag; übernommen wird nur, was du bestätigst.</p>
  </div>

  <div class="gruppe" style="border-bottom:0">
    <h3>Versionen</h3>
    <div class="versionen">
      {#each (alleVersionen ? versionen : versionen?.slice(0, 3)) ?? [] as v, i (v.id)}
        <div class="version-zeile">
          <span class="zeit">{tag(v.erstellt_am)}</span>
          <span class="version-text"><b>{(versionen?.length ?? 0) - i}</b> {uhr(v.erstellt_am)} · {v.notiz?.was ?? "geändert"}</span>
          {#if !v.aktuell && !bearbeiten && alleVersionen}
            <button class="knopf klein still" title="Diese Fassung als neue Version zurückholen" onclick={() => zurueck(v)}>
              {zurueckFrage === v.id ? "Wirklich?" : "Zurückholen"}</button>
          {/if}
        </div>
      {/each}
    </div>
    {#if (versionen?.length ?? 0) > 1}
      <button class="knopf klein still" onclick={() => (alleVersionen = !alleVersionen)}>
        <i class="fa-solid fa-clock-rotate-left"></i> {alleVersionen ? "Weniger" : "Alle Versionen"}</button>
    {/if}
  </div>
</div>
