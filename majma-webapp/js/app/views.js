// Die Seiten der Web-App. Jede Seite füllt `root` und gibt optional eine
// Aufräum-Funktion zurück (z. B. um einen Countdown-Timer zu stoppen).

import {
  DEMO_MODE, getMosque, getPrayerTimes, getNeeds, getLatestDonation, getFeed,
  login, logout, getBells, setBell,
} from '../data.js';
import {
  nextPrayer, progress, durationText, clockText, iqamaText, longDate, dayLabel,
  addDays, startOfDay, isSameDay,
} from '../prayer.js';
import { icon } from '../icons.js';
import { canOfferInstall, openInstallSheet } from './install.js';

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const euro = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });
const percent = (n) => Math.round((n.current / n.goal) * 100);
const amountText = (n) => (n.kind === 'money'
  ? `${euro.format(n.current)} € von ${euro.format(n.goal)} €`
  : `${n.current} von ${n.goal} ${n.unit}`);

function pageTop(title, action = '<span></span>') {
  return `
    <div class="page-top">
      <a class="circle-btn only-mobile" href="#/start" aria-label="Zurück">${icon('back', { size: 22, width: 2 })}</a>
      <h1>${esc(title)}</h1>
      ${action}
    </div>`;
}

function feedItem(f) {
  return `
    <a class="list-item" href="#/feed">
      <span class="list-icon">${icon(f.icon, { size: 22 })}</span>
      <span class="list-text"><strong>${esc(f.title)}</strong><span>${esc(f.type)} · ${esc(f.when)}</span></span>
    </a>`;
}

/* ---------- Anmelden ---------- */

function renderLogin(root, ctx) {
  root.innerHTML = `
    <div class="login">
      <img class="login-logo" src="../assets/logo.png" alt="Majma">
      <h1>Willkommen zurück</h1>
      <p class="intro">Melde dich an, um deine Moschee zu sehen.</p>
      <form class="glass-card login-form" novalidate>
        <div class="form-error" role="alert" hidden></div>
        <label for="email">E-Mail</label>
        <input id="email" name="email" type="email" autocomplete="email" inputmode="email" placeholder="name@beispiel.de" required>
        <label for="password">Passwort</label>
        <input id="password" name="password" type="password" autocomplete="current-password" placeholder="••••••••" required>
        <button class="forgot" type="button" data-soon>Passwort vergessen?</button>
        <button class="btn-white" type="submit">Anmelden</button>
        <div class="or">oder</div>
        <button class="btn-ghost" type="button" data-soon>${icon('mail', { size: 20 })}Mit Code per E-Mail anmelden</button>
      </form>
      <p class="login-foot">Neu bei Majma? <button type="button" data-soon>Konto erstellen</button>
        <small>Funktioniert in Chrome, Samsung Internet, Firefox und Edge</small></p>
      ${DEMO_MODE ? '<p class="demo-pill" style="margin-top:18px">Demo-Modus: jede E-Mail und jedes Passwort funktioniert</p>' : ''}
    </div>`;

  const form = root.querySelector('form');
  const error = root.querySelector('.form-error');
  const submit = form.querySelector('[type=submit]');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    error.hidden = true;
    submit.disabled = true;
    submit.textContent = 'Wird angemeldet …';
    try {
      await login(form.email.value, form.password.value);
      ctx.navigate('start');
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      submit.disabled = false;
      submit.textContent = 'Anmelden';
    }
  });
  root.querySelectorAll('[data-soon]').forEach((b) => b.addEventListener('click', () => {
    ctx.toast('Das kommt, sobald Majma mit dem Server verbunden ist.');
  }));
}

/* ---------- Start ---------- */

function nextPrayerCard(times) {
  const now = new Date();
  const next = nextPrayer(times, now);
  const inIqama = next.phase === 'iqama';
  const remain = durationText(next.target, now);
  return `
    <div class="np-row">
      <span class="np-label">${inIqama ? 'Gleich Iqama' : 'Nächstes Gebet'}</span>
      <span class="np-label only-mobile">Iqama +${next.prayer.iqama} Min</span>
    </div>
    <div class="np-row"><span class="np-name">${esc(next.prayer.name)}</span><span class="np-time">${esc(next.prayer.adhan)}</span></div>
    <div class="bar"><span style="width:${(progress(next, now) * 100).toFixed(1)}%"></span></div>
    <span class="np-sub">${inIqama ? `Iqama in ${remain}` : `noch ${remain}`}<span class="only-desktop"> · Iqama +${next.prayer.iqama} Min</span></span>`;
}

