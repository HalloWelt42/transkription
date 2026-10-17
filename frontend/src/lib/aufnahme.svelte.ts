// Aufnehmen im Browser. Der Rekorder liefert alle zwei Sekunden ein Stück, das sofort in den Gerätespeicher
// (IndexedDB) geht: so übersteht eine Aufnahme ein Neuladen oder einen Absturz und lässt sich danach noch hochladen.
// Nach dem Beenden wird sie eine Datei; erst wenn sie in der Kellerwolke liegt, verschwindet sie vom Gerät. Während
// der Aufnahme bleibt der Bildschirm an (soweit der Browser das erlaubt) und die App lädt nicht neu.
import { arbeit } from "./arbeit.svelte";

const DB_NAME = "transkription-aufnahmen";
const STUECK_MS = 2000;
const PEGEL = 40;

export interface Gespeichert {
  id: string;
  name: string;
  typ: string;
  beginn: number;
  dauer_ms: number;
  marker: { zeit: number; titel: string }[];
  groesse: number;
}

export const aufnahme = $state({
  laeuft: false,
  pausiert: false,
  dauer_ms: 0,
  pegel: Array<number>(PEGEL).fill(0),
  marker: [] as { zeit: number; titel: string }[],
  name: "",
  fehler: "",
});

let rekorder: MediaRecorder | null = null;
let strom: MediaStream | null = null;
let ton: AudioContext | null = null;
let wachbleiben: { release(): Promise<void> } | null = null;
let aktuell: Gespeichert | null = null;
let takt: ReturnType<typeof setInterval> | null = null;
let zuletzt = 0;
let schreiben: Promise<void> = Promise.resolve();

// --- Gerätespeicher ---------------------------------------------------------------------------------------------

function oeffnen(): Promise<IDBDatabase> {
  return new Promise((fertig, fehler) => {
    const anfrage = indexedDB.open(DB_NAME, 1);
    anfrage.onupgradeneeded = () => {
      const db = anfrage.result;
      db.createObjectStore("aufnahmen", { keyPath: "id" });
      db.createObjectStore("stuecke", { autoIncrement: true }).createIndex("aufnahme", "aufnahme");
    };
    anfrage.onsuccess = () => fertig(anfrage.result);
    anfrage.onerror = () => fehler(anfrage.error);
  });
}

async function vorgang<T>(speicher: string[], modus: IDBTransactionMode, arbeit: (t: IDBTransaction) => IDBRequest<T> | void): Promise<T | undefined> {
  const db = await oeffnen();
  return new Promise((fertig, fehler) => {
    const t = db.transaction(speicher, modus);
    const anfrage = arbeit(t);
    t.oncomplete = () => {
      db.close();
      fertig(anfrage ? anfrage.result : undefined);
    };
    t.onerror = () => {
      db.close();
      fehler(t.error);
    };
  });
}

function merken(a: Gespeichert): Promise<unknown> {
  return vorgang(["aufnahmen"], "readwrite", (t) => t.objectStore("aufnahmen").put($state.snapshot(a)));
}

function stueckAblegen(id: string, daten: Blob): Promise<unknown> {
  return vorgang(["stuecke"], "readwrite", (t) => t.objectStore("stuecke").add({ aufnahme: id, daten }));
}

export async function gespeicherte(): Promise<Gespeichert[]> {
  try {
    const liste = (await vorgang(["aufnahmen"], "readonly", (t) => t.objectStore("aufnahmen").getAll())) as Gespeichert[];
    return (liste ?? []).filter((a) => a.id !== aktuell?.id).sort((a, b) => b.beginn - a.beginn);
  } catch {
    return [];
  }
}

export async function alsDatei(id: string): Promise<{ daten: Blob; info: Gespeichert } | null> {
  const info = (await vorgang(["aufnahmen"], "readonly", (t) => t.objectStore("aufnahmen").get(id))) as Gespeichert | undefined;
  if (!info) return null;
  const stuecke = (await vorgang(["stuecke"], "readonly", (t) => t.objectStore("stuecke").index("aufnahme").getAll(id))) as
    { daten: Blob }[];
  return { daten: new Blob(stuecke.map((s) => s.daten), { type: info.typ }), info };
}

export async function verwerfen(id: string): Promise<void> {
  const schluessel = (await vorgang(["stuecke"], "readonly", (t) => t.objectStore("stuecke").index("aufnahme").getAllKeys(id))) as IDBValidKey[];
  await vorgang(["aufnahmen", "stuecke"], "readwrite", (t) => {
    t.objectStore("aufnahmen").delete(id);
    for (const k of schluessel ?? []) t.objectStore("stuecke").delete(k);
  });
}

// --- Aufnehmen --------------------------------------------------------------------------------------------------

function format(): { mime: string; endung: string } {
  for (const [mime, endung] of [["audio/webm;codecs=opus", ".webm"], ["audio/mp4", ".m4a"], ["audio/ogg;codecs=opus", ".ogg"]]) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(mime)) return { mime, endung };
  }
  return { mime: "", endung: ".webm" };
}

