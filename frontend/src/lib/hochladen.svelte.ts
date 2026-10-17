// Hochladen mit Fortschritt (fetch meldet beim Senden keinen Fortschritt, darum XMLHttpRequest). Die Liste der
// laufenden Uploads zeigt die Seite Aufnahmen; solange einer läuft, lädt die App nicht neu.
import { token } from "appkern-oberflaeche";
import { arbeit } from "./arbeit.svelte";
import type { Aufnahme } from "./typen";

export interface Upload {
  id: string;
  name: string;
  groesse: number;
  gesendet: number;
  fehler: string;
  fertig: boolean;
}

export const uploads = $state<{ liste: Upload[] }>({ liste: [] });

export function hochladen(daten: Blob, name: string): Promise<Aufnahme> {
  const eintrag: Upload = { id: crypto.getRandomValues(new Uint32Array(2)).join("-"), name, groesse: daten.size, gesendet: 0,
    fehler: "", fertig: false };
  uploads.liste = [eintrag, ...uploads.liste];
  const u = uploads.liste[0];
  arbeit.hochladen += 1;
  return new Promise<Aufnahme>((fertig, fehlgeschlagen) => {
    const x = new XMLHttpRequest();
    x.open("POST", `/api/v1/aufnahmen?name=${encodeURIComponent(name)}`);
    x.setRequestHeader("X-Kellerwolke-Sitzung", token());
    x.setRequestHeader("Content-Type", daten.type || "application/octet-stream");
    x.upload.onprogress = (e) => (u.gesendet = e.loaded);
    const ende = () => (arbeit.hochladen = Math.max(0, arbeit.hochladen - 1));
    x.onload = () => {
      ende();
      if (x.status === 201) {
        u.fertig = true;
        u.gesendet = u.groesse;
        setTimeout(() => (uploads.liste = uploads.liste.filter((z) => z.id !== u.id)), 4000);
        fertig(JSON.parse(x.responseText) as Aufnahme);
      } else {
        let meldung = `Fehler ${x.status}`;
        try {
          meldung = JSON.parse(x.responseText).detail ?? meldung;
        } catch {
          // Text bleibt
        }
        u.fehler = meldung;
        fehlgeschlagen(new Error(meldung));
      }
    };
    x.onerror = () => {
      ende();
      u.fehler = "Verbindung abgebrochen";
      fehlgeschlagen(new Error(u.fehler));
    };
    x.send(daten);
  });
}

export function entfernen(id: string): void {
  uploads.liste = uploads.liste.filter((u) => u.id !== id);
}