async function renderStart(root, ctx) {
  const [mosque, times, needs, feed] = await Promise.all([getMosque(), getPrayerTimes(new Date()), getNeeds(), getFeed()]);
  const user = ctx.session.user;
  const now = new Date();
  const next = nextPrayer(times, now);
  const tiles = [
    { route: 'bedarf', label: 'Bedarf', icon: 'heart' },
    { route: 'nachrichten', label: 'Nachrichten', icon: 'message' },
    { route: 'schule', label: 'Schule', icon: 'school' },
    { route: 'beitraege', label: 'Beiträge', icon: 'card' },
  ];

  root.innerHTML = `
    <div class="home-top only-mobile">
      <img class="home-logo" src="../assets/logo.png" alt="Majma">
      <div class="home-actions">
        <a class="circle-btn" href="#/feed" aria-label="Neuigkeiten">${icon('bell', { size: 22 })}<span class="dot"></span></a>
        <a class="avatar" href="#/profil" aria-label="Profil">${esc(user.initials)}</a>
      </div>
    </div>

    <div class="desk-head">
      <div class="greeting">
        <span class="sub">${esc(mosque.name)}<span class="only-desktop"> · ${esc(longDate(now))}</span></span>
        <h1>Assalamu alaikum, ${esc(user.firstName)}</h1>
      </div>
      <div class="search only-desktop">
        ${icon('search', { size: 20 })}
        <input type="search" placeholder="Suchen" aria-label="Suchen" data-search>
        <div class="search-results" data-results hidden></div>
      </div>
    </div>

    <div class="dash">
      <a class="glass-card np-card np" href="#/gebet" data-np>${nextPrayerCard(times)}</a>

      <div class="card only-desktop">
        <div class="card-head"><h2>Heute</h2></div>
        ${times.filter((p) => p.iqama !== null).map((p) => `
          <div class="today-row${p.key === next.prayer.key ? ' current' : ''}">
            <span>${esc(p.name)}</span><span><span class="t">${esc(p.adhan)}</span> <span class="q">· ${esc(iqamaText(p))}</span></span>
          </div>`).join('')}
      </div>

      <div class="card only-desktop">
        <div class="card-head"><h2>Bedarf</h2><a href="#/bedarf">Alle</a></div>
        ${needs.slice(0, 3).map((n) => `
          <a class="need-row" href="#/bedarf?id=${esc(n.id)}">
            <span class="top"><span>${esc(n.short)}</span><b>${percent(n)}%</b></span>
            <span class="gbar"><span style="width:${percent(n)}%"></span></span>
          </a>`).join('')}
        <a class="btn-green" href="#/bedarf" style="margin-top:12px">Unterstützen</a>
      </div>
    </div>

    <div class="tiles only-mobile">
      ${tiles.map((t) => `<a class="tile" href="#/${t.route}">${icon(t.icon, { size: 24 })}<span>${t.label}</span></a>`).join('')}
    </div>

    <div class="card">
      <div class="card-head"><h2>Neu im Feed</h2><a href="#/feed">Alle</a></div>
      <div class="list feed-row">${feed.map(feedItem).join('')}</div>
    </div>`;

  // Suche (Computer): Feed, Bedarf und Bereiche durchsuchen
  const search = root.querySelector('[data-search]');
  const results = root.querySelector('[data-results]');
  const index = [
    ...feed.map((f) => ({ title: f.title, meta: f.type, href: '#/feed', icon: f.icon })),
    ...needs.map((n) => ({ title: n.title, meta: 'Bedarf', href: `#/bedarf?id=${n.id}`, icon: n.icon })),
    { title: 'Gebetszeiten', meta: 'Bereich', href: '#/gebet', icon: 'clock' },
    { title: 'Nachrichten', meta: 'Bereich', href: '#/nachrichten', icon: 'message' },
    { title: 'Schule', meta: 'Bereich', href: '#/schule', icon: 'school' },
    { title: 'Profil', meta: 'Bereich', href: '#/profil', icon: 'user' },
  ];
  search.addEventListener('input', () => {
    const q = search.value.trim().toLowerCase();
    if (!q) { results.hidden = true; return; }
    const hits = index.filter((i) => i.title.toLowerCase().includes(q)).slice(0, 6);
    results.innerHTML = hits.length
      ? `<div class="list">${hits.map((h) => `
          <a class="list-item" href="${h.href}"><span class="list-icon">${icon(h.icon, { size: 22 })}</span>
          <span class="list-text"><strong>${esc(h.title)}</strong><span>${esc(h.meta)}</span></span></a>`).join('')}</div>`
      : '<div class="empty">Nichts gefunden.</div>';
    results.hidden = false;
  });
  search.addEventListener('keydown', (e) => { if (e.key === 'Escape') { search.value = ''; results.hidden = true; } });
  search.addEventListener('blur', () => setTimeout(() => { results.hidden = true; }, 150));

  // Countdown laufend aktualisieren
  const np = root.querySelector('[data-np]');
  const timer = setInterval(() => { np.innerHTML = nextPrayerCard(times); }, 20 * 1000);
  return () => clearInterval(timer);
}

