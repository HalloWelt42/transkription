// Was die App gerade tut, das ein Neuladen (neue Fassung) abbräche: Wiedergabe, Aufnahme, Hochladen, ungespeicherte
// Änderungen. Die Schale fragt es über `ruhig` ab.
export const arbeit = $state({ wiedergabe: false, aufnahme: false, hochladen: 0, ungespeichert: false });

export function ruhig(): boolean {
  return !arbeit.wiedergabe && !arbeit.aufnahme && arbeit.hochladen === 0 && !arbeit.ungespeichert;
}
