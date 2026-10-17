<script lang="ts">
  // Sprecherprofile: Liste, rechts das gewählte Profil mit Proben zum Anhören (Ausschnitt aus dem Ton des
  // Transkripts), Umbenennen, Zusammenführen, Löschen (mit zweitem Klick). Schwellen kommen aus den Einstellungen.
  // Am Telefon: Liste, Antippen öffnet das Profil (/sprecher/<kennung>). Entwurf: mockups/transkription.html (5).
  import { onMount } from "svelte";
  import { Auswahl, gehe, geraet, Leiste, leisteOeffnen, navigation, wann } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import type { Profil } from "../lib/typen";
  import { farbe, marke } from "../lib/zeit";

  const WENIGE = 3;
  let liste = $state<Profil[]>([]);
  let suche = $state("");
  let fehler = $state("");
  let name = $state("");
  let ziel = $state<string | null>(null);
  let loeschFrage = $state(false);
  let sicher = $state<number | null>(null);
  let vorschlag = $state<number | null>(null);
  let probe = $state<string | null>(null);
  let gewaehltId = $state<string | null>(null);

  const kennung = $derived(navigation.seite === "sprecher" ? navigation.teile[0] ?? null : null);
  const sichtbar = $derived(liste.filter((p) => !suche.trim() || p.name.toLowerCase().includes(suche.trim().toLowerCase())));
  const gewaehlt = $derived(liste.find((p) => p.id === (kennung ?? gewaehltId)) ?? (geraet.mobil ? null : sichtbar[0] ?? null));
  const andere = $derived(liste.filter((p) => p.id !== gewaehlt?.id).map((p) => ({ wert: p.id as string | null, titel: p.name })));

  $effect(() => {
    name = gewaehlt?.name ?? "";
    loeschFrage = false;
    ziel = null;
    if (kennung && gewaehlt) navigation.titel = gewaehlt.name;
  });

  async function machen(arbeit: () => Promise<Profil[]>) {
    fehler = "";
    try {
      liste = await arbeit();
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  onMount(() => {
    void machen(api.profile);
    api.einstellung<number>("sprecher_sicher").then((w) => (sicher = w));
    api.einstellung<number>("sprecher_vorschlag").then((w) => (vorschlag = w));
  });

  function waehlen(p: Profil) {
    if (geraet.mobil) gehe(`sprecher/${p.id}`);
    else {
      gewaehltId = p.id;
      leisteOeffnen();
    }
  }

  function umbenennen() {
    if (gewaehlt && name.trim() && name.trim() !== gewaehlt.name) void machen(() => api.profilUmbenennen(gewaehlt!.id, name.trim()));
  }

  function zusammenfuehren() {
    if (gewaehlt && ziel) {
      const quelle = ziel;
      void machen(() => api.profileZusammenfuehren(gewaehlt!.id, quelle));
    }
  }

  function loeschen() {
    if (!gewaehlt) return;
    if (!loeschFrage) {
      loeschFrage = true;
      return;
    }
    const id = gewaehlt.id;
    void machen(() => api.profilLoeschen(id)).then(() => kennung && gehe("sprecher"));
  }

  const anfang = (n: string) => n.trim().charAt(0).toUpperCase() || "?";
</script>

{#snippet detail(p: Profil)}
  <div class="abschnitt">Name</div>
  <label class="eingabe"><input bind:value={name} onkeydown={(e) => e.key === "Enter" && umbenennen()} onblur={umbenennen} /></label>
  <div class="abschnitt">Proben</div>
  <div class="liste-klein">
    {#each p.beispiele as b, i (i)}
      <div><button class="rund" style="width:30px;height:30px" title={probe === `${b.transkript_id}-${b.start}` ? "Anhalten" : "Anhören"}
                   onclick={() => (probe = probe === `${b.transkript_id}-${b.start}` ? null : `${b.transkript_id}-${b.start}`)}>
          <i class="fa-solid {probe === `${b.transkript_id}-${b.start}` ? 'fa-pause' : 'fa-play'}"></i></button>
        <span><button style="border:0;background:none;padding:0;font:inherit;color:var(--akzent);cursor:pointer"
                      onclick={() => gehe(`transkripte/${b.transkript_id}/${b.start}`)}>{marke(b.start)}</button>
          {b.text ? ` · "${b.text.slice(0, 60)}${b.text.length > 60 ? " ..." : ""}"` : ""}</span>
        {#if probe === `${b.transkript_id}-${b.start}`}
          <audio src="{api.tonAdresse(b.transkript_id)}#t={b.start},{b.ende}" autoplay onpause={() => (probe = null)} hidden></audio>
        {/if}
      </div>
    {:else}
      <p class="leer" style="padding:4px 0; text-align:left">Noch keine Proben gemerkt.</p>
    {/each}
  </div>
  <div class="abschnitt">Erkennung</div>
  <dl class="werte">
    <dt>Sicher ab</dt><dd>{sicher ?? ""} % Ähnlichkeit (Einstellung)</dd>
    <dt>Vorschlag ab</dt><dd>{vorschlag ?? ""} %, du bestätigst</dd>
    <dt>Proben</dt><dd>{p.proben}, zuletzt {wann(p.geaendert_am)}</dd>
  </dl>
  <div class="knopfzeile" style="margin-top:20px">
    {#if andere.length}
      <Auswahl bind:wert={ziel} optionen={[{ wert: null, titel: "Zusammenführen mit ..." }, ...andere]} symbol="fa-object-group" />
      {#if ziel}<button class="knopf" onclick={zusammenfuehren}>{andere.find((a) => a.wert === ziel)?.titel} geht in {p.name} auf</button>{/if}
    {/if}
    <button class="knopf gefahr" onclick={loeschen}><i class="fa-solid fa-trash"></i> {loeschFrage ? "Wirklich löschen?" : "Löschen"}</button>
  </div>
  {#if fehler}<div class="fehlertext">{fehler}</div>{/if}
{/snippet}

{#snippet zeile(p: Profil, i: number)}
  <div class="profil" class:gewaehlt={!geraet.mobil && gewaehlt?.id === p.id} role="button" tabindex="0"
       onclick={() => waehlen(p)} onkeydown={(e) => e.key === "Enter" && waehlen(p)}>
    <span class="bild" style="background:{farbe(`s${i + 1}`)}">{anfang(p.name)}</span>
    <div><div class="name">{p.name}</div>
      <div class="unter">in {p.transkripte} Transkript{p.transkripte === 1 ? "" : "en"} · {p.proben} Probe{p.proben === 1 ? "" : "n"} · zuletzt {wann(p.geaendert_am)}</div></div>
    <span class="stand-pille {p.proben < WENIGE ? 'offen' : 'fertig'}">{p.proben < WENIGE ? "wenige Proben" : "sicher"}</span>
  </div>
{/snippet}

{#if geraet.mobil}
  {#if kennung}
    {#if gewaehlt}{@render detail(gewaehlt)}{:else if liste.length}<p class="leer">Dieses Profil gibt es nicht (mehr).</p>{/if}
  {:else}
    {#each sichtbar as p, i (p.id)}{@render zeile(p, i)}{:else}<p class="leer">Noch keine Profile.</p>{/each}
    <p class="leer" style="padding:14px">Ein Profil entsteht, wenn du einem erkannten Sprecher einen Namen als Profil gibst.</p>
  {/if}
{:else}
  <div class="geruest-innen">
    <section class="seite">
      <div class="seiten-kopf">
        <h1>Sprecher</h1>
        <label class="suche" style="min-width:200px"><i class="fa-solid fa-magnifying-glass"></i>
          <input class="eingabe-roh" placeholder="Name suchen" bind:value={suche} /></label>
      </div>
      <div class="rollfeld">
        {#each sichtbar as p, i (p.id)}{@render zeile(p, i)}{:else}<p class="leer">{suche ? "Niemand gefunden." : "Noch keine Profile."}</p>{/each}
        <p class="leer" style="padding:14px">Ein Profil entsteht, wenn du einem erkannten Sprecher einen Namen als Profil gibst; jede
          bestätigte Zuordnung schärft den Abdruck.</p>
      </div>
    </section>
    <Leiste>
      {#if gewaehlt}
        <div class="leiste-kopf"><h2>{gewaehlt.name}</h2><span class="fassung">Stimmabdruck aus {gewaehlt.proben === 1 ? "einer Probe" : `${gewaehlt.proben} Proben`}</span></div>
        <div class="rollfeld">{@render detail(gewaehlt)}</div>
      {:else}
        <div class="leiste-kopf"><h2>Kein Profil gewählt</h2></div>
      {/if}
    </Leiste>
  </div>
{/if}
