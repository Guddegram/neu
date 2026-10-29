// Rechnen mit Gebetszeiten: nächstes Gebet, Countdown, Fortschritt, Datumstexte.

const MIN = 60 * 1000;

export function atTime(day, hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  const d = new Date(day);
  d.setHours(h, m, 0, 0);
  return d;
}

export function startOfDay(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

export function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

export function isSameDay(a, b) {
  return startOfDay(a).getTime() === startOfDay(b).getTime();
}

// Nur die fünf Gebete – Sonnenaufgang zählt nicht als „nächstes Gebet“.
const prayersOnly = (times) => times.filter((p) => p.iqama !== null);

// Liefert das nächste Gebet ab `now`. Läuft gerade die Zeit zwischen Adhan und Iqama,
// ist das laufende Gebet gemeint (phase = 'iqama'). Nach Isha kommt Fajr am nächsten Tag.
export function nextPrayer(times, now = new Date()) {
  const list = prayersOnly(times);
  const today = startOfDay(now);
  for (let i = 0; i < list.length; i++) {
    const p = list[i];
    const adhan = atTime(today, p.adhan);
    const iqama = new Date(adhan.getTime() + p.iqama * MIN);
    const prev = i > 0 ? atTime(today, list[i - 1].adhan) : atTime(addDays(today, -1), list[list.length - 1].adhan);
    if (now < adhan) return { prayer: p, adhan, iqama, phase: 'adhan', target: adhan, from: prev };
    if (now < iqama) return { prayer: p, adhan, iqama, phase: 'iqama', target: iqama, from: adhan };
  }
  const p = list[0];
  const adhan = atTime(addDays(today, 1), p.adhan);
  return {
    prayer: p,
    adhan,
    iqama: new Date(adhan.getTime() + p.iqama * MIN),
    phase: 'adhan',
    target: adhan,
    from: atTime(today, list[list.length - 1].adhan),
  };
}

// 0 … 1: wie weit die Zeit vom vorigen Gebet bis zum Ziel schon vergangen ist.
export function progress(next, now = new Date()) {
  const total = next.target - next.from;
  if (total <= 0) return 1;
  return Math.min(1, Math.max(0, (now - next.from) / total));
}

function remainingMinutes(target, now) {
  return Math.max(0, Math.ceil((target - now) / MIN));
}

// „1 Std 12 Min“ bzw. „12 Min“
export function durationText(target, now = new Date()) {
  const mins = remainingMinutes(target, now);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h} Std ${m} Min` : `${m} Min`;
}

// „1:12“ (Stunden:Minuten) für den Ring
export function clockText(target, now = new Date()) {
  const mins = remainingMinutes(target, now);
  return `${Math.floor(mins / 60)}:${String(mins % 60).padStart(2, '0')}`;
}

export function iqamaText(p) {
  return p.iqama === null ? '–' : `+${p.iqama} Min`;
}

export function longDate(d) {
  return d.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
}

export function shortDate(d) {
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// „Heute · 29.10.2026“, „Morgen · …“, „Gestern · …“, sonst Wochentag
export function dayLabel(d, now = new Date()) {
  const diff = Math.round((startOfDay(d) - startOfDay(now)) / (24 * 60 * MIN));
  const names = { 0: 'Heute', 1: 'Morgen', '-1': 'Gestern' };
  const name = names[diff] ?? d.toLocaleDateString('de-DE', { weekday: 'long' });
  return `${name} · ${shortDate(d)}`;
}
