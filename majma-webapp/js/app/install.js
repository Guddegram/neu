// „Majma installieren“: Web-App auf den Startbildschirm legen (Android, Tablet, Computer).
// iPhones bekommen das Angebot nicht – dort gibt es die richtige App im App Store.

import { icon } from '../icons.js';

const DISMISS_KEY = 'majma.installDismissedAt';
const WAIT_DAYS = 7;

let deferredPrompt = null;
let offeredThisVisit = false;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault(); // eigenes Fenster statt der Browser-Leiste
  deferredPrompt = e;
});
window.addEventListener('appinstalled', () => { deferredPrompt = null; });

export function isInstalled() {
  return matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
}

export function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

export function canOfferInstall() {
  return !isInstalled() && !isIOS();
}

function dismissedRecently() {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY));
    return at && Date.now() - at < WAIT_DAYS * 24 * 60 * 60 * 1000;
  } catch {
    return false;
  }
}

function rememberDismiss() {
  try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* egal */ }
}

export function openInstallSheet(ctx) {
  ctx.openSheet(`
    <div class="sheet-head">
      <img src="../assets/icon-rounded.png" alt="">
      <div><h2>Majma installieren</h2><p>Kostenlos · ohne App Store</p></div>
    </div>
    <div class="perk"><span>${icon('grid', { size: 20 })}</span><span>Eigenes Symbol auf dem Startbildschirm</span></div>
    <div class="perk"><span>${icon('expand', { size: 20 })}</span><span>Startet im Vollbild wie eine App</span></div>
    <div class="perk"><span>${icon('bell', { size: 20 })}</span><span>Mitteilungen zu Gebetszeiten</span></div>
    <button class="btn-green" type="button" data-install>Zum Startbildschirm hinzufügen</button>
    <button class="btn-text" type="button" data-later>Später</button>
    <p class="hint" data-hint>Kein Button zu sehen? Im Browser auf <b>⋮</b> tippen und <b>„App installieren“</b> oder <b>„Zum Startbildschirm“</b> wählen.</p>
  `, (sheet, close) => {
    sheet.querySelector('[data-later]').addEventListener('click', () => { rememberDismiss(); close(); });
    sheet.querySelector('[data-install]').addEventListener('click', async () => {
      if (!deferredPrompt) {
        // Der Browser bietet die Installation nicht direkt an → Anleitung hervorheben.
        const hint = sheet.querySelector('[data-hint]');
        hint.classList.remove('flash');
        void hint.offsetWidth;
        hint.classList.add('flash');
        return;
      }
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      deferredPrompt = null;
      close();
      ctx.toast(outcome === 'accepted' ? 'Majma wird installiert.' : 'Installation abgebrochen.');
    });
  });
}

// Auf Handy und Tablet einmal pro Besuch auf der Startseite anbieten, außer kürzlich
// „Später“ gewählt. Am Computer nur über „Profil › App installieren“.
export function maybeOfferInstall(ctx) {
  if (offeredThisVisit || !canOfferInstall() || dismissedRecently()) return;
  if (!matchMedia('(max-width: 959.98px)').matches) return;
  offeredThisVisit = true;
  setTimeout(() => {
    if (location.hash.startsWith('#/start') || location.hash === '') openInstallSheet(ctx);
  }, 800);
}
