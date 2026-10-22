import { Terminal } from '/vendor/xterm.mjs';
import { FitAddon } from '/vendor/addon-fit.mjs';
import { WebLinksAddon } from '/vendor/addon-web-links.mjs';
import { marked } from '/vendor/marked.esm.js';
import DOMPurify from '/vendor/purify.es.mjs';

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};

const ICONS = {
  panel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>',
  pencil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/></svg>',
};
const icon = (name) => {
  const span = el('span');
  span.innerHTML = ICONS[name];
  return span.firstChild;
};

const STATUS_LABEL = { busy: 'arbeitet', waiting: 'wartet auf dich', idle: 'bereit', starting: 'startet', exited: 'beendet' };
const HISTORY_WINDOW = 400;
const TERM_THEME = {
  background: '#1d1c1a', foreground: '#e8e6e1', cursor: '#d97757', cursorAccent: '#1d1c1a',
  selectionBackground: 'rgba(217, 119, 87, 0.35)',
};
const DAY = 864e5;
const MONTH = new Intl.DateTimeFormat('de-DE', { month: 'long', year: 'numeric' });
const SHORT_DATE = new Intl.DateTimeFormat('de-DE', { day: 'numeric', month: 'short' });
const CLOCK = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' });

const state = {
  sessions: [],
  byId: new Map(),
  terminals: new Map(),   // terminal id -> status row
  bySession: new Map(),   // session id -> running terminal row
  external: new Map(),    // session id -> CLI running outside claude-desk
  lastStatus: new Map(),  // terminal id -> previous status, to notice "finished"
  attention: new Set(),   // terminal ids that finished or need input while unseen
  tabs: [],
  active: null,
  home: '',
  renaming: false,
  online: true,
};

const store = {
  get(key, fallback) {
    try {
      const value = localStorage.getItem('desk.' + key);
      return value == null ? fallback : JSON.parse(value);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem('desk.' + key, JSON.stringify(value)); } catch { /* storage unavailable */ }
  },
};

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});
// Transcripts can quote anything (web pages, tool output), so no styles or form controls either.
const PURIFY = { FORBID_TAGS: ['style', 'form', 'input', 'button', 'textarea', 'select'], FORBID_ATTR: ['style'] };
const markdown = (text) => DOMPurify.sanitize(marked.parse(text), PURIFY);

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const err = new Error(data?.error || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

let toastTimer;
function toast(message) {
  const box = $('#toast');
  box.textContent = message;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, 5000);
}

// ---- data ---------------------------------------------------------------------------------

function applyStatus(data) {
  state.terminals = new Map(data.terminals.map((t) => [t.id, t]));
  state.bySession = new Map(data.terminals.filter((t) => t.status !== 'exited').map((t) => [t.session_id, t]));
  state.external = new Map(data.external.map((e) => [e.session_id, e]));
  let finished = false;
  for (const t of data.terminals) {
    const prev = state.lastStatus.get(t.id);
    if (prev && prev !== t.status) {
      const done = t.status === 'waiting' || t.status === 'exited' || (prev === 'busy' && t.status === 'idle');
      if (done && (state.active !== t.id || document.hidden)) state.attention.add(t.id);
      if (done) finished = true;
    }
    state.lastStatus.set(t.id, t.status);
  }
  return finished;
}

async function refreshStatus() {
  let finished = false;
  try {
    finished = applyStatus(await api('GET', '/api/status'));
    setOnline(true);
  } catch {
    setOnline(false);
    return;
  }
  for (const tab of state.tabs) {
    if (tab.term && !state.terminals.has(tab.id)) {
      disposeTerminal(tab);
      tab.view = 'history';
      loadHistory(tab);
    }
  }
  paint();
  if (finished) {
    refreshSessions();
    const tab = activeTab();
    if (tab && tab.view === 'history' && tab.loaded) loadHistory(tab, { quiet: true });
  }
}

async function refreshSessions() {
  let data;
  try {
    data = await api('GET', '/api/sessions');
    setOnline(true);
  } catch {
    setOnline(false);
    return;
  }
  state.home = data.home;
  state.sessions = data.sessions;
  state.byId = new Map(data.sessions.map((s) => [s.id, s]));
  applyStatus(data);
  if (!state.renaming) renderSidebar();
  paint();
}

function setOnline(online) {
  state.online = online;
  $('#banner').hidden = online;
}

