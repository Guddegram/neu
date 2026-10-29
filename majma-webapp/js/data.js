// Datenquelle der Web-App.
//
// Im Moment liefert diese Datei DEMO-DATEN. Sobald klar ist, welchen Server die
// iPhone-App benutzt, wird nur diese Datei umgebaut: Jede Funktion holt ihre Daten
// dann von dort. Der Rest der App (Seiten, Design) bleibt unverändert, weil er nur
// diese Funktionen aufruft.

export const DEMO_MODE = true;

const SESSION_KEY = 'majma.session';
const BELLS_KEY = 'majma.bells';

const mosque = {
  name: 'Demo-Moschee',
  iban: 'DE00 0000 0000 0000 0000 00',
  accountHolder: 'Demo-Moschee e. V.',
  paypalUrl: null,
};

// Adhan-Zeit und Iqama-Abstand in Minuten. Sonnenaufgang ist kein Gebet (keine Iqama).
const prayerTimes = [
  { key: 'fajr', name: 'Fajr', adhan: '06:12', iqama: 20 },
  { key: 'sunrise', name: 'Sonnenaufgang', adhan: '07:58', iqama: null },
  { key: 'dhuhr', name: 'Dhuhr', adhan: '13:18', iqama: 10 },
  { key: 'asr', name: 'Asr', adhan: '15:24', iqama: 10 },
  { key: 'maghrib', name: 'Maghrib', adhan: '18:02', iqama: 5 },
  { key: 'isha', name: 'Isha', adhan: '19:34', iqama: 10 },
];

const needs = [
  { id: 'teppiche', category: 'Teppiche', icon: 'rug', title: 'Neue Teppiche Gebetsraum', short: 'Neue Teppiche', kind: 'money', daysLeft: 12, current: 1240, goal: 2000, supporters: 27, initials: ['AK', 'MS', 'YB'] },
  { id: 'heizung', category: 'Heizung', icon: 'flame', title: 'Heizkosten Winter', short: 'Heizkosten Winter', kind: 'money', daysLeft: 30, current: 750, goal: 3000, supporters: 14, initials: ['AK', 'MS', 'YB'] },
  { id: 'koran', category: 'Koran', icon: 'book', title: 'Koranständer', short: 'Koranständer', kind: 'goods', unit: 'Stück', daysLeft: 20, current: 8, goal: 20, supporters: 10, initials: ['AK', 'MS', 'YB'] },
  { id: 'reinigung', category: 'Reinigung', icon: 'bottle', title: 'Reinigungsmittel', short: 'Reinigungsmittel', kind: 'goods', unit: 'Packungen', daysLeft: 9, current: 3, goal: 10, supporters: 3, initials: ['MS', 'YB'] },
  { id: 'lampen', category: 'Lampen', icon: 'bulb', title: 'LED-Lampen Eingang', short: 'LED-Lampen', kind: 'money', daysLeft: 25, current: 540, goal: 600, supporters: 18, initials: ['AK', 'YB', 'MS'] },
];

const latestDonation = { who: 'Familie K.', needId: 'teppiche', minutesAgo: 5 };

const feed = [
  { id: 'f1', icon: 'calendar', title: 'Kermes am Samstag ab 11 Uhr', type: 'Veranstaltung', when: 'vor 2 Std' },
  { id: 'f2', icon: 'rug', title: 'Neue Teppiche: 62 % erreicht', type: 'Bedarf', when: 'gestern' },
  { id: 'f3', icon: 'school', title: 'Koranunterricht startet wieder', type: 'Schule', when: 'vor 3 Tagen' },
];

const demoUser = { firstName: 'Yusuf', name: 'Yusuf B.', initials: 'YB', role: 'Mitglied' };

const clone = (v) => JSON.parse(JSON.stringify(v));

function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Privater Modus o. Ä.: dann gilt die Einstellung nur bis zum Neuladen.
  }
}

export async function getMosque() {
  return clone(mosque);
}

// Gebetszeiten für einen Tag. Die Demo hat jeden Tag dieselben Zeiten;
// echte Zeiten pflegt später die Moschee.
export async function getPrayerTimes(_date) {
  return clone(prayerTimes);
}

export async function getNeeds() {
  return clone(needs);
}

export async function getLatestDonation() {
  return clone(latestDonation);
}

export async function getFeed() {
  return clone(feed);
}

export function getSession() {
  return readJSON(SESSION_KEY, null);
}

export async function login(email, password) {
  email = email.trim();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('Bitte gib eine gültige E-Mail-Adresse ein.');
  if (!password) throw new Error('Bitte gib dein Passwort ein.');
  // Demo: jedes Passwort wird angenommen. Mit dem echten Server prüft der das Passwort.
  const session = { email, user: demoUser };
  writeJSON(SESSION_KEY, session);
  return session;
}

export function logout() {
  writeJSON(SESSION_KEY, null);
}

// Welche Gebete eine Erinnerung bekommen (Glocke an/aus).
export function getBells() {
  return readJSON(BELLS_KEY, { fajr: true, sunrise: false, dhuhr: true, asr: true, maghrib: true, isha: false });
}

export function setBell(key, on) {
  const bells = getBells();
  bells[key] = on;
  writeJSON(BELLS_KEY, bells);
  return bells;
}