export function vorschlagName(): string {
  const d = new Date();
  const z = (n: number) => String(n).padStart(2, "0");
  return `Sprachnotiz ${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}-${z(d.getMinutes())}`;
}

export async function starten(): Promise<void> {
  aufnahme.fehler = "";
  if (!navigator.mediaDevices?.getUserMedia) {
    aufnahme.fehler = "Aufnehmen geht hier nicht (der Browser erlaubt das Mikrofon nur über HTTPS oder am Rechner selbst).";
    return;
  }
  try {
    strom = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false } });
  } catch {
    aufnahme.fehler = "Kein Zugriff aufs Mikrofon (im Browser erlauben).";
    return;
  }
  const { mime, endung } = format();
  rekorder = new MediaRecorder(strom, mime ? { mimeType: mime } : undefined);
  const name = vorschlagName();
  aktuell = { id: `${Date.now()}`, name: `${name}${endung}`, typ: rekorder.mimeType || mime || "audio/webm",
    beginn: Date.now(), dauer_ms: 0, marker: [], groesse: 0 };
  aufnahme.name = name;
  aufnahme.marker = [];
  await merken(aktuell);
  rekorder.ondataavailable = (e) => {
    if (!aktuell || !e.data.size) return;
    const a = aktuell;
    a.groesse += e.data.size;
    a.dauer_ms = aufnahme.dauer_ms;
    schreiben = schreiben.then(() => stueckAblegen(a.id, e.data)).then(() => merken(a)).then(() => undefined);
  };
  rekorder.start(STUECK_MS);
  pegelMessen(strom);
  aufnahme.laeuft = true;
  aufnahme.pausiert = false;
  aufnahme.dauer_ms = 0;
  arbeit.aufnahme = true;
  zuletzt = performance.now();
  takt = setInterval(() => {
    const jetzt = performance.now();
    if (!aufnahme.pausiert) aufnahme.dauer_ms += jetzt - zuletzt;
    zuletzt = jetzt;
  }, 200);
  try {
    wachbleiben = await (navigator as unknown as { wakeLock?: { request(a: string): Promise<{ release(): Promise<void> }> } })
      .wakeLock?.request("screen") ?? null;
  } catch {
    wachbleiben = null;
  }
}

function pegelMessen(s: MediaStream): void {
  ton = new AudioContext();
  const analyse = ton.createAnalyser();
  analyse.fftSize = 512;
  ton.createMediaStreamSource(s).connect(analyse);
  const werte = new Uint8Array(analyse.fftSize);
  let letzte = 0;
  const schritt = (zeit: number) => {
    if (!aufnahme.laeuft) return;
    if (zeit - letzte > 100) {
      letzte = zeit;
      analyse.getByteTimeDomainData(werte);
      let spitze = 0;
      for (const w of werte) spitze = Math.max(spitze, Math.abs(w - 128));
      aufnahme.pegel = [...aufnahme.pegel.slice(1), aufnahme.pausiert ? 0 : Math.min(100, (spitze / 128) * 140)];
    }
    requestAnimationFrame(schritt);
  };
  requestAnimationFrame(schritt);
}

export function pause(): void {
  if (!rekorder || !aufnahme.laeuft) return;
  if (aufnahme.pausiert) rekorder.resume();
  else rekorder.pause();
  aufnahme.pausiert = !aufnahme.pausiert;
}

export function markerSetzen(): void {
  if (!aktuell) return;
  const m = { zeit: Math.round(aufnahme.dauer_ms / 100) / 10, titel: `Marker ${aufnahme.marker.length + 1}` };
  aufnahme.marker = [...aufnahme.marker, m];
  aktuell.marker = $state.snapshot(aufnahme.marker);
  void merken(aktuell);
}

// Beenden: liefert die Aufnahme als Datei (sie bleibt im Gerät, bis `verwerfen` nach dem Hochladen sie entfernt).
export async function beenden(name: string): Promise<{ daten: Blob; info: Gespeichert } | null> {
  if (!rekorder || !aktuell) return null;
  const r = rekorder;
  const fertig = new Promise<void>((ok) => (r.onstop = () => ok()));
  r.stop();
  await fertig;
  await schreiben;
  const a = aktuell;
  a.dauer_ms = aufnahme.dauer_ms;
  const endung = a.name.slice(a.name.lastIndexOf("."));
  a.name = `${name.trim() || aufnahme.name}${endung}`;
  await merken(a);
  aufraeumen();
  return alsDatei(a.id);
}

function aufraeumen(): void {
  strom?.getTracks().forEach((t) => t.stop());
  void ton?.close();
  void wachbleiben?.release().catch(() => {});
  if (takt) clearInterval(takt);
  rekorder = null;
  strom = null;
  ton = null;
  wachbleiben = null;
  aktuell = null;
  takt = null;
  aufnahme.laeuft = false;
  aufnahme.pausiert = false;
  aufnahme.pegel = Array<number>(PEGEL).fill(0);
  arbeit.aufnahme = false;
}