const tabSession = (tab) => state.terminals.get(tab.id)?.session_id || tab.id;
const titleOf = (sid) => state.byId.get(sid)?.title || 'Neuer Chat';
const activeTab = () => state.tabs.find((t) => t.id === state.active) || null;
const findTab = (id) => state.tabs.find((t) => t.id === id) || null;

function statusFor(sid) {
  const term = state.bySession.get(sid);
  if (term) return { cls: term.status, label: STATUS_LABEL[term.status], attention: state.attention.has(term.id) };
  const ext = state.external.get(sid);
  if (ext) {
    return { cls: `external ${ext.status === 'busy' ? 'busy' : ''}`, label: `läuft in anderem Terminal (${STATUS_LABEL[ext.status]})`, attention: false };
  }
  return { cls: '', label: '', attention: false };
}

// ---- sidebar ------------------------------------------------------------------------------

function groupLabel(mtime) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const t = mtime * 1000;
  if (t >= today) return 'Heute';
  if (t >= today - DAY) return 'Gestern';
  if (t >= today - 6 * DAY) return 'Letzte 7 Tage';
  if (t >= today - 29 * DAY) return 'Letzte 30 Tage';
  return MONTH.format(new Date(t));
}

function timeLabel(mtime) {
  const d = new Date(mtime * 1000);
  return d.toDateString() === new Date().toDateString() ? CLOCK.format(d) : SHORT_DATE.format(d);
}

function renderSidebar() {
  const list = $('#session-list');
  const query = $('#search').value.trim().toLowerCase();
  const matches = state.sessions.filter((s) => !query
    || [s.title, s.cwd_label, s.first_prompt, s.last_prompt].some((v) => v && v.toLowerCase().includes(query)));
  const nodes = [];
  let group = null;
  for (const s of matches) {
    const label = groupLabel(s.mtime);
    if (label !== group) {
      nodes.push(el('div', 'group-label', label));
      group = label;
    }
    nodes.push(sessionItem(s));
  }
  if (!matches.length) nodes.push(el('div', 'list-empty', query ? 'Keine Treffer' : 'Noch keine Chats'));
  list.replaceChildren(...nodes);
}

function sessionItem(s) {
  const item = el('div', 'item');
  item.dataset.id = s.id;
  item.title = s.first_prompt ? s.first_prompt.slice(0, 300) : '';
  const text = el('div', 'item-text');
  const title = el('div', 'item-title', s.title);
  const meta = el('div', 'item-meta', [s.cwd_label, timeLabel(s.mtime)].filter(Boolean).join(' · '));
  text.append(title, meta);
  const rename = el('button', 'icon-btn');
  rename.title = 'Umbenennen';
  rename.append(icon('pencil'));
  rename.onclick = (ev) => { ev.stopPropagation(); startRename(title, s.id); };
  title.ondblclick = (ev) => { ev.stopPropagation(); startRename(title, s.id); };
  item.onclick = () => openSession(s.id);
  item.append(el('span', 'dot'), text, rename);
  return item;
}

function paintSidebar() {
  const current = activeTab() ? tabSession(activeTab()) : null;
  for (const item of document.querySelectorAll('#session-list .item')) {
    const sid = item.dataset.id;
    const st = statusFor(sid);
    const dot = item.querySelector('.dot');
    dot.className = `dot ${st.cls} ${st.attention ? 'attention' : ''}`;
    dot.title = st.label;
    item.classList.toggle('active', sid === current);
    item.classList.toggle('attention', st.attention);
  }
}

