<script lang="ts">
  // Aufnahmen: Ton- und Videodateien in Aufnahmen und in freigegebenen Ordnern, mit Stand; Hochladen (Knopf oder
  // Ziehen), Aufnehmen im Browser, Auswahl transkribieren. Am Telefon: großer Aufnahmeknopf, Datei wählen, die letzten.
  // Entwurf: mockups/transkription.html (1) und transkription-mobil.html (1, 2).
  import { onMount } from "svelte";
  import { Auswahl, beiAuftrag, gehe, geraet, hole, json, sitzung, wann } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { ANZAHL_OPTIONEN, SPRECHER_WEGE, type SprecherWeg } from "../lib/sprecherwahl";
  import { alsDatei, aufnahme, geraeteLaden, gespeicherte, quelleWechseln, starten as aufnehmen, verwerfen, type Gespeichert } from "../lib/aufnahme.svelte";
  import { entfernen, hochladen, uploads } from "../lib/hochladen.svelte";
  import type { Aufnahme, AufnahmenSeite, Ordner } from "../lib/typen";
  import { groesse, marke, SPRACHEN } from "../lib/zeit";
  import Rekorder from "../teile/Rekorder.svelte";

  type Filter = "alle" | "ohne" | "transkribiert";
  const SEITE = 50;

  let ordnerListe = $state<Ordner[]>([]);
  let ordner = $state<string | null>(null);
  let stapel = $state<Ordner[]>([]);           // Unterordner, in die man hineingegangen ist
  let filter = $state<Filter>("alle");
  let suche = $state("");
  let seite = $state<AufnahmenSeite | null>(null);
  let ab = $state(0);
  let gewaehlt = $state<string[]>([]);
  let sprache = $state("de");
  let sprecher = $state<SprecherWeg>("ohne");
  let anzahl = $state<number | null>(null);
  let fehler = $state("");
  let meldung = $state("");
  let ueber = $state(false);
  let liegen = $state<Gespeichert[]>([]);
  let eingabe: HTMLInputElement;
  let vorschau = $state<string | null>(null);
  let mobilOrdner = $state(false);

  const aktuellerOrdner = $derived(stapel.at(-1)?.id ?? ordner);

  async function laden() {
    fehler = "";
    try {
      seite = await api.aufnahmen({ ordner: aktuellerOrdner, filter, suche: suche.trim(), ab, anzahl: SEITE });
      gewaehlt = gewaehlt.filter((id) => seite!.eintraege.some((a) => a.id === id && a.stand !== "transkribiert"));
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  onMount(() => {
    (async () => {
      try {
        ordnerListe = await api.ordnerListe();
        ordner = ordnerListe[0]?.id ?? null;
        sprache = (await api.einstellung<string>("sprache")) ?? "de";
        sprecher = (await api.einstellung<SprecherWeg>("sprecher_weg")) ?? "ohne";
      } catch (f) {
        fehler = (f as Error).message;
      }
      await laden();
      liegen = await gespeicherte();
      await geraeteLaden();
    })();
    return beiAuftrag((a) => {
      if (a.art !== "transkribieren" || !seite) return;
      const zeile = seite.eintraege.find((x) => x.id === a.eingabe.quelle_id);
      if (!zeile) return;
      if (a.zustand === "fertig") void laden();
      else if (a.zustand === "wartet" || a.zustand === "laeuft") {
        zeile.stand = a.zustand === "laeuft" ? "laeuft" : "wartet";
        zeile.auftrag = { id: a.id, zustand: a.zustand, fortschritt: a.fortschritt, schritt: a.schritt, phase: a.phase };
      } else void laden();
    });
  });

  // Sobald eine Aufnahme gespeichert ist (noch vor der Entscheidung), steht sie in der Liste.
  let zuletztGespeichert = "";
  $effect(() => {
    const d = aufnahme.danach;
    if (d && d.id !== zuletztGespeichert) {
      zuletztGespeichert = d.id;
      void laden();
    }
  });

  let suchTakt: ReturnType<typeof setTimeout>;
  function suchen() {
    clearTimeout(suchTakt);
    suchTakt = setTimeout(() => {
      ab = 0;
      void laden();
    }, 250);
  }

  function filtern(f: Filter) {
    filter = f;
    ab = 0;
    void laden();
  }

  function ordnerWaehlen(id: string | null) {
    ordner = id;
    stapel = [];
    ab = 0;
    void laden();
  }

  function hinein(o: Ordner) {
    stapel = [...stapel, o];
    ab = 0;
    void laden();
  }

  function hoch() {
    stapel = stapel.slice(0, -1);
    ab = 0;
    void laden();
  }

  function waehlen(a: Aufnahme) {
    if (a.stand === "transkribiert") {
      gehe(`transkripte/${a.transkripte[0].id}`);
      return;
    }
    if (a.stand !== "ohne") return;
    gewaehlt = gewaehlt.includes(a.id) ? gewaehlt.filter((x) => x !== a.id) : [...gewaehlt, a.id];
  }

  async function dateienSenden(dateien: FileList | File[]) {
    meldung = "";
    for (const d of Array.from(dateien)) {
      try {
        await hochladen(d, d.name);
      } catch {
        // steht in der Liste der Uploads
      }
    }
    await laden();
  }

  async function transkribierenAlle() {
    fehler = "";
    try {
      for (const id of gewaehlt) {
        await api.transkribieren({ quelle_id: id, sprache, sprecher, anzahl: sprecher !== "ohne" ? anzahl : null });
      }
      meldung = `${gewaehlt.length} ${gewaehlt.length === 1 ? "Aufnahme wird" : "Aufnahmen werden"} transkribiert.`;
      gewaehlt = [];
      await laden();
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  async function liegendeHochladen(g: Gespeichert) {
    const fertig = await alsDatei(g.id);
    if (!fertig) return;
    try {
      const datei = await hochladen(fertig.daten, g.name);
      if (g.marker.length) await hole(`/aufnahmen/${datei.id}/marker`, { method: "PUT", ...json(g.marker) });
      await verwerfen(g.id);
      liegen = await gespeicherte();
      await laden();
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  async function liegendeVerwerfen(g: Gespeichert) {
    await verwerfen(g.id);
    liegen = await gespeicherte();
  }

  function aufnahmeFertig(text: string) {
    meldung = text;
    void laden();
  }

  function ablegen(e: DragEvent) {
    e.preventDefault();
    ueber = false;
    if (e.dataTransfer?.files.length) void dateienSenden(e.dataTransfer.files);
  }

  const ordnerOptionen = $derived(ordnerListe.map((o) => ({ wert: o.id as string | null, titel: o.pfad })));
  const sprachOptionen = Object.entries(SPRACHEN).map(([wert, titel]) => ({ wert, titel }));
  const ART = { ton: "fa-file-audio", video: "fa-file-video" };

  // "2:14:08 · M4A · 186 MB · heute 08:12" wie im Entwurf; die Dauer, sobald sie bekannt ist
  function metazeile(a: Aufnahme): string {
    const format = a.name.includes(".") ? a.name.slice(a.name.lastIndexOf(".") + 1).toUpperCase() : "";
    const teile = [a.dauer_s ? marke(a.dauer_s) : "", a.name.startsWith("Sprachnotiz") ? "aufgenommen" : format, groesse(a.groesse), wann(a.geaendert_am)];
    return teile.filter(Boolean).join(" · ");
  }

  function standText(a: Aufnahme): string {
    if (a.stand === "transkribiert") return a.transkripte.length > 1 ? `${a.transkripte.length} Transkripte` : "transkribiert";
    if (a.stand === "laeuft") return `${a.auftrag?.schritt?.split(",")[0] || "läuft"}${a.auftrag?.fortschritt != null ? ` ${Math.round(a.auftrag.fortschritt * 100)} %` : ""}`;
    if (a.stand === "wartet") return "wartet";
    return "ohne Transkript";
  }
</script>

<input type="file" multiple accept="audio/*,video/*" hidden bind:this={eingabe}
       onchange={(e) => { const d = e.currentTarget.files; if (d?.length) void dateienSenden(d); e.currentTarget.value = ""; }} />

{#snippet zeile(a: Aufnahme)}
  <div class="zeile" class:gewaehlt={gewaehlt.includes(a.id)} role="button" tabindex="0"
       onclick={() => waehlen(a)} onkeydown={(e) => e.key === "Enter" && waehlen(a)}>
    <span class="art"><i class="fa-solid {a.name.startsWith('Sprachnotiz') ? 'fa-microphone' : ART[a.art]}"></i></span>
    <div style="min-width:0">
      <div class="name">{a.name}</div>
      <div class="meta">{metazeile(a)}</div>
    </div>
    <span class="stand-pille {a.stand === 'transkribiert' ? 'fertig' : a.stand === 'laeuft' ? 'laeuft' : 'offen'}">
      {#if a.stand === "laeuft"}<i class="fa-solid fa-circle-notch fa-spin"></i>{/if} {standText(a)}</span>
    <button class="knopf still" title={vorschau === a.id ? "Anhalten" : "Anhören"}
            onclick={(e) => { e.stopPropagation(); vorschau = vorschau === a.id ? null : a.id; }}>
      <i class="fa-solid {vorschau === a.id ? 'fa-pause' : 'fa-play'}"></i></button>
  </div>
{/snippet}

{#snippet uploadListe()}
  {#each uploads.liste as u (u.id)}
    <div class="upload">
      <i class="fa-solid {u.fehler ? 'fa-triangle-exclamation' : u.fertig ? 'fa-check' : 'fa-upload'}"
         style="color:{u.fehler ? 'var(--gefahr)' : u.fertig ? 'var(--gut)' : 'var(--akzent)'}"></i>
      <span style="min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">{u.name}</span>
      <span style="color:var(--text-3)">{u.fehler || (u.fertig ? "fertig" : `${Math.round((u.gesendet / Math.max(u.groesse, 1)) * 100)} %`)}
        {#if u.fehler}<button class="knopf still" onclick={() => entfernen(u.id)} title="Ausblenden"><i class="fa-solid fa-xmark"></i></button>{/if}</span>
      {#if !u.fertig && !u.fehler}<div class="balken"><span style="width:{(u.gesendet / Math.max(u.groesse, 1)) * 100}%"></span></div>{/if}
    </div>
  {/each}
{/snippet}

{#snippet liegendeListe()}
  {#each liegen as g (g.id)}
    <div class="band" style="border-radius:var(--r2); margin-bottom:8px">
      <i class="fa-solid fa-microphone"></i>
      <span><b>Aufnahme vom {new Date(g.beginn).toLocaleString("de-DE")}</b> ({marke(g.dauer_ms / 1000)}) liegt noch auf diesem Gerät.</span>
      <button class="knopf" onclick={() => liegendeHochladen(g)}><i class="fa-solid fa-upload"></i> Hochladen</button>
      <button class="knopf still" onclick={() => liegendeVerwerfen(g)}>Verwerfen</button>
    </div>
  {/each}
{/snippet}

{#if vorschau}
  <audio src={api.aufnahmeAdresse(vorschau)} autoplay onended={() => (vorschau = null)} hidden></audio>
{/if}

{#if geraet.mobil}
  {#if aufnahme.laeuft || aufnahme.danach}
    <Rekorder onfertig={aufnahmeFertig} />
  {:else}
    {@render liegendeListe()}
    <div class="t-aufnehmen">
      <button class="rot" title="Aufnahme starten" onclick={aufnehmen}><i class="fa-solid fa-microphone"></i></button>
      <div><b>Aufnehmen</b></div>
      <div class="unter">Landet in Aufnahmen; transkribiert wird erst, wenn du es danach entscheidest.</div>
      {#if aufnahme.geraete.length > 1}
        <Auswahl wert={aufnahme.geraet} titel="Mikrofon" symbol="fa-microphone" onwahl={(g) => quelleWechseln(g)}
                 optionen={[{ wert: "", titel: "Standard des Systems" }, ...aufnahme.geraete.filter((g) => g.id && g.id !== "default").map((g) => ({ wert: g.id, titel: g.name }))]} />
      {/if}
    </div>
    {#if aufnahme.fehler}<div class="fehlertext">{aufnahme.fehler}</div>{/if}
    <div class="t-zweit">
      <button class="knopf" onclick={() => eingabe.click()}><i class="fa-solid fa-file-audio"></i> Datei wählen</button>
      <button class="knopf" class:zweit={mobilOrdner} onclick={() => (mobilOrdner = !mobilOrdner)}>
        <i class="fa-solid fa-folder-open"></i> Aus der Kellerwolke</button>
    </div>
    {#if meldung}<p class="leer" style="padding:10px 4px">{meldung}</p>{/if}
    {@render uploadListe()}
    {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
    {#if mobilOrdner}
      <div class="t-gruppe knopfzeile">
        <Auswahl bind:wert={ordner} optionen={ordnerOptionen} symbol="fa-folder" onwahl={ordnerWaehlen} />
        {#if stapel.length}<button class="knopf still" onclick={hoch}><i class="fa-solid fa-arrow-up"></i> {stapel.at(-1)?.name}</button>{/if}
      </div>
      {#if seite?.unterordner.length}
        <div class="t-liste" style="margin-bottom:10px">
          {#each seite.unterordner as o (o.id)}
            <button class="t-zeile" onclick={() => hinein(o)}><i class="fa-solid fa-folder"></i>
              <span class="t-text"><span class="t-name">{o.name}</span></span><i class="fa-solid fa-chevron-right" style="color:var(--text-3)"></i></button>
          {/each}
        </div>
      {/if}
    {:else}
      <div class="t-gruppe">Zuletzt</div>
    {/if}
    <div class="t-liste">
      {#each seite?.eintraege.slice(0, mobilOrdner ? SEITE : 15) ?? [] as a (a.id)}
        <button class="t-zeile" onclick={() => (a.stand === "ohne" ? api.transkribieren({ quelle_id: a.id }).then(laden) : waehlen(a))}>
          <i class="fa-solid {a.stand === 'transkribiert' ? 'fa-file-lines' : ART[a.art]}"></i>
          <span class="t-text"><span class="t-name">{a.name}</span><span class="t-meta">{standText(a)}</span></span>
          {#if a.stand === "laeuft"}<span class="stand-pille laeuft"><i class="fa-solid fa-circle-notch fa-spin"></i></span>
          {:else if a.stand === "ohne"}<span class="stand-pille offen">Transkribieren</span>
          {:else}<i class="fa-solid fa-chevron-right" style="color:var(--text-3)"></i>{/if}
        </button>
      {:else}
        <div class="leer">Noch keine Aufnahmen.</div>
      {/each}
    </div>
  {/if}
{:else}
  <div class="seiten-kopf">
    <h1>Aufnahmen</h1>
    <span class="segment">
      <button class:aktiv={filter === "alle"} onclick={() => filtern("alle")}>Alle {seite?.zahlen.alle ?? ""}</button>
      <button class:aktiv={filter === "ohne"} onclick={() => filtern("ohne")}>Ohne Transkript {seite?.zahlen.ohne ?? ""}</button>
      <button class:aktiv={filter === "transkribiert"} onclick={() => filtern("transkribiert")}>Transkribiert</button>
    </span>
    <label class="suche" style="min-width:200px"><i class="fa-solid fa-magnifying-glass"></i>
      <input class="eingabe-roh" placeholder="Name suchen" bind:value={suche} oninput={suchen} /></label>
    <span class="knopfzeile" style="margin-left:auto">
      <button class="knopf" onclick={aufnehmen} disabled={aufnahme.laeuft || !!aufnahme.danach}><i class="fa-solid fa-circle-dot" style="color:var(--gefahr)"></i> Aufnehmen</button>
      <button class="knopf primaer" onclick={() => eingabe.click()}><i class="fa-solid fa-upload"></i> Hochladen</button>
    </span>
  </div>
  <div class="rollfeld" role="region" aria-label="Aufnahmen"
       ondragover={(e) => { e.preventDefault(); ueber = true; }} ondragleave={() => (ueber = false)} ondrop={ablegen}>
    {#if aufnahme.laeuft || aufnahme.danach}<Rekorder kompakt onfertig={aufnahmeFertig} />{/if}
    {#if aufnahme.fehler}<div class="fehlertext" style="margin-bottom:12px">{aufnahme.fehler}</div>{/if}
    {@render liegendeListe()}
    <div class="ordnerzeile">
      Ordner <Auswahl bind:wert={ordner} optionen={ordnerOptionen} symbol="fa-folder" onwahl={ordnerWaehlen}
                      titel="Ordner, die du der App in der Kellerwolke freigegeben hast" />
      {#each stapel as o (o.id)}<span class="chip"><i class="fa-solid fa-folder-open"></i>{o.name}</span>{/each}
      {#if stapel.length}<button class="knopf still" onclick={hoch}><i class="fa-solid fa-arrow-up"></i> Hoch</button>{/if}
      {#if sitzung.app?.kellerwolke}
        <a class="knopf still" href="{sitzung.app.kellerwolke}/einstellungen/zugaenge" target="_blank" rel="noopener"
           title="In der Kellerwolke unter Zugänge der App weitere Ordner freigeben"><i class="fa-solid fa-folder-plus"></i> Ordner freigeben</a>
      {/if}
    </div>
    <div class="ablage" class:ueber><i class="fa-solid fa-cloud-arrow-up"></i> Dateien hierher ziehen: Ton (WAV, MP3, M4A, OGG,
      FLAC) oder Video (MP4, MOV, MKV).</div>
    {@render uploadListe()}
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
          <button class="knopf primaer" onclick={transkribierenAlle}><i class="fa-solid fa-play"></i> Transkribieren</button>
        </span>
      </div>
    {/if}

    {#each seite?.unterordner ?? [] as o (o.id)}
      <div class="zeile ordner-zeile" role="button" tabindex="0" onclick={() => hinein(o)} onkeydown={(e) => e.key === "Enter" && hinein(o)}>
        <span class="art"><i class="fa-solid fa-folder"></i></span>
        <div style="min-width:0"><div class="name">{o.name}</div><div class="meta">Ordner</div></div>
        <span></span><i class="fa-solid fa-chevron-right" style="color:var(--text-3); padding-right:10px"></i>
      </div>
    {/each}
    {#each seite?.eintraege ?? [] as a (a.id)}
      {@render zeile(a)}
    {:else}
      {#if seite && !seite.unterordner.length}
        <p class="leer">{suche ? "Nichts gefunden." : filter === "transkribiert" ? "Noch nichts transkribiert." : "Keine Aufnahmen in diesem Ordner. Hochladen, hierher ziehen oder aufnehmen."}</p>
      {/if}
    {/each}
    {#if seite?.eintraege.length && filter === "ohne"}
      <p class="leer" style="padding:14px">Bereits transkribierte Aufnahmen zeigt "Alle" oder "Transkribiert"; dort führt ein Klick zum Transkript.</p>
    {:else if seite?.eintraege.some((a) => a.stand === "ohne")}
      <p class="leer" style="padding:14px">Aufnahmen ohne Transkript anklicken, um sie zum Transkribieren zu wählen.</p>
    {/if}
    {#if seite && seite.gesamt > SEITE}
      <div class="seitenzeile"><span>{ab + 1} bis {Math.min(ab + SEITE, seite.gesamt)} von {seite.gesamt}</span>
        <button class="knopf" disabled={ab === 0} onclick={() => { ab = Math.max(0, ab - SEITE); void laden(); }}><i class="fa-solid fa-chevron-left"></i> Zurück</button>
        <button class="knopf" disabled={ab + SEITE >= seite.gesamt} onclick={() => { ab += SEITE; void laden(); }}>Weiter <i class="fa-solid fa-chevron-right"></i></button>
      </div>
    {/if}
  </div>
{/if}
