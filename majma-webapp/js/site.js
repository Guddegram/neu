import { getMosque, getPrayerTimes } from './data.js';
import { nextPrayer, durationText } from './prayer.js';
import { icon } from './icons.js';

const features = [
  { title: 'Gebetszeiten', text: 'Täglich aktuell mit Iqama-Zeiten und Countdown bis zum nächsten Gebet.', icon: 'clock' },
  { title: 'Nachrichten', text: 'Direkt mit der Moschee schreiben – ohne private Nummern zu teilen.', icon: 'message' },
  { title: 'Feed', text: 'Ankündigungen, Veranstaltungen und Bilder aus deiner Gemeinde.', icon: 'feed' },
  { title: 'Spenden & Beiträge', text: 'Bedarf sehen und mit Apple Pay, PayPal oder Überweisung unterstützen.', icon: 'heart' },
  { title: 'Moscheeschule', text: 'Klassen, Hausaufgaben und Abgaben für Eltern, Kinder und Lehrkräfte.', icon: 'school' },
  { title: 'Familie', text: 'Kinder hinzufügen und Familienbeiträge gemeinsam verwalten.', icon: 'family' },
];

const admin = [
  { title: 'Mitglieder', text: 'Anfragen freigeben, Rollen und Co-Admins vergeben.' },
  { title: 'Finanzen', text: 'Buchungen, Fixkosten und Deckung im Blick.' },
  { title: 'Beiträge', text: 'Beitragstypen anlegen und Erinnerungen senden.' },
  { title: 'Gebetszeiten', text: 'Zeiten und Iqama pflegen, alle sehen es sofort.' },
];

const domain = location.host || 'diese Seite';
const steps = [
  { title: 'Seite öffnen', text: `Rufe ${domain} in Chrome, Samsung Internet oder einem anderen Browser auf.` },
  { title: 'Zum Startbildschirm', text: 'Im Browsermenü „Zum Startbildschirm hinzufügen“ oder „App installieren“ wählen.' },
  { title: 'Wie eine App nutzen', text: 'Majma startet im Vollbild mit eigenem Symbol – anmelden und loslegen.' },
];

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

document.querySelectorAll('[data-icon]').forEach((el) => {
  el.innerHTML = icon(el.dataset.icon, { size: el.dataset.icon === 'arrow' ? 18 : 20, width: el.dataset.icon === 'arrow' ? 2.2 : 1.8 });
});

document.getElementById('features').innerHTML = features.map((f) => `
  <div class="feature">
    <span class="feature-icon">${icon(f.icon)}</span>
    <h3>${esc(f.title)}</h3>
    <p>${esc(f.text)}</p>
  </div>`).join('');

document.getElementById('admin').innerHTML = admin.map((a) => `
  <div class="admin-tile"><strong>${esc(a.title)}</strong><span>${esc(a.text)}</span></div>`).join('');

document.getElementById('steps').innerHTML = steps.map((s, i) => `
  <div class="step">
    <span class="step-n">${i + 1}</span>
    <h3>${esc(s.title)}</h3>
    <p>${esc(s.text)}</p>
  </div>`).join('');

// Mobiles Menü
const menuButton = document.getElementById('menu-button');
const menu = document.getElementById('mobile-menu');
function setMenu(open) {
  menu.hidden = !open;
  menuButton.setAttribute('aria-expanded', String(open));
  menuButton.setAttribute('aria-label', open ? 'Menü schließen' : 'Menü öffnen');
  menuButton.innerHTML = icon(open ? 'close' : 'menu', { size: 20, width: 2 });
}
setMenu(false);
menuButton.addEventListener('click', () => setMenu(menu.hidden));
menu.addEventListener('click', (e) => { if (e.target.closest('a')) setMenu(false); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setMenu(false); });
// composedPath statt e.target: Das Symbol im Knopf wird beim Öffnen ausgetauscht.
document.addEventListener('click', (e) => {
  if (!menu.hidden && !e.composedPath().some((el) => el.classList?.contains('topnav'))) setMenu(false);
});

// Karte „Nächstes Gebet“
async function renderPrayerCard() {
  const [mosque, times] = await Promise.all([getMosque(), getPrayerTimes(new Date())]);
  const now = new Date();
  const next = nextPrayer(times, now);
  document.querySelectorAll('[data-mosque-name]').forEach((el) => { el.textContent = mosque.name; });
  document.getElementById('pc-name').textContent = next.prayer.name;
  document.getElementById('pc-time').textContent = next.prayer.adhan;
  document.getElementById('pc-sub').textContent = next.phase === 'adhan'
    ? `in ${durationText(next.adhan, now)} · Iqama +${next.prayer.iqama} Min`
    : `Iqama in ${durationText(next.iqama, now)}`;
  document.getElementById('pc-list').innerHTML = times
    .filter((p) => p.iqama !== null)
    .map((p) => `<div class="pc-row${p.key === next.prayer.key ? ' current' : ''}"><span>${esc(p.name)}</span><span>${esc(p.adhan)}</span></div>`)
    .join('');
}
renderPrayerCard();
setInterval(renderPrayerCard, 30 * 1000);

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