function startRename(target, sid) {
  if (target.querySelector('input')) return;
  const old = titleOf(sid);
  const original = target.textContent;
  const input = el('input', 'rename-input');
  input.value = old;
  target.replaceChildren(input);
  input.focus();
  input.select();
  state.renaming = true;
  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    state.renaming = false;
    const value = input.value.trim();
    target.textContent = save && value ? value : original;
    if (save && value && value !== old) {
      try {
        await api('PUT', `/api/sessions/${sid}/title`, { title: value });
        const s = state.byId.get(sid);
        if (s) s.title = value;
      } catch (e) {
        target.textContent = original;
        toast(e.message);
      }
    }
    renderSidebar();
    paint();
  };
  input.onkeydown = (ev) => {
    ev.stopPropagation();
    if (ev.key === 'Enter') finish(true);
    else if (ev.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(true);
  input.onclick = (ev) => ev.stopPropagation();
  input.ondblclick = (ev) => ev.stopPropagation();
}

function setCollapsed(collapsed) {
  $('#app').classList.toggle('collapsed', collapsed);
  store.set('collapsed', collapsed);
  setTimeout(() => fitTab(activeTab()), 200);
}

// ---- tabs ---------------------------------------------------------------------------------

function saveTabs() {
  store.set('tabs', state.tabs.map((t) => ({ id: t.id, view: t.view })));
  store.set('active', state.active);
}

function openSession(sid) {
  const term = state.bySession.get(sid);
  const id = term ? term.id : sid;
  if (!findTab(id)) addTab(id, term ? 'terminal' : 'history');
  activate(id);
}

function addTab(id, view) {
  const tab = { id, view, term: null, fit: null, ws: null, loaded: false, showAll: false, items: [] };
  buildView(tab);
  state.tabs.push(tab);
  saveTabs();
  return tab;
}

function buildView(tab) {
  const root = el('section', 'view');
  const head = el('header', 'view-head');
  const titleBox = el('div', 'view-titlebox');
  const title = el('h1', 'view-title');
  title.title = 'Klicken zum Umbenennen';
  title.onclick = () => startRename(title, tabSession(tab));
  const meta = el('div', 'view-meta');
  titleBox.append(title, meta);

  const seg = el('div', 'seg');
  const histBtn = el('button', '', 'Verlauf');
  const termBtn = el('button', '', 'Terminal');
  histBtn.onclick = () => setView(tab, 'history');
  termBtn.onclick = () => setView(tab, 'terminal');
  seg.append(histBtn, termBtn);

  const actions = el('div', 'view-actions');
  const refresh = el('button', 'icon-btn');
  refresh.title = 'Verlauf neu laden';
  refresh.append(icon('refresh'));
  refresh.onclick = () => loadHistory(tab);
  const resume = el('button', 'btn primary', 'Fortsetzen');
  resume.onclick = () => resumeTab(tab);
  const stop = el('button', 'btn danger', 'Beenden');
  stop.onclick = () => stopTab(tab);
  actions.append(refresh, resume, stop);
  head.append(titleBox, seg, actions);

  const body = el('div', 'view-body');
  const hist = el('div', 'history');
  const histInner = el('div', 'history-inner');
  hist.append(histInner);
  const termWrap = el('div', 'term-wrap');
  const termHost = el('div', 'term-host');
  const overlay = el('div', 'term-overlay');
  overlay.hidden = true;
  termWrap.append(termHost, overlay);
  body.append(hist, termWrap);
  root.append(head, body);
  $('#views').append(root);
  Object.assign(tab, { root, title, meta, histBtn, termBtn, refresh, resume, stop, hist, histInner, termWrap, termHost, overlay });
}

function activate(id) {
  const tab = findTab(id);
  if (!tab) return;
  state.active = id;
  if (!document.hidden) state.attention.delete(id);
  for (const t of state.tabs) t.root.classList.toggle('active', t === tab);
  saveTabs();
  paint();
  showView(tab);
}

function showView(tab) {
  const live = state.terminals.has(tab.id);
  if (tab.view === 'terminal' && live) {
    ensureTerminal(tab);
    requestAnimationFrame(() => {
      fitTab(tab);
      tab.term?.focus();
    });
  } else if (!tab.loaded) {
    loadHistory(tab);
  }
}

function setView(tab, view) {
  tab.view = view;
  saveTabs();
  paint();
  if (view === 'history' && tab.loaded) loadHistory(tab, { quiet: true });
  showView(tab);
}

function closeTab(tab) {
  const index = state.tabs.indexOf(tab);
  if (index < 0) return;
  disposeTerminal(tab);
  tab.root.remove();
  state.tabs.splice(index, 1);
  state.attention.delete(tab.id);
  const row = state.terminals.get(tab.id);
  if (row && row.status === 'exited') api('DELETE', `/api/terminals/${tab.id}`).catch(() => {});
  if (state.active === tab.id) {
    const next = state.tabs[Math.min(index, state.tabs.length - 1)];
    state.active = null;
    if (next) activate(next.id);
  }
  saveTabs();
  paint();
}

function cycleTab(step) {
  if (!state.tabs.length) return;
  const index = state.tabs.findIndex((t) => t.id === state.active);
  const next = state.tabs[(index + step + state.tabs.length) % state.tabs.length];
  activate(next.id);
}

function renderTabs() {
  if (state.renaming && document.activeElement?.closest('#tabs')) return;
  const nodes = state.tabs.map((tab) => {
    const sid = tabSession(tab);
    const st = statusFor(sid);
    const row = state.terminals.get(tab.id);
    const node = el('div', 'tab');
    node.classList.toggle('active', tab.id === state.active);
    node.classList.toggle('attention', state.attention.has(tab.id));
    node.setAttribute('role', 'tab');
    node.title = titleOf(sid) + (st.label ? ` – ${st.label}` : '');
    const dot = el('span', `dot ${row ? row.status : st.cls} ${state.attention.has(tab.id) ? 'attention' : ''}`);
    const label = el('span', 'tab-label', titleOf(sid));
    label.ondblclick = (ev) => { ev.stopPropagation(); startRename(label, sid); };
    const close = el('button', 'icon-btn');
    close.title = row && row.status !== 'exited' ? 'Tab schließen (Session läuft im Hintergrund weiter)' : 'Tab schließen';
    close.append(icon('x'));
    close.onclick = (ev) => { ev.stopPropagation(); closeTab(tab); };
    node.onclick = () => activate(tab.id);
    node.onauxclick = (ev) => { if (ev.button === 1) closeTab(tab); };
    node.append(dot, label, close);
    return node;
  });
  $('#tabs').replaceChildren(...nodes);
}

function paintView(tab) {
  const sid = tabSession(tab);
  const row = state.terminals.get(tab.id);
  const session = state.byId.get(sid);
  const ext = state.external.get(sid);
  const live = row && row.status !== 'exited';
  const showTerm = tab.view === 'terminal' && !!row;
  if (!tab.title.querySelector('input')) tab.title.textContent = titleOf(sid);
  const parts = [session?.cwd_label || row?.cwd || ''];
  if (row) parts.push(STATUS_LABEL[row.status]);
  else if (ext) parts.push('läuft in einem anderen Terminal');
  tab.meta.textContent = parts.filter(Boolean).join(' · ');
  tab.histBtn.classList.toggle('on', !showTerm);
  tab.termBtn.classList.toggle('on', showTerm);
  tab.termBtn.disabled = !row;
  tab.termBtn.title = row ? '' : 'Erst „Fortsetzen“, dann läuft die Session hier im Terminal';
  tab.resume.hidden = live;
  tab.stop.hidden = !live;
  tab.refresh.hidden = showTerm;
  tab.hist.hidden = showTerm;
  tab.termWrap.hidden = !showTerm;
}

function paint() {
  renderTabs();
  paintSidebar();
  for (const tab of state.tabs) paintView(tab);
  $('#empty').hidden = state.tabs.length > 0;
  const waiting = state.attention.size;
  document.title = waiting ? `(${waiting}) Claude Desk` : 'Claude Desk';
}

// ---- history ------------------------------------------------------------------------------

async function loadHistory(tab, { quiet = false } = {}) {
  const sid = tabSession(tab);
  const box = tab.hist;
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  if (!quiet) tab.histInner.replaceChildren(el('div', 'loading', 'Lade Verlauf …'));
  let data;
  try {
    data = await api('GET', `/api/sessions/${sid}/messages`);
  } catch (e) {
    tab.histInner.replaceChildren(el('div', 'empty-note', e.message));
    return;
  }
  tab.items = data.items;
  tab.truncated = data.truncated;
  tab.loaded = true;
  renderHistory(tab);
  if (!quiet || atBottom) box.scrollTop = box.scrollHeight;
}

function renderHistory(tab) {
  const items = tab.items;
  const start = tab.showAll ? 0 : Math.max(0, items.length - HISTORY_WINDOW);
  const nodes = [];
  if (start > 0) {
    const more = el('button', 'btn more', `Frühere Einträge anzeigen (${start})`);
    more.onclick = () => {
      const fromBottom = tab.hist.scrollHeight - tab.hist.scrollTop;
      tab.showAll = true;
      renderHistory(tab);
      tab.hist.scrollTop = tab.hist.scrollHeight - fromBottom;
    };
    nodes.push(more);
  } else if (tab.truncated) {
    nodes.push(el('div', 'note', 'Sehr lange Unterhaltung – nur die letzten Einträge werden angezeigt.'));
  }
  if (!items.length) {
    const live = state.terminals.has(tab.id);
    nodes.push(el('div', 'empty-note', live ? 'Noch keine Nachrichten – schreib im Terminal los.' : 'Keine Nachrichten.'));
  }
  let steps = null;
  for (const item of items.slice(start)) {
    if (item.k === 'tool' || item.k === 'thinking') {
      if (!steps) {
        steps = stepsGroup();
        nodes.push(steps.root);
      }
      steps.add(item);
      continue;
    }
    steps = null;
    nodes.push(renderItem(item));
  }
  tab.histInner.replaceChildren(...nodes);
}

function renderItem(item) {
  switch (item.k) {
    case 'user': {
      const node = el('div', 'msg user');
      node.append(el('div', 'bubble', item.text));
      return node;
    }
    case 'assistant': {
      const node = el('div', 'msg assistant md');
      node.innerHTML = markdown(item.text);
      return node;
    }
    case 'command': {
      const node = el('div', 'msg command');
      node.append(el('code', '', item.text));
      return node;
    }
    case 'output':
      return el('pre', 'cmd-output', item.text);
    case 'divider': {
      return el('div', 'divider', item.text);
    }
    default:
      return el('div', 'note', item.text || '');
  }
}

function stepsGroup() {
  const root = el('details', 'steps');
  const summary = el('summary');
  const body = el('div', 'steps-body');
  root.append(summary, body);
  const names = [];
  let tools = 0;
  let errors = 0;
  let thoughts = 0;
  return {
    root,
    add(item) {
      body.append(renderStep(item));
      if (item.k === 'tool') {
        tools += 1;
        if (!names.includes(item.name)) names.push(item.name);
        if (item.error) errors += 1;
      } else {
        thoughts += 1;
      }
      const label = tools
        ? `${tools} ${tools === 1 ? 'Schritt' : 'Schritte'} · ${names.slice(0, 4).join(', ')}${names.length > 4 ? ' …' : ''}`
        : 'Gedankengang';
      summary.replaceChildren(el('span', '', label));
      if (errors) summary.append(el('span', 'badge', `${errors} Fehler`));
    },
  };
}

function renderStep(item) {
  if (item.k === 'thinking') {
    const node = el('div', 'thinking md');
    node.innerHTML = markdown(item.text);
    return node;
  }
  const node = el('details', 'tool');
  const summary = el('summary');
  summary.append(el('span', 'tool-name', item.name), el('span', 'tool-sum', item.summary));
  if (item.error) summary.append(el('span', 'badge', 'Fehler'));
  node.append(summary);
  node.addEventListener('toggle', () => {
    if (!node.open || node.dataset.filled) return;
    node.dataset.filled = '1';
    if (item.input && item.input !== item.summary) node.append(toolInput(item));
    if (item.result) node.append(el('pre', '', item.result));
  });
  return node;
}

function toolInput(item) {
  if (item.name !== 'Edit') return el('pre', '', item.input);
  const pre = el('pre', 'diff');
  for (const line of item.input.split('\n')) {
    const cls = line.startsWith('- ') ? 'diff-del' : line.startsWith('+ ') ? 'diff-add' : '';
    pre.append(el('span', cls, line + '\n'));
  }
  return pre;
}

// ---- terminals ----------------------------------------------------------------------------

function ensureTerminal(tab) {
  if (tab.term) {
    if (!tab.ws) connect(tab);
    return;
  }
  const term = new Terminal({
    fontFamily: '"Cascadia Mono", "Cascadia Code", Consolas, "DejaVu Sans Mono", monospace',
    fontSize: 14,
    lineHeight: 1.15,
    cursorBlink: true,
    scrollback: 10000,
    theme: TERM_THEME,
    allowProposedApi: true,
  });
  const fit = new FitAddon();
  term.loadAddon(fit);
  term.loadAddon(new WebLinksAddon((ev, uri) => window.open(uri, '_blank', 'noopener')));
  term.open(tab.termHost);
  term.attachCustomKeyEventHandler((ev) => terminalKey(tab, ev));
  term.onData((data) => send(tab, { t: 'i', d: data }));
  term.onResize(({ cols, rows }) => send(tab, { t: 'r', c: cols, r: rows }));
  tab.term = term;
  tab.fit = fit;
  connect(tab);
}

function connect(tab) {
  if (tab.ws && tab.ws.readyState <= WebSocket.OPEN) return;
  const ws = new WebSocket(`ws://${location.host}/ws/terminals/${tab.id}`);
  ws.binaryType = 'arraybuffer';
  tab.ws = ws;
  tab.exited = false;
  ws.onopen = () => {
    tab.retries = 0;
    tab.term.reset();
    tab.overlay.hidden = true;
    fitTab(tab);
    send(tab, { t: 'r', c: tab.term.cols, r: tab.term.rows });
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data !== 'string') {
      tab.term.write(new Uint8Array(ev.data));
      return;
    }
    const msg = JSON.parse(ev.data);
    if (msg.t === 'exit') {
      tab.exited = true;
      // 129 = the CLI's answer to our SIGHUP from "Beenden", not an error.
      const code = msg.code === 0 || msg.code === 129 ? '' : ` (Code ${msg.code})`;
      showOverlay(tab, `Session beendet${code}. Der Verlauf ist gespeichert.`);
      refreshStatus();
    }
  };
  ws.onclose = () => {
    if (tab.ws !== ws) return;
    tab.ws = null;
    if (tab.exited || !state.tabs.includes(tab) || !tab.term) return;
    showOverlay(tab, 'Verbindung getrennt – verbinde neu …');
    tab.retries = (tab.retries || 0) + 1;
    setTimeout(() => {
      if (tab.term && state.tabs.includes(tab) && state.terminals.has(tab.id)) connect(tab);
    }, Math.min(5000, 300 * 2 ** tab.retries));
  };
}

