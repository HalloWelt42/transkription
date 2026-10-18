<script lang="ts">
  // Alle Dateien der Kellerwolke als Quelle (Entwurf mockups/verbund.html 6b am Rechner, 6e am Telefon), mit der
  // Dateiwahl des Appkerns: wählbar sind Ton und Video ohne Transkript, das Transkript kommt neben die Datei. Eigen ist
  // der Transkription nur, wie sie startet (Sprache, Sprecher, Anzahl).
  import { onMount } from "svelte";
  import { Auswahl, Dateiwahl, SPRACHEN, type WahlSeite, type WahlZweck } from "appkern-oberflaeche";
  import * as api from "../lib/api";
  import { ANZAHL_OPTIONEN, SPRECHER_WEGE, type SprecherWeg } from "../lib/sprecherwahl";

  // `ordner`: der gezeigte Ordner (null: "Meine Dateien"); `kette` meldet den Weg dorthin an die Seite (Chips, Hoch).
  let { ordner, suche = "", kette = $bindable([]) }: { ordner: string | null; suche?: string; kette?: WahlSeite["kette"] } = $props();

  let sprache = $state("de");
  let sprecher = $state<SprecherWeg>("ohne");
  let anzahl = $state<number | null>(null);
  const sprachOptionen = Object.entries(SPRACHEN).map(([wert, titel]) => ({ wert, titel }));

  onMount(() => {
    void (async () => {
      sprache = (await api.einstellung<string>("sprache")) ?? "de";
      sprecher = (await api.einstellung<SprecherWeg>("sprecher_weg")) ?? "ohne";
    })().catch(() => {});
  });

  const zweck: WahlZweck = {
    auftrag: "transkribieren",
    quelle: (a) => String(a.eingabe.quelle_id),
    ergebnis: ["transkript"],
    ordnerAdresse: (id) => `aufnahmen/kellerwolke/${id}`,
    woerter: {
      tun: "Transkribieren", symbol: "fa-closed-captioning", fertig: "transkribiert", offen: "ohne Transkript",
      gruppe: "Ton und Video", leer: "Hier liegt kein Ton und kein Video.", andere: "kein Ton",
      nichtWaehlbar: "Nur Ton und Video lassen sich transkribieren",
      hinweis: "Hier siehst du nur Namen. Lesen darf die App eine Datei erst, wenn du sie zum Transkribieren wählst, und nur bis der Auftrag fertig ist. Das Transkript liegt dann neben der Datei.",
      hinweisKurz: "Lesen darf die App nur, was du wählst, und nur für den Auftrag.",
      anleitung: "Ton und Video ohne Transkript anklicken, um sie zum Transkribieren zu wählen.",
    },
    starten: async (ids) => {
      await api.ausKellerwolke({ knoten_ids: ids, sprache, sprecher, anzahl: sprecher !== "ohne" ? anzahl : null });
      return `${ids.length} ${ids.length === 1 ? "Datei wird" : "Dateien werden"} transkribiert; das Transkript kommt jeweils neben die Datei.`;
    },
  };
</script>

<Dateiwahl {zweck} {ordner} {suche} bind:kette>
  {#snippet optionen()}
    <label>Sprache <Auswahl bind:wert={sprache} optionen={sprachOptionen} /></label>
    <label>Sprecher <Auswahl bind:wert={sprecher} optionen={SPRECHER_WEGE} /></label>
    {#if sprecher !== "ohne"}<label>Anzahl <Auswahl bind:wert={anzahl} optionen={ANZAHL_OPTIONEN} /></label>{/if}
  {/snippet}
</Dateiwahl>