/* ---------- Gebetszeiten ---------- */

async function renderPrayer(root, ctx) {
  let day = startOfDay(new Date());
  const times = await getPrayerTimes(day);
  let timer;

  root.innerHTML = `
    ${pageTop('Gebetszeiten', `<label class="circle-btn" aria-label="Datum wählen">${icon('calendar', { size: 22 })}<input type="date" data-date style="position:absolute;inset:0;opacity:0;width:100%;cursor:pointer"></label>`)}
    <div class="day-switch">
      <button type="button" data-prev aria-label="Vorheriger Tag">${icon('back', { size: 20, width: 2 })}</button>
      <span data-day></span>
      <button type="button" data-next aria-label="Nächster Tag">${icon('next', { size: 20, width: 2 })}</button>
    </div>
    <div data-countdown></div>
    <div class="card times" data-table></div>`;

  const dateInput = root.querySelector('[data-date]');
  const toISO = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

  function drawCountdown() {
    const box = root.querySelector('[data-countdown]');
    const now = new Date();
    if (!isSameDay(day, now)) { box.innerHTML = ''; return; }
    const next = nextPrayer(times, now);
    const inIqama = next.phase === 'iqama';
    const tomorrow = !isSameDay(next.adhan, now);
    const r = 46;
    const c = 2 * Math.PI * r;
    const done = progress(next, now);
    const iqamaTime = next.iqama.toTimeString().slice(0, 5);
    box.innerHTML = `
      <div class="countdown">
        <div class="ring">
          <svg width="104" height="104" viewBox="0 0 104 104" aria-hidden="true">
            <circle cx="52" cy="52" r="${r}" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="7"></circle>
            <circle cx="52" cy="52" r="${r}" fill="none" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round"
              stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - done)).toFixed(1)}"></circle>
          </svg>
          <div class="ring-text"><b>${clockText(next.target, now)}</b><span>Std : Min</span></div>
        </div>
        <div class="countdown-text">
          <span class="k">${inIqama ? 'Bis zur Iqama' : tomorrow ? 'Bis zum Adhan (morgen)' : 'Bis zum Adhan'}</span>
          <span class="big">${esc(next.prayer.name)} ${inIqama ? iqamaTime : esc(next.prayer.adhan)}</span>
          <span class="s">${inIqama ? `Adhan war um ${esc(next.prayer.adhan)}` : `Danach Countdown bis Iqama (+${next.prayer.iqama} Min)`}</span>
        </div>
      </div>`;
  }

  function drawTable() {
    const now = new Date();
    const bells = getBells();
    const current = isSameDay(day, now) ? nextPrayer(times, now) : null;
    const showCurrent = current && isSameDay(current.adhan, day);
    root.querySelector('[data-day]').textContent = dayLabel(day, now);
    dateInput.value = toISO(day);
    root.querySelector('[data-table]').innerHTML = `
      <div class="times-row head"><span>GEBET</span><span>ADHAN</span><span>IQAMA</span><span></span></div>
      ${times.map((p) => `
        <div class="times-row${showCurrent && current.prayer.key === p.key ? ' current' : ''}">
          <span class="name">${esc(p.name)}</span>
          <span class="adhan">${esc(p.adhan)}</span>
          <span class="iq">${esc(iqamaText(p))}</span>
          <button type="button" class="bell${bells[p.key] ? ' on' : ''}" data-bell="${p.key}"
            aria-pressed="${bells[p.key] ? 'true' : 'false'}" aria-label="Erinnerung für ${esc(p.name)}">${icon('bell', { size: 20 })}</button>
        </div>`).join('')}`;
  }

  function draw() { drawTable(); drawCountdown(); }

  root.querySelector('[data-prev]').addEventListener('click', () => { day = addDays(day, -1); draw(); });
  root.querySelector('[data-next]').addEventListener('click', () => { day = addDays(day, 1); draw(); });
  dateInput.addEventListener('change', () => {
    if (!dateInput.value) return;
    const [y, m, d] = dateInput.value.split('-').map(Number);
    day = new Date(y, m - 1, d);
    draw();
  });
  dateInput.closest('label').addEventListener('click', (e) => {
    if (e.target === dateInput && dateInput.showPicker) {
      e.preventDefault();
      try { dateInput.showPicker(); } catch { /* Browser ohne showPicker: normales Feld */ }
    }
  });
  root.querySelector('[data-table]').addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-bell]');
    if (!btn) return;
    const key = btn.dataset.bell;
    const on = !getBells()[key];
    setBell(key, on);
    const name = times.find((p) => p.key === key).name;
    if (on && 'Notification' in window && Notification.permission === 'default') {
      try { await Notification.requestPermission(); } catch { /* ignorieren */ }
    }
    ctx.toast(on ? `Erinnerung für ${name} an` : `Erinnerung für ${name} aus`);
    drawTable();
  });

  draw();
  timer = setInterval(draw, 20 * 1000);
  return () => clearInterval(timer);
}