function showOverlay(tab, message) {
  const resume = el('button', 'btn primary', 'Fortsetzen');
  resume.onclick = () => resumeTab(tab);
  tab.overlay.replaceChildren(el('span', '', message));
  if (tab.exited) tab.overlay.append(resume);
  tab.overlay.hidden = false;
}

function disposeTerminal(tab) {
  if (tab.ws) {
    const ws = tab.ws;
    tab.ws = null;
    ws.close();
  }
  if (tab.term) {
    tab.term.dispose();
    tab.term = null;
    tab.fit = null;
  }
  tab.overlay.hidden = true;
}

function send(tab, msg) {
  if (tab.ws && tab.ws.readyState === WebSocket.OPEN) tab.ws.send(JSON.stringify(msg));
}

function fitTab(tab) {
  if (!tab || !tab.term || tab.termWrap.hidden || !tab.root.classList.contains('active')) return;
  try { tab.fit.fit(); } catch { /* not laid out yet */ }
}

function terminalKey(tab, ev) {
  const key = ev.key.toLowerCase();
  // The CLI reads ESC+CR (meta-enter) as "new line" rather than "send".
  if (ev.key === 'Enter' && ev.shiftKey && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
    if (ev.type === 'keydown') send(tab, { t: 'i', d: '\x1b\r' });
    return false;
  }
  if (ev.ctrlKey && !ev.altKey && key === 'c' && (ev.shiftKey || tab.term.hasSelection())) {
    if (ev.type === 'keydown' && tab.term.hasSelection()) {
      navigator.clipboard?.writeText(tab.term.getSelection()).catch(() => {});
      tab.term.clearSelection();
    }
    return false;
  }
  // Leave Ctrl+V to the browser so the paste event reaches xterm (bracketed paste included).
  if (ev.ctrlKey && !ev.altKey && key === 'v') return false;
  return true;
}

