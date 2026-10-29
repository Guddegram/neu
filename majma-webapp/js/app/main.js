// Einstieg der Web-App: Seitenwechsel (über die Adresse nach dem #), Navigation, Einblendungen.

import { getSession } from '../data.js';
import { icon } from '../icons.js';
import { esc, views } from './views.js';
import { maybeOfferInstall } from './install.js';

const root = document.getElementById('view');
const tabbar = document.getElementById('tabbar');
const sidebarNav = document.getElementById('sidebar-nav');
const sidebarUser = document.getElementById('sidebar-user');
const overlayRoot = document.getElementById('overlay-root');
const toastEl = document.getElementById('toast');

const tabs = [
  { route: 'start', label: 'Start', icon: 'home' },
  { route: 'moschee', label: 'Moschee', icon: 'mosque' },
  { route: 'feed', label: 'Feed', icon: 'feed' },
  { route: 'gebet', label: 'Gebet', icon: 'clock' },
  { route: 'profil', label: 'Profil', icon: 'user' },
];

const sideLinks = [
  { route: 'start', label: 'Start', icon: 'home' },
  { route: 'gebet', label: 'Gebetszeiten', icon: 'clock' },
  { route: 'feed', label: 'Feed', icon: 'feed' },
  { route: 'nachrichten', label: 'Nachrichten', icon: 'message' },
  { route: 'bedarf', label: 'Bedarf', icon: 'heart' },
  { route: 'schule', label: 'Schule', icon: 'school' },
  { route: 'profil', label: 'Profil', icon: 'user' },
];

tabbar.innerHTML = tabs.map((t) => `
  <a class="tab" href="#/${t.route}" data-route="${t.route}">
    <span class="tab-ico">${icon(t.icon, { size: 24 })}</span>${t.label}
  </a>`).join('');

sidebarNav.innerHTML = sideLinks.map((l) => `
  <a class="side-link" href="#/${l.route}" data-route="${l.route}">${icon(l.icon, { size: 22 })}${l.label}</a>`).join('');

let toastTimer;
function toast(text) {
  toastEl.textContent = text;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, 3200);
}

let closeCurrentSheet = null;
function openSheet(html, onMount) {
  closeCurrentSheet?.();
  const backdrop = document.createElement('div');
  backdrop.className = 'backdrop';
  backdrop.innerHTML = `<div class="sheet" role="dialog" aria-modal="true"><div class="handle"></div>${html}</div>`;
  overlayRoot.append(backdrop);
  const previousFocus = document.activeElement;
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  function close() {
    backdrop.remove();
    document.removeEventListener('keydown', onKey);
    closeCurrentSheet = null;
    previousFocus?.focus?.();
  }
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop || e.target.closest('[data-close]')) close(); });
  document.addEventListener('keydown', onKey);
  closeCurrentSheet = close;
  onMount?.(backdrop.querySelector('.sheet'), close);
  backdrop.querySelector('button, a')?.focus();
  return close;
}

function navigate(path) {
  location.hash = `#/${path}`;
}

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [name, query = ''] = raw.split('?');
  return { name: name || 'start', params: new URLSearchParams(query) };
}

let cleanup = null;
let renderId = 0;

async function render() {
  const { name, params } = parseHash();
  const session = getSession();
  const view = views[name] ? name : 'start';
  if (!session && view !== 'login') return navigate('login');
  if (session && view === 'login') return navigate('start');
  if (view !== name) return navigate(view);

  const def = views[view];
  const id = ++renderId;
  cleanup?.();
  cleanup = null;
  closeCurrentSheet?.();

  document.body.className = `route-${view} bg-${def.bg}`;
  root.classList.toggle('narrow', view !== 'start');
  document.title = def.title ? `${def.title} – Majma` : 'Majma';
  const active = def.nav ?? view;
  document.querySelectorAll('[data-route]').forEach((a) => {
    const on = a.dataset.route === active;
    a.classList.toggle('active', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  if (session) {
    sidebarUser.innerHTML = `<span class="avatar">${esc(session.user.initials)}</span><span><strong>${esc(session.user.name)}</strong><span>${esc(session.user.role)}</span></span>`;
  }

  const ctx = { session, params, navigate, toast, openSheet };
  const result = await def.render(root, ctx);
  if (id !== renderId) { result?.(); return; } // inzwischen schon weiter navigiert
  cleanup = result || null;
  window.scrollTo(0, 0);
  if (view === 'start') maybeOfferInstall(ctx);
}

window.addEventListener('hashchange', render);
render();

if ('serviceWorker' in navigator) navigator.serviceWorker.register('../sw.js').catch(() => {});
