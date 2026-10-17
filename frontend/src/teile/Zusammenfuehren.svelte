<script lang="ts">
  // Eine Ablage (Entwurf mockups/verbund.html 6d): solange die frühere getrennte Ablage Transkripte noch besteht, steht
  // über den Aufnahmen die Vorschau, was wohin kommt, und der Knopf zum Zusammenführen. Nichts wird gelöscht; der leere
  // Ordner geht in den Papierkorb der Kellerwolke. Der Auftrag läuft unter Aufträge, danach lädt die Liste neu.
  import { onMount } from "svelte";
  import { beiAuftrag } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import type { Umzugsplan, Umzugsschritt } from "../lib/typen";

  let { onfertig }: { onfertig: () => void } = $props();

  const ZEIGEN = 50;   // so viele Schritte in der Vorschau, der Rest als Zahl
  let plan = $state<Umzugsplan | null>(null);
  let vorschau = $state(true);
  let laeuft = $state<{ fortschritt: number | null; schritt: string } | null>(null);
  let fehler = $state("");

  async function laden() {
    try {
      plan = await api.zusammenfuehrenPlan();
    } catch {
      plan = null;   // ohne Plan kein Band; die Liste darunter bleibt nutzbar
    }
  }

  onMount(() => {
    void laden();
    return beiAuftrag((a) => {
      if (a.art !== "zusammenfuehren") return;
      if (a.zustand === "wartet" || a.zustand === "laeuft") laeuft = { fortschritt: a.fortschritt, schritt: a.schritt };
      else {
        laeuft = null;
        if (a.zustand !== "fertig") fehler = a.fehler ?? "Zusammenführen gescheitert";
        void laden();
        onfertig();
      }
    });
  });

  async function starten() {
    fehler = "";
    try {
      const a = await api.zusammenfuehren();
      laeuft = { fortschritt: a.fortschritt, schritt: a.schritt };
    } catch (f) {
      fehler = (f as Error).message;
    }
  }

  // Pfade ab dem Zweig der App ("Transkripte/Besprechungen/..."), wie im Entwurf
  const wurzel = $derived.by(() => {
    const ordner = plan?.schritte.find((s) => s.art === "ordner");
    return ordner ? ordner.von.slice(0, ordner.von.lastIndexOf("/") + 1) : "";
  });
  const kurz = (pfad: string) => (wurzel && pfad.startsWith(wurzel) ? pfad.slice(wurzel.length) : pfad);
  const umzuege = $derived((plan?.zahlen.begleiter ?? 0) + (plan?.zahlen.daneben ?? 0));
  const ohne = $derived(plan?.zahlen.ohne_aufnahme ?? 0);

  const PILLE: Record<Umzugsschritt["art"], { klasse: string; text: string; titel: string } | null> = {
    begleiter: { klasse: "fertig", text: "neben die Aufnahme", titel: "Wird Begleiter der Aufnahme und zieht künftig mit ihr um" },
    daneben: { klasse: "warn", text: "zweites Transkript", titel: "Zu dieser Aufnahme gibt es schon ein neueres Transkript; das ältere liegt als eigene Datei daneben" },
    ohne_aufnahme: { klasse: "offen", text: "ohne Aufnahme", titel: "Die Aufnahme liegt im Papierkorb oder fehlt" },
    ordner: null,
  };
</script>

{#if plan?.noetig}
  <div class="hinweis-band"><i class="fa-solid fa-code-merge"></i>
    {#if laeuft}
      <span><b>Wird zusammengeführt:</b> {laeuft.schritt || "wartet"}{laeuft.fortschritt != null ? ` (${Math.round(laeuft.fortschritt * 100)} %)` : ""}</span>
    {:else if umzuege + ohne === 0}
      <span><b>Eine Ablage:</b> Transkripte liegen jetzt neben ihrer Aufnahme. Der frühere Ordner Transkripte ist leer und
        geht beim Zusammenführen in den Papierkorb der Kellerwolke.</span>
    {:else}
      <span><b>Eine Ablage:</b> Transkripte liegen künftig neben ihrer Aufnahme (wie in der Kellerwolke).
        {umzuege} {umzuege === 1 ? "zieht" : "ziehen"} um{ohne ? `, ${ohne} ${ohne === 1 ? "hat" : "haben"} keine Aufnahme mehr` : ""}. Nichts wird gelöscht.</span>
    {/if}
    {#if !laeuft}
      <span class="knopfzeile">
        <button class="knopf still" onclick={() => (vorschau = !vorschau)}>{vorschau ? "Vorschau ausblenden" : "Vorschau zeigen"}</button>
        <button class="knopf primaer" onclick={starten}><i class="fa-solid fa-code-merge"></i> Zusammenführen</button>
      </span>
    {/if}
  </div>
  {#if fehler}<div class="fehlertext" style="margin-bottom:12px">{fehler}</div>{/if}
  {#if vorschau && !laeuft}
    <div class="umzug-liste">
      <div class="u-zeile u-kopf"><span></span><span>Jetzt</span><span></span><span>Danach</span><span></span></div>
      {#each plan.schritte.slice(0, ZEIGEN) as s (s.knoten_id)}
        {@const p = PILLE[s.art]}
        <div class="u-zeile">
          <i class="fa-solid {s.art === 'ordner' ? 'fa-folder' : 'fa-closed-captioning'}"></i>
          <code title={s.von}><bdi>{kurz(s.von)}</bdi></code><i class="fa-solid fa-arrow-right"></i><code title={s.nach}><bdi>{kurz(s.nach)}</bdi></code>
          {#if p}<span class="stand-pille {p.klasse}" title={p.titel}>{p.text}</span>{:else}<span></span>{/if}
        </div>
      {/each}
      {#if plan.schritte.length > ZEIGEN}
        <div class="u-zeile u-mehr">und {plan.schritte.length - ZEIGEN} weitere, ebenso</div>
      {/if}
    </div>
  {/if}
{/if}