async function resumeTab(tab, force = false) {
  const sid = tabSession(tab);
  try {
    const started = await api('POST', '/api/terminals', { resume: sid, force });
    disposeTerminal(tab);
    if (started.id !== tab.id) {
      const other = findTab(started.id);
      if (other && other !== tab) closeTab(other);
      if (state.active === tab.id) state.active = started.id;
      tab.id = started.id;
    }
    tab.exited = false;
    tab.view = 'terminal';
    await refreshStatus();
    activate(tab.id);
  } catch (e) {
    if (e.status === 409 && !force) {
      const ok = confirm(`${e.message}\n\nTrotzdem hier fortsetzen? Dann schreiben zwei Prozesse in denselben Verlauf.`);
      if (ok) return resumeTab(tab, true);
      return;
    }
    toast(e.message);
  }
}

async function stopTab(tab) {
  if (!confirm('Session beenden?\n\nDer Verlauf bleibt erhalten und kann jederzeit fortgesetzt werden.')) return;
  try {
    await api('DELETE', `/api/terminals/${tab.id}`);
  } catch (e) {
    toast(e.message);
  }
  setTimeout(refreshStatus, 400);
}

// ---- new chat dialog ----------------------------------------------------------------------

async function openNewDialog() {
  const dialog = $('#new-dialog');
  if (dialog.open) return;
  const cwdInput = $('#new-cwd');
  $('#new-error').textContent = '';
  $('#new-title').value = '';
  cwdInput.value = store.get('lastCwd', state.home || '~');
  dialog.showModal();
  cwdInput.focus();
  cwdInput.select();
  try {
    const { cwds } = await api('GET', '/api/cwds');
    $('#cwd-list').replaceChildren(...cwds.map((cwd) => {
      const option = el('option');
      option.value = cwd;
      return option;
    }));
    $('#cwd-chips').replaceChildren(...cwds.slice(0, 6).map((cwd) => {
      const chip = el('button', 'chip', cwd.startsWith(state.home) ? '~' + cwd.slice(state.home.length) : cwd);
      chip.type = 'button';
      chip.title = cwd;
      chip.onclick = () => { cwdInput.value = cwd; $('#new-title').focus(); };
      return chip;
    }));
  } catch { /* suggestions are optional */ }
}