/* ---------- Bedarf ---------- */

function catRing(n) {
  const r = 29;
  const c = 2 * Math.PI * r;
  return `<svg class="ringsvg" width="62" height="62" viewBox="0 0 62 62" aria-hidden="true">
    <circle cx="31" cy="31" r="${r}" fill="none" stroke="rgba(47,90,43,0.15)" stroke-width="3.5"></circle>
    <circle cx="31" cy="31" r="${r}" fill="none" stroke="#2F5A2B" stroke-width="3.5" stroke-linecap="round"
      stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - percent(n) / 100)).toFixed(1)}"></circle></svg>`;
}

function openSupportSheet(ctx, need, mosque) {
  const isMoney = need.kind === 'money';
  const body = isMoney
    ? `
      <div class="pay-row"><span>Empfänger</span><strong>${esc(mosque.accountHolder)}</strong></div>
      <div class="pay-row"><span>IBAN</span><strong>${esc(mosque.iban)}</strong>
        <button type="button" class="copy" data-copy="${esc(mosque.iban.replace(/\s/g, ''))}">IBAN kopieren</button></div>
      <div class="pay-row"><span>Verwendungszweck</span><strong>Spende ${esc(need.title)}</strong></div>
      ${mosque.paypalUrl
        ? `<a class="btn-green" href="${esc(mosque.paypalUrl)}" target="_blank" rel="noopener">Mit PayPal spenden</a>`
        : '<p class="note">PayPal hat die Moschee noch nicht eingerichtet.</p>'}`
    : `
      <p class="note" style="font-size:16px">Bitte bring die Spende direkt in die Moschee und gib sie beim Vorstand ab.</p>
      <div class="pay-row"><span>Noch benötigt</span><strong>${need.goal - need.current} ${esc(need.unit)}</strong></div>`;
  ctx.openSheet(`
    <div><h2 style="font-size:24px;font-weight:800">Unterstützen</h2><p class="note" style="font-size:16px;margin-top:4px">${esc(need.title)} · ${esc(amountText(need))}</p></div>
    ${body}
    ${DEMO_MODE ? '<p class="note">Demo-Daten – hier stehen später die echten Angaben deiner Moschee.</p>' : ''}
    <button type="button" class="btn-text" data-close>Schließen</button>
  `, (sheet) => {
    sheet.querySelector('[data-copy]')?.addEventListener('click', async (e) => {
      try {
        await navigator.clipboard.writeText(e.currentTarget.dataset.copy);
        ctx.toast('IBAN kopiert');
      } catch {
        ctx.toast('Kopieren nicht möglich – bitte abschreiben.');
      }
    });
  });
}

