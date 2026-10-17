<script lang="ts">
  // Die Bereiche der Transkription in der gemeinsamen Schale (Kopf, Navigation, Aufträge, Protokoll, Einstellungen).
  // Am Telefon sind Aufnahmen und Transkripte Reiter, Sprecher liegt unter Mehr.
  import { ereignisseBenennen, Schale, type Anfrage, type Bereich } from "appkern-oberflaeche";
  import * as api from "./lib/api";
  import Aufnahmen from "./seiten/Aufnahmen.svelte";
  import Sprecher from "./seiten/Sprecher.svelte";
  import Transkripte from "./seiten/Transkripte.svelte";

  ereignisseBenennen({
    "aufnahme.hochgeladen": "Aufnahme hochgeladen",
    "transkript.geloescht": "Transkript in den Papierkorb",
    "aufnahme.geloescht": "Aufnahme in den Papierkorb",
    "sprecher.ohne_trennung": "Sprecher ohne Sprechertrennung",
  });

  const bereiche: Bereich[] = [
    { schluessel: "aufnahmen", titel: "Aufnahmen", symbol: "fa-microphone-lines", seite: Aufnahmen, reiter: true },
    { schluessel: "transkripte", titel: "Transkripte", symbol: "fa-file-lines", seite: Transkripte, reiter: true },
    { schluessel: "sprecher", titel: "Sprecher", symbol: "fa-user-group", seite: Sprecher },
  ];

  // Aus der Kellerwolke geöffnet ("In Transkription öffnen", auch auf dem Transkript: dann gilt die Anfrage der
  // Aufnahme): das Transkript, wenn es eines gibt, sonst die Aufnahme zum Anhören und Transkribieren.
  async function oeffnen(a: Anfrage): Promise<string> {
    const aufnahme = await api.aufnahme(a.knoten_id, a.id);
    const t = aufnahme.transkripte[0];
    return t ? `transkripte/${t.id}/anfrage/${a.id}` : `aufnahmen/${a.knoten_id}/anfrage/${a.id}`;
  }
</script>

<Schale {bereiche} fassung={__APP_FASSUNG__} {oeffnen} />
