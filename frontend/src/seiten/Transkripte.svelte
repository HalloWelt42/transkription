<script lang="ts">
  // Transkripte: Verzeichnis mit Volltextsuche (Treffer mit Zeit, Klick springt in den Ton), Filter nach Sprache und
  // Sprecher, seitenweise; mit einer Kennung in der Adresse (/transkripte/<kennung>[/<sekunden>]) das Transkript selbst.
  // Entwurf: mockups/transkription.html (2) und transkription-mobil.html (4).
  import { onMount } from "svelte";
  import { Auswahl, gehe, geraet, navigation, wann } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import type { Verzeichnis } from "../lib/typen";
  import { marke, sprache as spracheName, SPRACHEN } from "../lib/zeit";
  import TranskriptAnsicht from "../teile/TranskriptAnsicht.svelte";

  const SEITE = 20;
  let suche = $state("");
  let sprache = $state<string | null>(null);
  let sprecher = $state<string[]>([]);
  let namen = $state<string[]>([]);
  let liste = $state<Verzeichnis | null>(null);
  let ab = $state(0);
  let fehler = $state("");

  const kennung = $derived(navigation.seite === "transkripte" ? navigation.teile[0] ?? null : null);
  const beginn = $derived(navigation.teile[1] != null && !Number.isNaN(Number(navigation.teile[1])) ? Number(navigation.teile[1]) : null);

  async function laden(anhaengen = false) {
    fehler = "";
    try {
      const neu = await api.verzeichnis({ suche: suche.trim(), sprache, sprecher, ab, anzahl: SEITE });
      liste = anhaengen && liste ? { ...neu, eintraege: [...liste.eintraege, ...neu.eintraege] } : neu;
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  onMount(() => {
    void laden();
    api.sprecherNamen().then((n) => (namen = n)).catch(() => {});
  });

  let takt: ReturnType<typeof setTimeout>;
  function suchen() {
    clearTimeout(takt);
    takt = setTimeout(() => {
      ab = 0;
      void laden();
    }, 250);
  }

  function neu() {
    ab = 0;
    void laden();
  }

  const sprachOptionen = [{ wert: null as string | null, titel: "Alle Sprachen" },
    ...Object.entries(SPRACHEN).filter(([k]) => k !== "auto").map(([wert, titel]) => ({ wert: wert as string | null, titel }))];
  const sprecherOptionen = $derived([{ wert: null as string | null, titel: "Sprecher" },
    ...namen.filter((n) => !sprecher.includes(n)).map((n) => ({ wert: n as string | null, titel: n }))]);
  const begriffe = $derived(suche.trim().toLowerCase().split(/\s+/).filter(Boolean));

  function markiert(text: string): { t: string; treffer: boolean }[] {
    if (!begriffe.length) return [{ t: text, treffer: false }];
    const muster = new RegExp(`(${begriffe.map((b) => b.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
    return text.split(muster).filter(Boolean).map((t) => ({ t, treffer: begriffe.includes(t.toLowerCase()) }));
  }
</script>

{#snippet ausschnitt(text: string)}{#each markiert(text) as x, i (i)}{#if x.treffer}<mark>{x.t}</mark>{:else}{x.t}{/if}{/each}{/snippet}

{#if kennung}
  {#key kennung}<TranskriptAnsicht id={kennung} {beginn} />{/key}
{:else if geraet.mobil}
  <label class="suche" style="display:flex; color:var(--text); height:44px"><i class="fa-solid fa-magnifying-glass" style="color:var(--text-3)"></i>
    <input class="eingabe-roh" placeholder="In allen Transkripten suchen" bind:value={suche} oninput={suchen} />
    {#if suche}<button class="knopf still" style="height:auto; padding:0" aria-label="Suche leeren" onclick={() => { suche = ""; neu(); }}><i class="fa-solid fa-xmark"></i></button>{/if}</label>
  <div class="t-gruppe">{liste ? (suche.trim() ? `${liste.gesamt} mit Treffern` : `${liste.gesamt} Transkripte`) : ""}</div>
  {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
  <div class="t-liste">
    {#each liste?.eintraege ?? [] as e (e.id)}
      <button class="t-zeile" onclick={() => gehe(`transkripte/${e.id}`)}><i class="fa-solid fa-file-lines"></i>
        <span class="t-text"><span class="t-name">{e.name}</span>
          <span class="t-meta">{wann(e.geaendert_am)} · {suche.trim() ? `${e.treffer} Treffer` : marke(e.dauer_s)}</span></span></button>
      {#each e.fundstellen.slice(0, 1) as f, i (i)}
        <button class="t-treffer" style="border:0; background:none; text-align:left; font:inherit; width:100%" onclick={() => gehe(`transkripte/${e.id}/${f.zeit}`)}>
          <span class="zeit">{marke(f.zeit)}</span>{@render ausschnitt(f.ausschnitt)}</button>
      {/each}
    {:else}
      {#if liste}<div class="leer">{suche.trim() ? "Nichts gefunden." : "Noch keine Transkripte. Unter Aufnahmen hochladen oder aufnehmen."}</div>{/if}
    {/each}
  </div>
  {#if liste && liste.eintraege.length < liste.gesamt}
    <button class="knopf" style="width:100%; justify-content:center; margin-top:12px; height:46px"
            onclick={() => { ab = liste!.eintraege.length; void laden(true); }}>Weitere {Math.min(SEITE, liste.gesamt - liste.eintraege.length)} laden</button>
  {/if}
{:else}
  <div class="seiten-kopf">
    <h1>Transkripte</h1>
    <label class="suche" style="min-width:320px; color:var(--text)"><i class="fa-solid fa-magnifying-glass" style="color:var(--text-3)"></i>
      <input class="eingabe-roh" placeholder="In allen Transkripten suchen" bind:value={suche} oninput={suchen} />
      {#if suche}<button class="knopf still" style="height:auto; padding:0" aria-label="Suche leeren" onclick={() => { suche = ""; neu(); }}><i class="fa-solid fa-xmark"></i></button>{/if}</label>
    <Auswahl bind:wert={sprache} optionen={sprachOptionen} onwahl={neu} />
    <span class="chips">
      {#each sprecher as n (n)}<span class="chip">{n}<button aria-label="{n} entfernen" onclick={() => { sprecher = sprecher.filter((x) => x !== n); neu(); }}><i class="fa-solid fa-xmark"></i></button></span>{/each}
      {#if sprecherOptionen.length > 1}
        <Auswahl wert={null} optionen={sprecherOptionen} symbol="fa-plus" onwahl={(n) => { if (n) { sprecher = [...sprecher, n]; neu(); } }} />
      {/if}
    </span>
  </div>
  <div class="rollfeld">
    {#if fehler}<div class="fehlertext" style="margin-bottom:12px">{fehler}</div>{/if}
    {#if liste}<p style="margin:0 0 10px; font-size:var(--klein); color:var(--text-2)">
      {suche.trim() ? `${liste.gesamt} Transkripte mit Treffern, neueste zuerst` : `${liste.gesamt} Transkripte, zuletzt geändert zuerst`}</p>{/if}
    {#each liste?.eintraege ?? [] as e (e.id)}
      <div class="zeile" role="button" tabindex="0" onclick={() => gehe(`transkripte/${e.id}`)} onkeydown={(k) => k.key === "Enter" && gehe(`transkripte/${e.id}`)}>
        <span class="art"><i class="fa-solid fa-file-lines"></i></span>
        <div style="min-width:0"><div class="name">{e.name}</div>
          <div class="meta">{marke(e.dauer_s)} · {spracheName(e.sprache)}{e.sprecher.length ? ` · ${e.sprecher.join(", ")}` : ""} · geändert {wann(e.geaendert_am)}</div></div>
        {#if suche.trim()}<span class="stand-pille fertig">{e.treffer} Treffer</span>{:else}<span></span>{/if}
        <i class="fa-solid fa-chevron-right" style="color:var(--text-3); padding-right:10px"></i>
      </div>
      {#if e.fundstellen.length}
        <div class="treffer">
          {#each e.fundstellen as f, i (i)}
            <button style="border:0; background:none; text-align:left; font:inherit; padding:0; cursor:pointer" onclick={() => gehe(`transkripte/${e.id}/${f.zeit}`)}>
              <span class="zeit">{marke(f.zeit)}</span>{#if f.art === "marker"}<i class="fa-solid fa-flag" style="color:var(--warn)"></i> Marker "{@render ausschnitt(f.ausschnitt)}"{:else}{@render ausschnitt(f.ausschnitt)}{/if}</button>
          {/each}
          {#if e.treffer > e.fundstellen.length}<button style="border:0; background:none; text-align:left; font:inherit; padding:0; color:var(--akzent); cursor:pointer"
                  onclick={() => gehe(`transkripte/${e.id}`)}>{e.treffer - e.fundstellen.length} weitere Treffer</button>{/if}
        </div>
      {/if}
    {:else}
      {#if liste}<p class="leer">{suche.trim() ? "Nichts gefunden." : "Noch keine Transkripte. Unter Aufnahmen hochladen oder aufnehmen und transkribieren."}</p>{/if}
    {/each}
    {#if liste && liste.gesamt > SEITE}
      <div class="seitenzeile"><span>{ab + 1} bis {Math.min(ab + SEITE, liste.gesamt)} von {liste.gesamt}</span>
        <button class="knopf" disabled={ab === 0} onclick={() => { ab = Math.max(0, ab - SEITE); void laden(); }}><i class="fa-solid fa-chevron-left"></i> Zurück</button>
        <button class="knopf" disabled={ab + SEITE >= liste.gesamt} onclick={() => { ab += SEITE; void laden(); }}>Weiter <i class="fa-solid fa-chevron-right"></i></button>
      </div>
    {/if}
  </div>
{/if}