async function renderNeeds(root, ctx) {
  const [needs, latest, mosque] = await Promise.all([getNeeds(), getLatestDonation(), getMosque()]);
  let selected = needs.some((n) => n.id === ctx.params.get('id')) ? ctx.params.get('id') : needs[0].id;
  const latestNeed = needs.find((n) => n.id === latest.needId);

  root.innerHTML = `
    ${pageTop('Bedarf')}
    <div class="cats" role="tablist" aria-label="Kategorien">
      ${needs.map((n) => `
        <button type="button" class="cat" role="tab" data-cat="${esc(n.id)}">
          <span class="cat-circle">${catRing(n)}<span class="inner">${icon(n.icon, { size: 22 })}</span></span>
          ${esc(n.category)}
        </button>`).join('')}
    </div>
    ${latestNeed ? `<div class="ticker"><span><b>${esc(latest.who)}</b> hat vor ${latest.minutesAgo} Min für ${esc(latestNeed.category)} gespendet</span></div>` : ''}
    <div data-needs style="display:flex;flex-direction:column;gap:14px"></div>`;

  function draw() {
    root.querySelectorAll('[data-cat]').forEach((b) => {
      const on = b.dataset.cat === selected;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', String(on));
    });
    root.querySelector('[data-needs]').innerHTML = needs.map((n) => `
      <div class="card need${n.id === selected ? ' active' : ''}" data-need="${esc(n.id)}" id="need-${esc(n.id)}">
        <span class="kick">${n.kind === 'money' ? 'Geldspende' : 'Sachspende'} · noch ${n.daysLeft} Tage</span>
        <h2>${esc(n.title)}</h2>
        <span class="gbar"><span style="width:${percent(n)}%"></span></span>
        <span class="amounts"><span>${esc(amountText(n))}</span><b>${percent(n)}%</b></span>
        <span class="supporters"><span class="faces">${n.initials.map((i) => `<span>${esc(i)}</span>`).join('')}</span>
          +${Math.max(0, n.supporters - n.initials.length)} haben unterstützt</span>
        ${n.id === selected ? `<button type="button" class="btn-green" data-support="${esc(n.id)}" style="min-height:52px;font-size:16px;padding:10px 14px">
          ${n.kind === 'money' ? 'Unterstützen · PayPal oder Überweisung' : 'Unterstützen · Sachspende'}</button>` : ''}
      </div>`).join('');
  }

  function select(id, scroll) {
    selected = id;
    draw();
    if (scroll) root.querySelector(`#need-${CSS.escape(id)}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  root.querySelector('.cats').addEventListener('click', (e) => {
    const b = e.target.closest('[data-cat]');
    if (b) select(b.dataset.cat, true);
  });
  root.querySelector('[data-needs]').addEventListener('click', (e) => {
    const support = e.target.closest('[data-support]');
    if (support) { openSupportSheet(ctx, needs.find((n) => n.id === support.dataset.support), mosque); return; }
    const card = e.target.closest('[data-need]');
    if (card && card.dataset.need !== selected) select(card.dataset.need, false);
  });

  draw();
  if (ctx.params.get('id')) setTimeout(() => select(selected, true), 50);
}

/* ---------- Feed ---------- */

async function renderFeed(root) {
  const feed = await getFeed();
  root.innerHTML = `
    ${pageTop('Feed')}
    <div class="card"><div class="list">${feed.map(feedItem).join('')}</div></div>`;
}

/* ---------- Profil ---------- */

function renderProfile(root, ctx) {
  const { user, email } = ctx.session;
  root.innerHTML = `
    ${pageTop('Profil')}
    <div class="card profile-head">
      <span class="avatar">${esc(user.initials)}</span>
      <div><strong>${esc(user.name)}</strong><span>${esc(user.role)} · ${esc(email)}</span></div>
    </div>
    <div class="card menu-list">
      ${canOfferInstall() ? `<button type="button" data-install>${icon('download', { size: 22 })}App installieren</button>` : ''}
      <button type="button" data-logout>${icon('logout', { size: 22 })}Abmelden</button>
    </div>
    ${DEMO_MODE ? '<p class="note" style="text-align:center">Demo-Modus – Daten sind Beispiele.</p>' : ''}`;
  root.querySelector('[data-install]')?.addEventListener('click', () => openInstallSheet(ctx));
  root.querySelector('[data-logout]').addEventListener('click', () => {
    logout();
    ctx.navigate('login');
  });
}

/* ---------- Bereiche ohne Design ---------- */

function soon(title) {
  return (root) => {
    root.innerHTML = `
      ${pageTop(title)}
      <div class="card soon">
        <h2>Kommt bald</h2>
        <p>Der Bereich „${esc(title)}“ ist in Arbeit.</p>
      </div>`;
  };
}

// bg: Hintergrund auf dem Handy, nav: welcher Menüpunkt hervorgehoben wird
export const views = {
  login: { render: renderLogin, bg: 'dark', title: 'Anmelden' },
  start: { render: renderStart, bg: 'dark', title: '' },
  gebet: { render: renderPrayer, bg: 'light', title: 'Gebetszeiten' },
  bedarf: { render: renderNeeds, bg: 'light', title: 'Bedarf' },
  feed: { render: renderFeed, bg: 'light', title: 'Feed' },
  profil: { render: renderProfile, bg: 'light', title: 'Profil' },
  moschee: { render: soon('Moschee'), bg: 'light', title: 'Moschee' },
  nachrichten: { render: soon('Nachrichten'), bg: 'light', title: 'Nachrichten' },
  schule: { render: soon('Schule'), bg: 'light', title: 'Schule' },
  beitraege: { render: soon('Beiträge'), bg: 'light', title: 'Beiträge' },
};