async function submitNewChat(ev) {
  ev.preventDefault();
  const cwd = $('#new-cwd').value.trim();
  const title = $('#new-title').value.trim();
  try {
    const started = await api('POST', '/api/terminals', { cwd, title });
    store.set('lastCwd', started.cwd);
    $('#new-dialog').close();
    await refreshSessions();
    if (!findTab(started.id)) addTab(started.id, 'terminal');
    activate(started.id);
  } catch (e) {
    $('#new-error').textContent = e.message;
  }
}

// ---- wiring -------------------------------------------------------------------------------

function wire() {
  for (const node of document.querySelectorAll('[data-icon]')) node.append(icon(node.dataset.icon));
  document.addEventListener('click', (ev) => {
    const action = ev.target.closest('[data-action]')?.dataset.action;
    if (action === 'toggle-sidebar') setCollapsed(!$('#app').classList.contains('collapsed'));
    else if (action === 'new-chat') openNewDialog();
    else if (action === 'close-dialog') $('#new-dialog').close();
  });
  $('#new-form').addEventListener('submit', submitNewChat);
  $('#search').addEventListener('input', renderSidebar);

  // Capture phase, so the terminal never sees the app's own shortcuts.
  window.addEventListener('keydown', (ev) => {
    const key = ev.key.toLowerCase();
    if (ev.ctrlKey && ev.shiftKey && key === 'b') setCollapsed(!$('#app').classList.contains('collapsed'));
    else if (ev.ctrlKey && ev.shiftKey && key === 'o') openNewDialog();
    else if (ev.ctrlKey && !ev.shiftKey && (ev.key === 'PageDown' || ev.key === 'PageUp')) cycleTab(ev.key === 'PageDown' ? 1 : -1);
    else if (ev.ctrlKey && ev.shiftKey && key === 'f') { setCollapsed(false); $('#search').focus(); }
    else return;
    ev.preventDefault();
    ev.stopPropagation();
  }, true);

  let pending = 0;
  new ResizeObserver(() => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(() => fitTab(activeTab()));
  }).observe($('#views'));

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) return;
    if (state.active) state.attention.delete(state.active);
    refreshSessions();
  });
  window.addEventListener('focus', () => {
    if (state.active) state.attention.delete(state.active);
    paint();
  });
}

async function start() {
  wire();
  if (store.get('collapsed', false)) $('#app').classList.add('collapsed');
  await refreshSessions();
  for (const saved of store.get('tabs', [])) {
    if (!saved || findTab(saved.id)) continue;
    if (state.byId.has(saved.id) || state.terminals.has(saved.id)) addTab(saved.id, saved.view === 'terminal' ? 'terminal' : 'history');
  }
  const linked = location.hash.slice(1);
  const wanted = store.get('active', null);
  if (state.byId.has(linked) || state.bySession.has(linked)) {
    history.replaceState(null, '', location.pathname);
    openSession(linked);
  } else if (findTab(wanted)) activate(wanted);
  else if (state.tabs.length) activate(state.tabs[0].id);
  paint();
  setInterval(refreshStatus, 2000);
  setInterval(refreshSessions, 20000);
}

start();
