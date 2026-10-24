import { Terminal } from '/vendor/xterm.mjs';
import { FitAddon } from '/vendor/addon-fit.mjs';
import { WebLinksAddon } from '/vendor/addon-web-links.mjs';
import { marked } from '/vendor/marked.esm.js';
import DOMPurify from '/vendor/purify.es.mjs';
import hljs from '/vendor/highlight.mjs';
import { htmlToMarkdown } from '/static/paste.js';
import { LANGUAGES, language, locale, setLanguage, t } from '/static/i18n.js';

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};

const ICONS = {
  panel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></svg>',
  add: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5.5v13M5.5 12h13"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>',
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
  folderPlus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10.5v5M9.5 13h5"/></svg>',
  chevronRight: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
  chevronDown: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
  archive: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8M10 12h4"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/></svg>',
  restore: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 5v5h5"/></svg>',
  pencil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  note: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h14v10l-6 6H5z"/><path d="M13 20v-6h6"/><path d="M8.5 9h7M8.5 12.5h4"/></svg>',
  paperclip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5l-8.6 8.6a5 5 0 0 1-7.1-7.1l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M10.1 5.0L10.7 2.5L13.3 2.5L13.9 5.0L15.6 5.8L17.8 4.3L19.7 6.2L18.2 8.4L19.0 10.1L21.5 10.7L21.5 13.3L19.0 13.9L18.2 15.6L19.7 17.8L17.8 19.7L15.6 18.2L13.9 19.0L13.3 21.5L10.7 21.5L10.1 19.0L8.4 18.2L6.2 19.7L4.3 17.8L5.8 15.6L5.0 13.9L2.5 13.3L2.5 10.7L5.0 10.1L5.8 8.4L4.3 6.2L6.2 4.3L8.4 5.8z"/><circle cx="12" cy="12" r="3"/></svg>',
  branch: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10M18 9c0 5-7 4-11.4 8.6"/></svg>',
  file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></svg>',
  tree: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3.5" width="6" height="5" rx="1"/><rect x="13" y="10" width="7" height="4.5" rx="1"/><rect x="13" y="16" width="7" height="4.5" rx="1"/><path d="M7 8.5v10h6M7 12.3h6"/></svg>',
  list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1" fill="currentColor"/><circle cx="4.5" cy="12" r="1" fill="currentColor"/><circle cx="4.5" cy="18" r="1" fill="currentColor"/></svg>',
  comment: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M4 5h16v11H10l-5 4v-4H4z"/></svg>',
  width: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4v16M20 4v16M8 12h8M10.5 9.5L8 12l2.5 2.5M13.5 9.5L16 12l-2.5 2.5"/></svg>',
};
const icon = (name) => {
  const span = el('span');
  span.innerHTML = ICONS[name];
  return span.firstChild;
};

// On a Mac the app shortcuts use Cmd, and Ctrl+C / Ctrl+V belong to the CLI (interrupt, image paste).
const MAC = /Mac|iPhone|iPad/.test(navigator.userAgentData?.platform || navigator.platform || '');
const MONO = '"Cascadia Mono", "Cascadia Code", Consolas, "SF Mono", Menlo, Monaco, "DejaVu Sans Mono", monospace';
const HISTORY_WINDOW = 400;
// Text width slider 0..100: 0 = narrowest, 50 = the classic 800px column, 100 = full width.
const HISTORY_WIDTH = { min: 480, normal: 800, start: 50 };
const DAY = 864e5;
const DATE_FORMATS = {};

// Date formats of the current language, made once per language.
function dates() {
  DATE_FORMATS[locale()] ||= {
    month: new Intl.DateTimeFormat(locale(), { month: 'long', year: 'numeric' }),
    short: new Intl.DateTimeFormat(locale(), { day: 'numeric', month: 'short' }),
    clock: new Intl.DateTimeFormat(locale(), { hour: '2-digit', minute: '2-digit' }),
  };
  return DATE_FORMATS[locale()];
}

const money = (usd) => new Intl.NumberFormat(locale(), { style: 'currency', currency: 'USD', maximumFractionDigits: usd < 1 ? 3 : 2 }).format(usd);
const count = (n) => new Intl.NumberFormat(locale(), { notation: 'compact', maximumFractionDigits: 1 }).format(n);

const quote = (text) => t('quoted', { text });

// t() for a text with elements in it: each {placeholder} named in nodes is put in as that node.
function textWith(key, nodes) {
  return t(key).split(/(\{\w+\})/).filter(Boolean)
    .map((part) => (/^\{\w+\}$/.test(part) && nodes[part.slice(1, -1)]) || part);
}

const state = {
  sessions: [],
  byId: new Map(),
  terminals: new Map(),   // terminal id -> status row
  bySession: new Map(),   // session id -> running terminal row
  external: new Map(),    // session id -> CLI running outside CLIDA
  lastStatus: new Map(),  // terminal id -> previous status, to notice "finished"
  attention: new Set(),   // terminal ids that finished or need input while unseen
  tabs: [],
  active: null,
  home: '',
  renaming: false,
  folders: [],
  dragging: null,   // session id while a chat is dragged
  menu: null,       // open context menu
  sessionsSeq: 0,   // numbers sidebar loads, so a late answer cannot undo a newer state
  tabPress: null,   // pressed or dragged tab (see tabPointerDown)
  tabSettle: null,  // a dropped tab still gliding into its slot
  attachTarget: null, // tab whose paperclip opened the file picker
  answer: null,     // resolves the question in the ask dialog
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
// SANITIZE_NAMED_PROPS prefixes id and name, so an id="toast" in a message cannot hijack the app's own.
const PURIFY = {
  FORBID_TAGS: ['style', 'form', 'input', 'button', 'textarea', 'select'], FORBID_ATTR: ['style'],
  SANITIZE_NAMED_PROPS: true,
};
const markdown = (text) => DOMPurify.sanitize(marked.parse(text), PURIFY);
hljs.registerAliases(['mysql', 'mariadb', 'pgsql', 'postgres', 'postgresql', 'sqlite', 'tsql', 'plsql'], { languageName: 'sql' });

function renderMarkdown(node, text) {
  node.innerHTML = markdown(text);
  for (const pre of node.querySelectorAll('pre')) enhanceCodeBlock(pre);
}

function enhanceCodeBlock(pre) {
  const code = pre.querySelector('code');
  if (!code) return;
  const lang = [...code.classList].find((c) => c.startsWith('language-'))?.slice('language-'.length) || '';
  if (lang && hljs.getLanguage(lang)) hljs.highlightElement(code);
  const box = el('div', 'codeblock');
  const bar = el('div', 'codeblock-bar');
  const copy = el('button', 'codeblock-copy');
  copy.type = 'button';
  copy.title = t('copy.title');
  copy.append(icon('copy'), el('span', '', t('copy')));
  copy.onclick = () => copyText(code.textContent.replace(/\n$/, ''), copy);
  bar.append(el('span', 'codeblock-lang', lang || 'code'), copy);
  pre.replaceWith(box);
  box.append(bar, pre);
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = el('textarea');
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  button.replaceChildren(icon('check'), el('span', '', t('copied')));
  button.classList.add('done');
  clearTimeout(button.resetTimer);
  button.resetTimer = setTimeout(() => {
    button.replaceChildren(icon('copy'), el('span', '', t('copy')));
    button.classList.remove('done');
  }, 1500);
}

function historyWidthCss(value) {
  const { min, normal } = HISTORY_WIDTH;
  if (value <= 50) return `${Math.round(min + (normal - min) * value / 50)}px`;
  return `calc(${normal}px + (100% - ${normal}px) * ${((value - 50) / 50).toFixed(3)})`;
}

function setHistoryWidth(value) {
  document.documentElement.style.setProperty('--history-width', historyWidthCss(value));
  store.set('historyWidth', value);
  for (const tab of state.tabs) tab.widthRange.value = String(value);
}

// A 404 for an unknown route: the server runs older code than this page. Servers from before the
// language setting send only this German text.
const staleServer = (status, data) => status === 404 && (data?.code === 'no_route' || data?.error === 'Nicht gefunden');

// This window, for the server: an open window reloads by itself after a restart, so `clida restart`
// opens a new one only when none is open. Closing the window says so (see wire).
const WINDOW_ID = [...crypto.getRandomValues(new Uint8Array(8))].map((b) => b.toString(16).padStart(2, '0')).join('');

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { 'X-Clida-Window': WINDOW_ID, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const err = new Error(staleServer(res.status, data) ? t('restartNeeded') : data?.error || `HTTP ${res.status}`);
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
  if (data.boot) {
    state.boot ||= data.boot;
    if (data.boot !== state.boot) reloadSafely();
  }
  state.terminals = new Map(data.terminals.map((row) => [row.id, row]));
  state.bySession = new Map(data.terminals.filter((row) => row.status !== 'exited').map((row) => [row.session_id, row]));
  state.external = new Map(data.external.map((e) => [e.session_id, e]));
  for (const tab of state.tabs) {
    const row = state.terminals.get(tab.id);
    if (row) tab.sid = row.session_id;  // follows /clear and /resume inside the CLI
  }
  let finished = false;
  for (const row of data.terminals) {
    const prev = state.lastStatus.get(row.id);
    if (prev && prev !== row.status) {
      const done = row.status === 'waiting' || row.status === 'exited' || (prev === 'busy' && row.status === 'idle');
      if (done && (state.active !== row.id || document.hidden)) state.attention.add(row.id);
      if (done) finished = true;
    }
    state.lastStatus.set(row.id, row.status);
  }
  return finished;
}

async function refreshStatus() {
  let finished = false;
  const asked = Date.now();
  try {
    finished = applyStatus(await api('GET', '/api/status'));
    setOnline(true);
  } catch (e) {
    setOnline(false, e.status);
    return;
  }
  for (const tab of [...state.tabs]) {
    // An answer older than the tab's terminal cannot know it yet.
    if (tab.id !== tab.sid && !state.terminals.has(tab.id) && tab.since < asked) historyTab(tab);
  }
  paint();
  if (finished) {
    refreshSessions();
    const tab = activeTab();
    if (tab && tab.view === 'history' && tab.loaded) loadHistory(tab, { quiet: true });
    for (const other of state.tabs) if (other !== tab && other.loaded) other.stale = true;  // reload when shown
    for (const other of state.tabs) loadChanges(other);  // the header and the switch show its counts
  }
}

// The tab's terminal is gone (server restart, or forgotten after it ended): it shows the chat's
// history from now on, under the chat's id. If another tab shows that chat already, it closes.
function historyTab(tab) {
  disposeTerminal(tab);
  if (findTab(tab.sid)) {
    closeTab(tab);
    return;
  }
  state.attention.delete(tab.id);
  if (state.active === tab.id) state.active = tab.sid;
  tab.id = tab.sid;
  tab.view = 'history';
  saveTabs();
  loadHistory(tab);
}

async function refreshSessions() {
  const seq = ++state.sessionsSeq;
  let data;
  try {
    data = await api('GET', '/api/sessions');
    setOnline(true);
  } catch (e) {
    setOnline(false, e.status);
    return;
  }
  if (seq !== state.sessionsSeq) return;  // a newer load or a local change came in meanwhile
  state.home = data.home;
  state.sessions = data.sessions;
  state.byId = new Map(data.sessions.map((s) => [s.id, s]));
  state.folders = data.folders || [];
  state.costToday = data.cost_today ?? null;
  applyStatus(data);
  if (!state.renaming && !state.dragging) renderSidebar();
  paint();
}

// Change sidebar data on the server. Loads that are still on the way carry the old state,
// so they are dropped, and a fresh list follows once the change is saved.
async function change(method, path, body) {
  state.sessionsSeq += 1;
  const result = await api(method, path, body);
  refreshSessions();
  return result;
}

// Reload the page: after a server restart, perhaps with new code, so the page matches it, and by
// F5. What is being written is settled first: open notes are saved, a rename keeps the old name,
// and an open new chat dialog starts nothing (the reload just drops it). Nothing that goes wrong
// while settling keeps the page from reloading.
async function reloadSafely() {
  if (state.reloading) return;
  state.reloading = true;
  await settleWriting().catch(() => {});
  location.reload();
}

// Before the page goes: open notes are saved, a rename keeps the old name, and an open new chat
// dialog starts nothing (it goes with the page).
async function settleWriting() {
  for (const input of document.querySelectorAll('.rename-input')) {
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
  }
  const notes = [...document.querySelectorAll('#views .note-editor')];
  await Promise.all(notes.map((editor) => Promise.resolve(editor.flush?.()).catch(() => {})));
}

// ---- one window ---------------------------------------------------------------------------
// CLIDA runs in one window per browser. `clida` brings an open window to the front instead of
// opening another; a second page that comes up anyway (a link from `clida url`, the address typed
// into a tab) finds the first one on this channel and steps aside. "Use it here" turns that round.

const peers = 'BroadcastChannel' in window ? new BroadcastChannel('clida') : null;

// True when no other CLIDA page answers: this window is the one.
function claimWindow() {
  if (!peers) return Promise.resolve(true);
  return new Promise((resolve) => {
    const heard = (ev) => {
      if (ev.data?.type !== 'here') return;
      clearTimeout(timer);
      peers.removeEventListener('message', heard);
      resolve(false);
    };
    const timer = setTimeout(() => {
      peers.removeEventListener('message', heard);
      resolve(true);
    }, 250);
    peers.addEventListener('message', heard);
    peers.postMessage({ type: 'hello' });
  });
}

peers?.addEventListener('message', (ev) => {
  if (!state.claimed) return;
  if (ev.data?.type === 'hello') {
    peers.postMessage({ type: 'here' });
    window.focus();  // may or may not raise the window; the browser decides
  } else if (ev.data?.type === 'take-over') {
    giveWay();
  }
});

// Another page took over: settle what is being written, then close. A browser keeps a tab open
// that the user opened by hand; reloaded, it finds the new one and shows the notice instead.
async function giveWay() {
  state.claimed = false;
  await settleWriting();
  window.close();
  await new Promise((resolve) => setTimeout(resolve, 1000));  // the taker claims first, or both would
  location.reload();
}

function stepAside() {
  window.close();  // a window that `clida` opened closes; a tab opened by hand stays
  const here = el('button', 'btn primary', t('single.useHere'));
  here.onclick = () => {
    peers.postMessage({ type: 'take-over' });
    location.reload();
  };
  const notice = el('div', 'single-notice');
  notice.append(el('h1', '', t('single.elsewhere')), el('p', '', t('single.hint')), here);
  document.body.replaceChildren(notice);
}

function setOnline(online, status) {
  state.online = online;
  const banner = $('#banner');
  banner.hidden = online;
  if (online) return;
  // 403: the server runs but no longer knows this window (new token), so a reload cannot help.
  banner.replaceChildren(...textWith(status === 403 ? 'banner.expired' : 'banner.offline', { cmd: el('code', '', 'clida') }));
}

const tabSession = (tab) => state.terminals.get(tab.id)?.session_id || tab.sid;
const titleOf = (sid) => state.byId.get(sid)?.title || t('chat.new');
const activeTab = () => state.tabs.find((tab) => tab.id === state.active) || null;
const findTab = (id) => state.tabs.find((tab) => tab.id === id) || null;

function statusFor(sid) {
  const term = state.bySession.get(sid);
  if (term) return { cls: term.status, label: t(`status.${term.status}`), attention: state.attention.has(term.id) };
  const ext = state.external.get(sid);
  if (ext) {
    const label = t('status.external', { status: t(`status.${ext.status}`) });
    return { cls: `external ${ext.status === 'busy' ? 'busy' : ''}`, label, attention: false };
  }
  return { cls: '', label: '', attention: false };
}

// ---- sidebar ------------------------------------------------------------------------------

function groupLabel(mtime) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const time = mtime * 1000;
  if (time >= today) return t('group.today');
  if (time >= today - DAY) return t('group.yesterday');
  if (time >= today - 6 * DAY) return t('group.week');
  if (time >= today - 29 * DAY) return t('group.month');
  return dates().month.format(new Date(time));
}

function timeLabel(mtime) {
  const d = new Date(mtime * 1000);
  return d.toDateString() === new Date().toDateString() ? dates().clock.format(d) : dates().short.format(d);
}

function matchesSearch(s, query) {
  return !query || [s.title, s.cwd_label, s.first_prompt, s.last_prompt].some((v) => v && v.toLowerCase().includes(query));
}

function renderSidebar() {
  const list = $('#session-list');
  const query = $('#search').value.trim().toLowerCase();
  const collapsedFolders = store.get('collapsedFolders', {});
  const byFolder = new Map(state.folders.map((f) => [f.id, []]));
  const loose = [];
  const archived = [];
  for (const s of state.sessions) {
    if (!matchesSearch(s, query)) continue;
    if (s.archived) archived.push(s);
    else if (byFolder.has(s.folder)) byFolder.get(s.folder).push(s);
    else loose.push(s);
  }
  const nodes = [];
  for (const folder of state.folders) {
    const chats = byFolder.get(folder.id);
    if (query && !chats.length) continue;
    nodes.push(folderNode(folder, chats, query ? true : !collapsedFolders[folder.id]));
  }
  let group = null;
  for (const s of loose) {
    const label = groupLabel(s.mtime);
    if (label !== group) {
      nodes.push(el('div', 'group-label', label));
      group = label;
    }
    nodes.push(sessionItem(s));
  }
  if (archived.length) nodes.push(archiveNode(archived, query ? true : store.get('archiveOpen', false)));
  if (!nodes.length) nodes.push(el('div', 'list-empty', t(query ? 'list.noMatches' : 'list.empty')));
  const focused = document.activeElement?.closest('#session-list .item, #session-list .folder-head, #session-list .archive-head');
  const focusKey = focused && (focused.dataset.id || focused.dataset.folder || 'archive');
  list.replaceChildren(...nodes);
  if (focusKey) focusSidebar(focusKey);
}

// Put keyboard focus back on a sidebar entry (chat id, folder id or 'archive') after a rebuild.
function focusSidebar(key) {
  const list = $('#session-list');
  const node = key === 'archive'
    ? list.querySelector('.archive-head')
    : list.querySelector(`.item[data-id="${key}"], .folder-head[data-folder="${key}"]`);
  node?.focus();
}

function sessionItem(s) {
  const item = el('div', 'item');
  item.dataset.id = s.id;
  item.title = [s.note && t('note.tooltip', { note: s.note }), s.first_prompt?.slice(0, 300)].filter(Boolean).join('\n\n');
  const text = el('div', 'item-text');
  const title = el('div', 'item-title', s.title);
  const meta = el('div', 'item-meta', [s.cwd_label, timeLabel(s.mtime)].filter(Boolean).join(' · '));
  if (s.note) {
    const mark = el('span', 'note-mark');
    mark.append(icon('note'));
    meta.prepend(mark);
  }
  text.append(title, meta);
  const rename = el('button', 'icon-btn');
  rename.title = t('rename');
  rename.append(icon('pencil'));
  rename.onclick = (ev) => { ev.stopPropagation(); startRename(title, s.id); };
  title.ondblclick = (ev) => { ev.stopPropagation(); startRename(title, s.id); };
  item.onclick = () => openSession(s.id);
  item.tabIndex = 0;
  item.setAttribute('role', 'button');
  item.onkeydown = (ev) => onItemKey(ev, item, () => openSession(s.id), () => startRename(title, s.id));
  if (!s.archived) {
    item.draggable = true;
    item.ondragstart = (ev) => startDrag(ev, s.id);
    item.ondragend = endDrag;
  }
  item.append(el('span', 'dot'), text, rename);
  return item;
}

function folderNode(folder, chats, open) {
  const box = el('div', 'folder');
  const head = el('div', 'folder-head');
  head.dataset.folder = folder.id;
  head.tabIndex = 0;
  head.setAttribute('role', 'button');
  head.setAttribute('aria-expanded', String(open));
  head.append(icon(open ? 'chevronDown' : 'chevronRight'), icon('folder'),
    el('span', 'folder-name', folder.name), el('span', 'folder-count', String(chats.length)));
  head.onclick = () => toggleFolder(folder.id);
  head.onkeydown = (ev) => onItemKey(ev, head, () => toggleFolder(folder.id), () => renameFolder(folder.id));
  box.append(head);
  if (open) {
    const body = el('div', 'folder-body');
    body.append(...(chats.length ? chats.map(sessionItem) : [el('div', 'folder-empty', t('folder.dropHere'))]));
    box.append(body);
  }
  dropZone(box, folder.id);
  return box;
}

function archiveNode(chats, open) {
  const box = el('div', 'archive');
  const head = el('div', 'archive-head');
  head.tabIndex = 0;
  head.setAttribute('role', 'button');
  head.setAttribute('aria-expanded', String(open));
  head.append(icon(open ? 'chevronDown' : 'chevronRight'), icon('archive'),
    el('span', 'folder-name', t('archive.title')), el('span', 'folder-count', String(chats.length)));
  const toggle = () => {
    store.set('archiveOpen', !open);
    renderSidebar();
    paintSidebar();
  };
  head.onclick = toggle;
  head.onkeydown = (ev) => onItemKey(ev, head, toggle, () => {});
  box.append(head);
  if (open) {
    const body = el('div', 'folder-body');
    body.append(...chats.map(sessionItem));
    box.append(body);
  }
  return box;
}

function toggleFolder(folderId) {
  const collapsed = store.get('collapsedFolders', {});
  if (collapsed[folderId]) delete collapsed[folderId];
  else collapsed[folderId] = true;
  store.set('collapsedFolders', collapsed);
  renderSidebar();
  paintSidebar();
}

// Enter/Space opens, F2 renames - only when the entry itself has focus, not its rename field.
function onItemKey(ev, node, open, rename) {
  if (ev.target !== node) return;
  if (ev.key === 'Enter' || ev.key === ' ') open();
  else if (ev.key === 'F2') rename();
  else return;
  ev.preventDefault();
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

// Swap target's text for an input. Enter or leaving the field saves, Escape cancels.
// focusKey: the sidebar entry that gets keyboard focus back afterwards (see focusSidebar).
// maxLength: the server's limit, so the field never shows more than will be stored.
function inlineEdit(target, initial, save, { focusKey = null, maxLength = 200 } = {}) {
  if (target.querySelector('input')) return;
  const original = target.textContent;
  const input = el('input', 'rename-input');
  input.autocomplete = 'off';  // no autofill suggestions from what was typed into other fields
  input.maxLength = maxLength;
  input.value = initial;
  target.replaceChildren(input);
  input.focus();
  input.select();
  state.renaming = true;
  let done = false;
  const finish = async (commit) => {
    if (done) return;
    done = true;
    const value = input.value.trim();
    const refocus = document.activeElement === input;  // false when the user clicked elsewhere
    target.textContent = commit && value ? value : original;
    if (commit && value && value !== initial) {
      try {
        await save(value);
      } catch (e) {
        target.textContent = original;
        toast(e.message);
      }
    }
    state.renaming = false;
    renderSidebar();
    paint();
    if (refocus && focusKey) focusSidebar(focusKey);
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

function startRename(target, sid) {
  const inSidebar = !!target.closest('#session-list');
  inlineEdit(target, titleOf(sid), async (value) => {
    await change('PUT', `/api/sessions/${sid}/title`, { title: value });
    const s = state.byId.get(sid);
    if (s) s.title = value;
  }, { focusKey: inSidebar ? sid : null, maxLength: 200 });
}

// ---- folders, archive, delete -------------------------------------------------------------

async function newFolder() {
  if (state.addingFolder) return;  // a second click while the first folder is on its way
  state.addingFolder = true;
  let folder;
  try {
    folder = await change('POST', '/api/folders', { name: t('folder.new') });
  } catch (e) {
    toast(e.message);
    return;
  } finally {
    state.addingFolder = false;
  }
  $('#search').value = '';  // a search would hide the new, still empty folder
  if (!state.folders.some((f) => f.id === folder.id)) state.folders.push(folder);
  renderSidebar();
  paintSidebar();
  renameFolder(folder.id);
}

// Look folders up by id at every step: a sidebar reload replaces the objects in state.folders,
// and a name written into an old object would never show up.
function renameFolder(folderId) {
  const folder = state.folders.find((f) => f.id === folderId);
  const name = $(`#session-list .folder-head[data-folder="${folderId}"] .folder-name`);
  if (!folder || !name) return;
  name.scrollIntoView({ block: 'nearest' });
  inlineEdit(name, folder.name, async (value) => {
    await change('PUT', `/api/folders/${folderId}`, { name: value });
    const current = state.folders.find((f) => f.id === folderId);
    if (current) current.name = value;
  }, { focusKey: folderId, maxLength: 80 });
}

async function deleteFolder(folder) {
  try {
    await change('DELETE', `/api/folders/${folder.id}`);
  } catch (e) {
    toast(e.message);
  }
}

async function moveToFolder(sid, folderId) {
  const s = state.byId.get(sid);
  if (!s || (s.folder || null) === folderId) return;
  try {
    await change('PUT', `/api/sessions/${sid}/folder`, { folder: folderId });
  } catch (e) {
    toast(e.message);
    return;
  }
  const current = state.byId.get(sid);
  if (current) current.folder = folderId;
  if (folderId) expandFolder(folderId);
  renderSidebar();
  paintSidebar();
}

// Open a folder that just got a chat, so the chat does not seem to vanish.
function expandFolder(folderId) {
  const collapsed = store.get('collapsedFolders', {});
  delete collapsed[folderId];
  store.set('collapsedFolders', collapsed);
}

async function setArchived(sid, archived) {
  try {
    await change('PUT', `/api/sessions/${sid}/archived`, { archived });
  } catch (e) {
    toast(e.message);
    return;
  }
  const s = state.byId.get(sid);
  if (s) s.archived = archived;
  renderSidebar();
  paintSidebar();
}

// A yes/no question in CLIDA's own dialog; the browser's confirm() would head it "localhost says".
// text is a string or a list of strings and nodes. Resolves true for yes; Cancel and Esc are no.
function ask({ title, text, yes, danger = false }) {
  const dialog = $('#ask-dialog');
  if (dialog.open) return Promise.resolve(false);  // one question at a time
  $('#ask-title').textContent = title;
  $('#ask-text').replaceChildren(...[].concat(text));
  $('#ask-yes').textContent = yes;
  $('#ask-yes').className = `btn ${danger ? 'danger-solid' : 'primary'}`;
  dialog.showModal();
  $('#ask-cancel').focus();
  return new Promise((resolve) => { state.answer = resolve; });
}

// The buttons answer directly: the dialog's close event comes later and could already find the
// next question open.
function answer(yes) {
  const resolve = state.answer;
  state.answer = null;
  $('#ask-dialog').close();
  resolve?.(yes);
}

async function deleteChat(sid) {
  const name = el('strong', '', quote(titleOf(sid)));
  const text = textWith('delete.text', { name });
  if (!(await ask({ title: t('delete.title'), text, yes: t('delete'), danger: true }))) return;
  try {
    await change('DELETE', `/api/sessions/${sid}`);
  } catch (e) {
    toast(e.message);
    return;
  }
  for (const tab of [...state.tabs]) {
    const row = state.terminals.get(tab.id);
    if (tabSession(tab) === sid && (!row || row.status === 'exited')) closeTab(tab);
  }
}

// ---- drag and drop ------------------------------------------------------------------------

function startDrag(ev, sid) {
  state.dragging = sid;
  ev.dataTransfer.setData('application/x-clida-session', sid);
  ev.dataTransfer.effectAllowed = 'move';
  closeMenu();
}

function endDrag() {
  state.dragging = null;
  for (const node of document.querySelectorAll('.drop-target')) node.classList.remove('drop-target');
}

// node accepts dragged chats: into a folder, or with folderId null back into the main list.
function dropZone(node, folderId) {
  node.addEventListener('dragover', (ev) => {
    if (!state.dragging) return;
    ev.stopPropagation();
    if ((state.byId.get(state.dragging)?.folder || null) === folderId) return;  // already there
    ev.preventDefault();
    ev.dataTransfer.dropEffect = 'move';
    for (const other of document.querySelectorAll('.drop-target')) if (other !== node) other.classList.remove('drop-target');
    node.classList.add('drop-target');
  });
  node.addEventListener('dragleave', (ev) => {
    if (!node.contains(ev.relatedTarget)) node.classList.remove('drop-target');
  });
  node.addEventListener('drop', (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const sid = state.dragging;
    endDrag();
    if (sid) moveToFolder(sid, folderId);
  });
}

// ---- context menu -------------------------------------------------------------------------

function chatMenu(sid, ev, anchor) {
  const s = state.byId.get(sid);
  if (!s) return;
  showMenu(ev, anchor, [
    s.archived
      ? { label: t('restore'), icon: 'restore', action: () => setArchived(sid, false) }
      : { label: t('archive'), icon: 'archive', action: () => setArchived(sid, true) },
    { label: t('delete'), icon: 'trash', danger: true, action: () => deleteChat(sid) },
  ]);
}

function folderMenu(folderId, ev, anchor) {
  const folder = state.folders.find((f) => f.id === folderId);
  if (!folder) return;
  showMenu(ev, anchor, [
    { label: t('rename'), icon: 'pencil', action: () => renameFolder(folder.id) },
    { label: t('folder.delete'), icon: 'trash', danger: true, action: () => deleteFolder(folder) },
  ]);
}

function showMenu(ev, anchor, entries) {
  closeMenu();
  const menu = el('div', 'ctx-menu');
  menu.setAttribute('role', 'menu');
  for (const entry of entries) {
    const button = el('button', entry.danger ? 'ctx-item danger' : 'ctx-item');
    button.type = 'button';
    button.setAttribute('role', 'menuitem');
    button.append(icon(entry.icon), el('span', '', entry.label));
    button.onclick = () => {
      closeMenu();
      entry.action();
    };
    menu.append(button);
  }
  menu.onkeydown = (e) => {
    const items = [...menu.querySelectorAll('button')];
    const at = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') items[(at + 1) % items.length].focus();
    else if (e.key === 'ArrowUp') items[(at - 1 + items.length) % items.length].focus();
    else if (e.key === 'Escape' || e.key === 'Tab') {
      closeMenu();
      anchor.focus();
    } else return;
    e.preventDefault();
  };
  document.body.append(menu);
  // Opened by keyboard (menu key, Shift+F10) there is no pointer position, so use the entry's.
  const box = anchor.getBoundingClientRect();
  const x = ev.clientX || box.left + 24;
  const y = ev.clientY || box.bottom;
  const { width, height } = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(4, Math.min(x, innerWidth - width - 4))}px`;
  menu.style.top = `${Math.max(4, Math.min(y, innerHeight - height - 4))}px`;
  anchor.classList.add('menu-open');
  state.menu = { menu, anchor };
  menu.querySelector('button').focus();
}

function closeMenu() {
  if (!state.menu) return;
  state.menu.menu.remove();
  state.menu.anchor.classList.remove('menu-open');
  state.menu = null;
}

function setCollapsed(collapsed) {
  $('#app').classList.toggle('collapsed', collapsed);
  $('.sidebar').inert = collapsed;  // 0 px wide, but Tab would still walk through its entries
  store.set('collapsed', collapsed);
  setTimeout(() => fitTab(activeTab()), 200);
}

// ---- tabs ---------------------------------------------------------------------------------

function saveTabs() {
  store.set('tabs', state.tabs.map((tab) => ({ id: tab.id, sid: tab.sid, view: tab.view })));
  store.set('active', state.active);
}

// Open a chat: in the tab of its running terminal, else in the tab that shows it already, else in a
// new history tab. A terminal tab's id is the terminal's, a history tab's id is the chat's.
function openSession(sid) {
  const term = state.bySession.get(sid);
  const shown = term ? findTab(term.id) : state.tabs.find((tab) => tabSession(tab) === sid);
  if (shown) return activate(shown.id);
  addTab(term ? term.id : sid, term ? 'terminal' : 'history', sid);
  activate(term ? term.id : sid);
}

function addTab(id, view, sid = id) {
  const tab = { id, sid, since: Date.now(), view, term: null, fit: null, ws: null, loaded: false, stale: false,
    showAll: false, items: [], notes: { session: null, messages: [] }, changes: null };
  buildView(tab);
  state.tabs.push(tab);
  saveTabs();
  loadNotes(tab);
  loadChanges(tab);  // the header shows the branch, the switch the number of changed files
  return tab;
}

function buildView(tab) {
  const root = el('section', 'view');
  const head = el('header', 'view-head');
  const titleBox = el('div', 'view-titlebox');
  const title = el('h1', 'view-title');
  title.onclick = () => startRename(title, tabSession(tab));
  const meta = el('div', 'view-meta');
  titleBox.append(title, meta);

  const widthCtl = el('label', 'width-ctl');
  const widthRange = el('input');
  widthRange.type = 'range';
  widthRange.min = '0';
  widthRange.max = '100';
  widthRange.value = String(store.get('historyWidth', HISTORY_WIDTH.start));
  widthRange.oninput = () => setHistoryWidth(Number(widthRange.value));
  widthRange.ondblclick = () => setHistoryWidth(HISTORY_WIDTH.start);
  widthCtl.append(icon('width'), widthRange);

  const seg = el('div', 'seg');
  const histBtn = el('button');
  const termBtn = el('button');
  const changesBtn = el('button');
  histBtn.onclick = () => setView(tab, 'history');
  termBtn.onclick = () => setView(tab, 'terminal');
  changesBtn.onclick = () => setView(tab, 'changes');
  seg.append(histBtn, termBtn, changesBtn);

  const actions = el('div', 'view-actions');
  const refresh = el('button', 'icon-btn');
  refresh.append(icon('refresh'));
  refresh.onclick = () => (tab.view === 'changes' ? loadChanges(tab) : loadHistory(tab));
  const attach = el('button', 'icon-btn');
  attach.append(icon('paperclip'));
  attach.onclick = () => {
    state.attachTarget = tab;
    $('#attach-input').click();
  };
  const noteBtn = el('button', 'icon-btn');
  noteBtn.append(icon('note'));
  noteBtn.onclick = () => editSessionNote(tab);
  const resume = el('button', 'btn primary');
  resume.onclick = () => resumeTab(tab);
  const stop = el('button', 'btn danger');
  stop.onclick = () => stopTab(tab);
  actions.append(refresh, noteBtn, attach, resume, stop);
  head.append(titleBox, widthCtl, seg, actions);

  const body = el('div', 'view-body');
  const hist = el('div', 'history');
  const histInner = el('div', 'history-inner');
  hist.append(histInner);
  const changesPane = el('div', 'changes');
  const changesInner = el('div', 'changes-inner');
  changesPane.append(changesInner);
  const termWrap = el('div', 'term-wrap');
  const termHost = el('div', 'term-host');
  const overlay = el('div', 'term-overlay');
  overlay.hidden = true;
  termWrap.append(termHost, overlay);
  body.append(hist, changesPane, termWrap);
  const sessionNote = el('div', 'session-note');
  sessionNote.hidden = true;
  root.append(head, sessionNote, body);
  $('#views').append(root);
  Object.assign(tab, { root, title, meta, widthCtl, widthRange, histBtn, termBtn, changesBtn, refresh, attach, noteBtn,
    resume, stop, sessionNote, hist, histInner, changesPane, changesInner, termWrap, termHost, overlay });
  labelView(tab);
}

// The view's fixed texts, set again after a language switch.
function labelView(tab) {
  tab.title.title = t('view.clickToRename');
  tab.widthCtl.title = t('width.title');
  tab.widthRange.setAttribute('aria-label', t('width'));
  tab.histBtn.textContent = t('view.history');
  tab.termBtn.textContent = t('view.terminal');
  tab.refresh.title = t(tab.view === 'changes' ? 'changes.reload' : 'history.reload');
  tab.attach.title = t('attach.title');
  tab.noteBtn.title = t('note.session');
  tab.resume.textContent = t('resume');
  tab.stop.textContent = t('stop');
  if (!tab.overlay.hidden && tab.overlayText) showOverlay(tab, ...tab.overlayText);
}

function activate(id) {
  const tab = findTab(id);
  if (!tab) return;
  state.active = id;
  if (!document.hidden) state.attention.delete(id);
  for (const other of state.tabs) other.root.classList.toggle('active', other === tab);
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
  } else if (tab.view === 'changes') {
    loadChanges(tab);  // full: the diffs come only now
  } else if (!tab.loaded || tab.stale) {
    loadHistory(tab, { quiet: tab.loaded });
  }
}

function setView(tab, view) {
  tab.view = view;
  saveTabs();
  paint();
  if (view === 'history' && tab.loaded) loadHistory(tab, { quiet: true });
  tab.refresh.title = t(view === 'changes' ? 'changes.reload' : 'history.reload');
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
  const index = state.tabs.findIndex((tab) => tab.id === state.active);
  const next = state.tabs[(index + step + state.tabs.length) % state.tabs.length];
  activate(next.id);
}

function renderTabs() {
  if (state.renaming && document.activeElement?.closest('#tabs')) return;
  // A rebuild would pull the pressed, dragged or gliding tab away; only the active mark changes.
  if (state.tabPress || state.tabSettle) {
    syncTabClasses();
    return;
  }
  // Polling repaints every 2 s; rebuilding unchanged tabs would only throw away focus and hover.
  const signature = language() + JSON.stringify(state.tabs.map((tab) => {
    const sid = tabSession(tab);
    return [tab.id, sid, titleOf(sid), state.terminals.get(tab.id)?.status, statusFor(sid).cls,
      state.attention.has(tab.id), tab.id === state.active, state.byId.get(sid)?.note];
  }));
  if (signature === state.tabsSignature) return;
  state.tabsSignature = signature;
  const focusedTab = document.activeElement?.closest('#tabs .tab');
  const focusId = focusedTab?.dataset.id;
  const focusClose = !!focusedTab && document.activeElement !== focusedTab;
  const nodes = state.tabs.map((tab) => {
    const sid = tabSession(tab);
    const st = statusFor(sid);
    const row = state.terminals.get(tab.id);
    const node = el('div', 'tab');
    node.classList.toggle('active', tab.id === state.active);
    node.classList.toggle('attention', state.attention.has(tab.id));
    node.setAttribute('role', 'tab');
    node.setAttribute('aria-selected', String(tab.id === state.active));
    node.dataset.id = tab.id;
    node.tabIndex = 0;
    const note = state.byId.get(sid)?.note;
    node.title = titleOf(sid) + (st.label ? ` – ${st.label}` : '') + (note ? `\n${t('note.tooltip', { note })}` : '');
    const dot = el('span', `dot ${row ? row.status : st.cls} ${state.attention.has(tab.id) ? 'attention' : ''}`);
    const label = el('span', 'tab-label', titleOf(sid));
    label.ondblclick = (ev) => { ev.stopPropagation(); startRename(label, sid); };
    const close = el('button', 'icon-btn');
    close.title = t(row && row.status !== 'exited' ? 'tab.closeRunning' : 'tab.close');
    close.append(icon('x'));
    close.onclick = (ev) => { ev.stopPropagation(); closeTab(tab); };
    node.onclick = () => activate(tab.id);
    node.onauxclick = (ev) => { if (ev.button === 1) closeTab(tab); };
    node.onkeydown = (ev) => onItemKey(ev, node, () => activate(tab.id), () => startRename(label, sid));
    node.onpointerdown = (ev) => tabPointerDown(ev, tab, node);
    node.append(dot, label, close);
    return node;
  });
  $('#tabs').replaceChildren(...nodes);
  const again = focusId && $(`#tabs .tab[data-id="${focusId}"]`);
  if (again) (focusClose ? again.querySelector('.icon-btn') : again).focus();
}

// ---- tab order: drag tabs like in Chrome -------------------------------------------------
// Pressing a tab activates it, the pressed tab follows the pointer, the others slide aside, and on
// release it glides into its new slot. Meanwhile the 2 s repaint leaves the tab nodes alone.

const TAB_DRAG_START = 4;  // px of movement before a press becomes a drag (a click stays a click)
const TAB_SLIDE_MS = 150;

function tabPointerDown(ev, tab, node) {
  if (ev.button !== 0 || ev.target.closest('button, input')) return;
  settleTabs();  // a tab still gliding stops in its slot, so this press sees the real layout
  state.tabPress = { id: tab.id, node, startX: ev.clientX, pointerId: ev.pointerId, dragging: false };
  if (state.active !== tab.id) activate(tab.id);
}

function syncTabClasses() {
  for (const node of document.querySelectorAll('#tabs .tab')) {
    const on = node.dataset.id === state.active;
    node.classList.toggle('active', on);
    node.setAttribute('aria-selected', String(on));
  }
}

// End the glide of a dropped tab at once. The DOM is already in the new order, so nothing is rebuilt
// here: a press that comes in meanwhile keeps the node it grabbed.
function settleTabs() {
  const settle = state.tabSettle;
  if (!settle) return;
  clearTimeout(settle.timer);
  for (const node of settle.nodes) {
    node.classList.remove('sliding', 'landing');
    node.style.transform = '';
  }
  state.tabSettle = null;
}

function startTabDrag(press) {
  const slots = [...document.querySelectorAll('#tabs .tab')].map((node) => {
    const box = node.getBoundingClientRect();
    return { node, left: box.left, width: box.width };
  });
  press.from = slots.findIndex((slot) => slot.node === press.node);
  press.slot = slots[press.from];
  press.others = slots.filter((slot) => slot.node !== press.node);
  press.step = press.slot.width + (parseFloat(getComputedStyle($('#tabs')).columnGap) || 0);
  const last = slots[slots.length - 1];
  press.minDx = slots[0].left - press.slot.left;
  press.maxDx = last.left + last.width - (press.slot.left + press.slot.width);
  press.target = press.from;
  press.dragging = true;
  try { press.node.setPointerCapture(press.pointerId); } catch { /* pointer already gone */ }
  $('#tabs').classList.add('dragging');  // no hover effects on the tabs that slide by
  press.node.classList.add('lifted');
  for (const other of press.others) other.node.classList.add('sliding');
}

function tabPointerMove(ev) {
  const press = state.tabPress;
  if (!press || ev.pointerId !== press.pointerId) return;
  const dx = ev.clientX - press.startX;
  if (!press.dragging) {
    if (Math.abs(dx) < TAB_DRAG_START) return;
    startTabDrag(press);
  }
  const offset = Math.max(press.minDx, Math.min(press.maxDx, dx));
  press.node.style.transform = `translateX(${offset}px)`;
  // A neighbour makes room once the leading edge passes its middle: the left edge for tabs on
  // the left, the right edge for tabs on the right. Middles alone fail for tabs of other widths.
  const left = press.slot.left + offset;
  const right = left + press.slot.width;
  press.target = press.others.filter((other, i) => {
    const middle = other.left + other.width / 2;
    return i < press.from ? left >= middle : right > middle;
  }).length;
  press.others.forEach((other, i) => {
    let shift = 0;
    if (press.target > press.from && i >= press.from && i < press.target) shift = -press.step;
    if (press.target < press.from && i >= press.target && i < press.from) shift = press.step;
    other.node.style.transform = shift ? `translateX(${shift}px)` : '';
  });
}

function tabPointerUp(ev) {
  const press = state.tabPress;
  if (!press || ev.pointerId !== press.pointerId) return;
  if (!press.dragging) {
    state.tabPress = null;
    return;
  }
  // Every tab glides from where it is on screen right now - the dropped one from the pointer,
  // the others from wherever their slide had got to - into its new slot (FLIP).
  const nodes = [press.node, ...press.others.map((other) => other.node)];
  const onScreen = nodes.map((node) => node.getBoundingClientRect().left);
  $('#tabs').classList.remove('dragging');
  state.tabs.splice(press.target, 0, state.tabs.splice(press.from, 1)[0]);
  $('#tabs').insertBefore(press.node, press.others[press.target]?.node || null);
  press.node.classList.replace('lifted', 'landing');
  for (const node of nodes) {
    node.classList.remove('sliding');
    node.style.transform = '';
  }
  const slots = nodes.map((node) => node.getBoundingClientRect().left);
  nodes.forEach((node, i) => { node.style.transform = `translateX(${onScreen[i] - slots[i]}px)`; });
  press.node.getBoundingClientRect();  // apply these start positions before the transition begins
  for (const node of nodes) {
    node.classList.add('sliding');
    node.style.transform = '';
  }
  state.tabPress = null;
  saveTabs();
  const timer = setTimeout(() => {
    settleTabs();
    renderTabs();
  }, TAB_SLIDE_MS + 20);
  state.tabSettle = { nodes, timer };
}

function paintView(tab) {
  const sid = tabSession(tab);
  const row = state.terminals.get(tab.id);
  const session = state.byId.get(sid);
  const ext = state.external.get(sid);
  const live = row && row.status !== 'exited';
  const showTerm = tab.view === 'terminal' && !!row;
  const showChanges = tab.view === 'changes';
  if (!tab.title.querySelector('input')) tab.title.textContent = titleOf(sid);
  const parts = [session?.cwd_label || row?.cwd || ''];
  if (row) parts.push(t(`status.${row.status}`));
  else if (ext) parts.push(t('status.elsewhere'));
  const branch = tab.changesCounts?.git?.branch;
  if (branch) parts.push(t('view.branch', { branch }));
  const usage = session?.usage;
  if (usage?.cost) parts.push(`≈ ${money(usage.cost)}`);
  tab.meta.textContent = parts.filter(Boolean).join(' · ');
  tab.meta.title = usage ? t('usage.tooltip', {
    cost: money(usage.cost), input: count(usage.tokens.input_tokens), write: count(usage.tokens.cache_creation_input_tokens),
    read: count(usage.tokens.cache_read_input_tokens), output: count(usage.tokens.output_tokens),
  }) : '';
  const files = tab.changesCounts?.files.length || 0;
  tab.changesBtn.textContent = files ? `${t('view.changes')} · ${files}` : t('view.changes');
  tab.histBtn.classList.toggle('on', !showTerm && !showChanges);
  tab.termBtn.classList.toggle('on', showTerm);
  tab.changesBtn.classList.toggle('on', showChanges);
  tab.termBtn.disabled = !row;
  tab.termBtn.title = row ? '' : t('view.resumeFirst');
  tab.resume.hidden = live;
  tab.stop.hidden = !live;
  tab.refresh.hidden = showTerm;
  tab.attach.hidden = !(showTerm && live);
  tab.widthCtl.hidden = showTerm || showChanges;
  tab.hist.hidden = showTerm || showChanges;
  tab.changesPane.hidden = !showChanges;
  tab.termWrap.hidden = !showTerm;
}

function paint() {
  renderTabs();
  paintSidebar();
  for (const tab of state.tabs) paintView(tab);
  $('#empty').hidden = state.tabs.length > 0;
  const today = $('#cost-today');
  today.hidden = !state.costToday;
  if (state.costToday) {
    today.textContent = t('usage.today', { cost: money(state.costToday) });
    today.title = t('usage.todayHint');
  }
  const waiting = state.attention.size;
  document.title = waiting ? `(${waiting}) CLIDA` : 'CLIDA';
}

// ---- history ------------------------------------------------------------------------------

async function loadHistory(tab, { quiet = false } = {}) {
  const sid = tabSession(tab);
  const box = tab.hist;
  // A background refresh would pull a note being written out from under the cursor; catch up later.
  if (quiet && tab.histInner.querySelector('.note-editor')) {
    tab.stale = true;
    return;
  }
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  if (!quiet) tab.histInner.replaceChildren(el('div', 'loading', t('history.loading')));
  let data;
  try {
    [data] = await Promise.all([api('GET', `/api/sessions/${sid}/messages`), loadNotes(tab, { render: false })]);
  } catch (e) {
    tab.histInner.replaceChildren(el('div', 'empty-note', e.message));
    return;
  }
  tab.items = data.items;
  tab.truncated = data.truncated;
  tab.loaded = true;
  tab.stale = false;
  if (quiet && historySignature(tab) === tab.shownSignature) return;  // nothing new: leave it be
  renderHistory(tab, { keepPlace: quiet && !atBottom });
  if (!quiet || atBottom) box.scrollTop = box.scrollHeight;
}

const historySignature = (tab) => JSON.stringify([language(), tab.showAll, tab.truncated, tab.items, tab.notes]);

// Where the reader is: the first message in view, and the steps and tools they unfolded.
function historyPlace(tab) {
  const top = tab.hist.getBoundingClientRect().top;
  const anchor = [...tab.histInner.querySelectorAll(':scope > [data-index]')].find((node) => node.getBoundingClientRect().bottom > top);
  return {
    open: new Set([...tab.histInner.querySelectorAll('details[open][data-key]')].map((node) => node.dataset.key)),
    index: anchor?.dataset.index,
    offset: anchor ? anchor.getBoundingClientRect().top - top : 0,
  };
}

function restorePlace(tab, place, scroll) {
  for (const node of tab.histInner.querySelectorAll('details[data-key]')) {
    if (!place.open.has(node.dataset.key)) continue;
    node.open = true;
    node.fill?.();  // now, not in the later toggle event, so the scroll below sees the final height
  }
  const anchor = scroll && place.index !== undefined && tab.histInner.querySelector(`:scope > [data-index="${place.index}"]`);
  if (anchor) tab.hist.scrollTop += anchor.getBoundingClientRect().top - tab.hist.getBoundingClientRect().top - place.offset;
}

// keepPlace: the first message in view stays where it is, even when older ones drop out of the window.
function renderHistory(tab, { keepPlace = false } = {}) {
  const place = historyPlace(tab);
  const items = tab.items;
  const start = tab.showAll ? 0 : Math.max(0, items.length - HISTORY_WINDOW);
  const nodes = [];
  if (start > 0) {
    const more = el('button', 'btn more', t('history.more', { n: start }));
    more.onclick = () => {
      const fromBottom = tab.hist.scrollHeight - tab.hist.scrollTop;
      tab.showAll = true;
      renderHistory(tab);
      tab.hist.scrollTop = tab.hist.scrollHeight - fromBottom;
    };
    nodes.push(more);
  } else if (tab.truncated) {
    nodes.push(el('div', 'note', t('history.truncated')));
  }
  if (!items.length) {
    const live = state.terminals.has(tab.id);
    nodes.push(el('div', 'empty-note', t(live ? 'history.emptyLive' : 'history.empty')));
  }
  let steps = null;
  for (let i = start; i < items.length; i++) {
    const item = items[i];
    if (item.k === 'tool' || item.k === 'thinking') {
      if (!steps) {
        steps = stepsGroup(i);
        nodes.push(steps.root);
      }
      steps.add(item, i);
      continue;
    }
    steps = null;
    const [node, ...cards] = withNotes(tab, item);
    node.dataset.index = String(i);
    nodes.push(node, ...cards);
  }
  // Notes whose message is no longer in the transcript still deserve a place.
  const shown = new Set(items.map((item) => item.uid));
  const orphans = tab.notes.messages.filter((note) => !shown.has(note.anchor));
  if (orphans.length && items.length) {
    nodes.push(el('div', 'divider', t('note.orphans')));
    for (const note of orphans) nodes.push(noteCard(tab, note, true));
  }
  // Open note editors keep their unsaved text: they go back next to their message or note.
  const editors = [...tab.histInner.querySelectorAll('.note-editor')];
  const focused = editors.some((editor) => editor.contains(document.activeElement)) ? document.activeElement : null;
  tab.histInner.replaceChildren(...nodes);
  for (const editor of editors) {
    const { note, anchor } = editor.dataset;
    const spot = note
      ? tab.histInner.querySelector(`.note-card[data-note="${CSS.escape(note)}"]`)
      : tab.histInner.querySelector(`.msg-wrap[data-uid="${CSS.escape(anchor)}"]`);
    if (note) spot?.replaceWith(editor);  // no card: the note was deleted
    else spot?.after(editor);
  }
  focused?.focus({ preventScroll: true });
  restorePlace(tab, place, keepPlace);
  tab.shownSignature = historySignature(tab);
}

// ---- notes --------------------------------------------------------------------------------
// Private notes on a session and on single messages. They live in CLIDA's own store and are never
// typed into a terminal or written to a transcript, so neither the CLI nor the model sees them.

const NOTE_MAX = 2000;

async function loadNotes(tab, { render = true } = {}) {
  try {
    tab.notes = await api('GET', `/api/sessions/${tabSession(tab)}/notes`);
  } catch {
    return;  // no notes, or the server predates them: the view simply shows none
  }
  if (!tab.sessionNote.querySelector('.note-editor')) renderSessionNote(tab);  // keep a note being written
  if (render && tab.loaded) rerenderHistory(tab);
}

// Re-render the history without losing the reader's place in it.
function rerenderHistory(tab) {
  renderHistory(tab, { keepPlace: true });
}

// Paste rendered chat output as markdown instead of flat text (see paste.js).
function pasteAsMarkdown(ev) {
  const html = ev.clipboardData?.getData('text/html');
  const markdown = html && htmlToMarkdown(html);
  if (!markdown) return;
  ev.preventDefault();
  const area = ev.target;
  area.setRangeText(markdown, area.selectionStart, area.selectionEnd, 'end');
  area.dispatchEvent(new Event('input', { bubbles: true }));
}

// flush(text): save the text as it stands, without touching the page; used before a reload
// (see reloadSafely). It skips empty text, so a cleared editor never deletes a stored note.
function noteEditor({ initial = '', onSave, onCancel, onDelete, flush }) {
  const box = el('div', 'note-editor');
  const area = el('textarea');
  box.flush = () => {
    const text = area.value.trim();
    return flush && text && text !== initial.trim() ? flush(text) : null;
  };
  area.maxLength = NOTE_MAX;
  area.value = initial;
  area.rows = initial ? 6 : 4;
  area.placeholder = t('note.placeholder');
  area.addEventListener('paste', pasteAsMarkdown);
  const actions = el('div', 'note-actions');
  actions.append(el('span', 'note-hint', t('note.keys', { mod: MAC ? '⌘' : t('key.ctrl') })));
  if (onDelete) {
    const del = el('button', 'btn danger', t('delete'));
    del.onclick = onDelete;
    actions.append(del);
  }
  const cancel = el('button', 'btn', t('cancel'));
  const save = el('button', 'btn primary', t('save'));
  cancel.onclick = onCancel;
  save.onclick = () => onSave(area.value.trim());
  actions.append(cancel, save);
  area.onkeydown = (ev) => {
    ev.stopPropagation();
    if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      onSave(area.value.trim());
    } else if (ev.key === 'Escape') {
      ev.preventDefault();
      onCancel();
    }
  };
  box.append(area, actions);
  requestAnimationFrame(() => area.focus());
  return box;
}

function renderSessionNote(tab) {
  const bar = tab.sessionNote;
  const note = tab.notes.session;
  bar.hidden = !note;
  if (!note) {
    bar.replaceChildren();  // also the editor that just closed, or the note button would find it
    return;
  }
  const body = el('div', 'md');
  renderMarkdown(body, note.body);
  bar.replaceChildren(icon('note'), body);
  bar.title = t('note.clickToEdit');
  bar.onclick = (ev) => { if (!ev.target.closest('a, button')) editSessionNote(tab); };
}

function editSessionNote(tab) {
  const bar = tab.sessionNote;
  if (bar.querySelector('.note-editor')) return;
  const save = async (body) => {
    try {
      const res = await change('PUT', `/api/sessions/${tabSession(tab)}/notes/session`, { body });
      tab.notes.session = res.session;
    } catch (e) {
      toast(e.message);
      return;
    }
    renderSessionNote(tab);
  };
  bar.onclick = null;
  bar.hidden = false;
  bar.title = '';
  bar.replaceChildren(noteEditor({
    initial: tab.notes.session?.body || '',
    onSave: save,
    onCancel: () => renderSessionNote(tab),
    onDelete: tab.notes.session ? () => save('') : null,
    flush: (body) => api('PUT', `/api/sessions/${tabSession(tab)}/notes/session`, { body }),
  }));
}

// A user or assistant message, with its add-note button and the notes anchored to it.
function withNotes(tab, item) {
  const node = renderItem(item);
  if (!item.uid || (item.k !== 'user' && item.k !== 'assistant')) return [node];
  const wrap = el('div', `msg-wrap ${item.k}`);
  wrap.dataset.uid = item.uid;
  const add = el('button', 'icon-btn note-add');
  add.title = t('note.message');
  add.append(icon('note'));
  add.onclick = () => {
    if (wrap.nextElementSibling?.classList.contains('note-editor')) return;
    const editor = noteEditor({
      onSave: async (body) => {
        if (!body) {
          editor.remove();
          return;
        }
        try {
          const note = await change('POST', `/api/sessions/${tabSession(tab)}/notes`, {
            anchor: item.uid, role: item.k, preview: item.text.slice(0, 300), body,
          });
          tab.notes.messages.push(note);
        } catch (e) {
          toast(e.message);
          return;
        }
        editor.remove();  // done; other open editors stay
        rerenderHistory(tab);
      },
      onCancel: () => editor.remove(),
      flush: (body) => api('POST', `/api/sessions/${tabSession(tab)}/notes`, {
        anchor: item.uid, role: item.k, preview: item.text.slice(0, 300), body,
      }),
    });
    editor.dataset.anchor = item.uid;
    wrap.after(editor);
  };
  wrap.append(node, add);
  const cards = tab.notes.messages.filter((note) => note.anchor === item.uid).map((note) => noteCard(tab, note));
  return [wrap, ...cards];
}

function noteCard(tab, note, withPreview = false) {
  const card = el('div', 'note-card');
  card.dataset.note = note.id;
  const head = el('div', 'note-head');
  head.append(icon('note'), el('span', '', t('note')), el('span', 'note-time', timeLabel(note.updated)));
  const edit = el('button', 'icon-btn');
  edit.title = t('edit');
  edit.append(icon('pencil'));
  head.append(edit);
  const body = el('div', 'md note-body');
  renderMarkdown(body, note.body);
  if (withPreview && note.preview) card.append(el('div', 'note-preview', quote(note.preview)));
  card.append(head, body);
  const remove = async () => {
    if (!(await ask({ title: t('note.deleteTitle'), text: t('note.deleteText'), yes: t('delete'), danger: true }))) return;
    try {
      await change('DELETE', `/api/sessions/${tabSession(tab)}/notes/${note.id}`);
    } catch (e) {
      toast(e.message);
      return;
    }
    tab.notes.messages = tab.notes.messages.filter((n) => n.id !== note.id);
    rerenderHistory(tab);
  };
  edit.onclick = () => {
    const editor = noteEditor({
      initial: note.body,
      onSave: async (text) => {
        if (!text) {
          remove();
          return;
        }
        try {
          Object.assign(note, await change('PUT', `/api/sessions/${tabSession(tab)}/notes/${note.id}`, { body: text }));
        } catch (e) {
          toast(e.message);
          return;
        }
        editor.remove();
        rerenderHistory(tab);
      },
      onCancel: () => {
        editor.remove();
        rerenderHistory(tab);
      },
      onDelete: remove,
      flush: (text) => api('PUT', `/api/sessions/${tabSession(tab)}/notes/${note.id}`, { body: text }),
    });
    editor.dataset.note = note.id;
    card.replaceWith(editor);
  };
  return card;
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
      renderMarkdown(node, item.text);
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

// index: the first item's place in the history, a key that stays the same across re-renders.
function stepsGroup(index) {
  const root = el('details', 'steps');
  root.dataset.index = String(index);
  root.dataset.key = `s${index}`;
  const summary = el('summary');
  const body = el('div', 'steps-body');
  root.append(summary, body);
  const names = [];
  let tools = 0;
  let errors = 0;
  let thoughts = 0;
  return {
    root,
    add(item, i) {
      body.append(renderStep(item, i));
      if (item.k === 'tool') {
        tools += 1;
        if (!names.includes(item.name)) names.push(item.name);
        if (item.error) errors += 1;
      } else {
        thoughts += 1;
      }
      const label = tools
        ? `${t('steps', { n: tools })} · ${names.slice(0, 4).join(', ')}${names.length > 4 ? ' …' : ''}`
        : t('thinking');
      summary.replaceChildren(el('span', '', label));
      if (errors) summary.append(el('span', 'badge', t('errors', { n: errors })));
    },
  };
}

function renderStep(item, index) {
  if (item.k === 'thinking') {
    const node = el('div', 'thinking md');
    renderMarkdown(node, item.text);
    return node;
  }
  const node = el('details', 'tool');
  node.dataset.key = `t${index}`;
  const summary = el('summary');
  summary.append(el('span', 'tool-name', item.name), el('span', 'tool-sum', item.summary));
  if (item.error) summary.append(el('span', 'badge', t('error')));
  node.append(summary);
  node.fill = () => {  // on first open; also called directly when a re-render opens it again
    if (node.dataset.filled) return;
    node.dataset.filled = '1';
    if (item.input && item.input !== item.summary) node.append(toolInput(item));
    if (item.result) node.append(el('pre', '', item.result));
  };
  node.addEventListener('toggle', () => { if (node.open) node.fill(); });
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

// ---- changes ------------------------------------------------------------------------------
// What the chat changed, laid out like a GitLab merge request: the changed files on the left (as
// a tree or a list, with a search), their diffs on the right. Click a line number to comment on a
// line, Shift+click to take a range. "Send to Claude" types all comments into this chat's own
// session as one prompt, resuming it first if it is not running.

const DIFF_COLLAPSE_ROWS = 800;  // a diff with more rows starts collapsed
const SCROLL_ANCHORING = CSS.supports('overflow-anchor', 'auto');
// A step's line height and its extra height (heading, margins, padding), measured once.
let stepPx = null;
function stepSizes() {
  if (!stepPx) {
    const probe = el('div', 'mr-file');
    probe.style.cssText = 'position:absolute;visibility:hidden;left:-9999px;width:600px';
    const measure = (lines) => {
      const step = stepBlock({ tool: 'Edit', ts: null, lines: Array(lines).fill('x'), replaced: false });
      probe.replaceChildren(step);
      return step.getBoundingClientRect().height;
    };
    document.body.append(probe);
    const one = measure(1);
    const eleven = measure(11);
    probe.remove();
    stepPx = { line: (eleven - one) / 10 || 15, extra: one - (eleven - one) / 10 || 40 };
  }
  return stepPx;
}

// The height of one diff row as the stylesheet draws it, measured once.
let diffRowPx = 0;
function rowHeight() {
  if (!diffRowPx) {
    const probe = el('div', 'net-diff');
    probe.style.cssText = 'position:absolute;visibility:hidden;left:-9999px';
    const row = el('div', 'dl');
    row.append(el('span', 'code', 'x'));
    probe.append(row);
    document.body.append(probe);
    diffRowPx = row.getBoundingClientRect().height || 19;
    probe.remove();
  }
  return diffRowPx;
}
const PROMPT_CODE_LINES = 60;    // code lines quoted per comment in the prompt

// Without the diffs unless the view is shown: the other tabs only need the counts, and showing
// the view loads them in full (showView).
async function loadChanges(tab) {
  const seq = tab.changesSeq = (tab.changesSeq || 0) + 1;
  const brief = tab.view !== 'changes';
  let data;
  try {
    data = await api('GET', `/api/sessions/${tabSession(tab)}/changes${brief ? '?brief=1' : ''}`);
  } catch (e) {
    if (seq === tab.changesSeq && !brief) tab.changesInner.replaceChildren(el('div', 'empty-note', e.message));
    return;
  }
  if (seq !== tab.changesSeq) return;  // a newer load went out meanwhile
  // The header and the switch take the latest counts from either kind of load; the view is only
  // ever drawn from a full one, which has the diffs and where each file stands in git.
  tab.changesCounts = data;
  if (!brief) {
    tab.changes = data;
    const signature = JSON.stringify([language(), data]);
    // A comment being written stays: the view catches up once it is saved or dropped.
    if (tab.changesInner.querySelector('.cform') || tab.mrDragging) tab.changesStale ||= signature !== tab.changesSignature;
    else if (signature !== tab.changesSignature) renderChanges(tab);  // unchanged: keep scroll and open files
    tab.changesSignature = signature;
  }
  paintView(tab);
}

const reviewKey = (tab) => `review.${tabSession(tab)}`;
const reviewOf = (tab) => (tab.review ||= store.get(reviewKey(tab), []));
const saveReview = (tab) => store.set(reviewKey(tab), tab.review);

function renderChanges(tab) {
  tab.changesStale = false;
  const { files } = tab.changes;
  // Back to the same file and place after the redraw: the diffs above have only estimated
  // heights until drawn, so the same scroll offset could be in another file.
  const keep = { anchor: viewAnchor(tab), main: tab.mrMain?.scrollTop || 0, side: tab.mrList?.scrollTop || 0 };
  tab.mrObserver?.disconnect();
  tab.collapsed ||= new Set(files.filter((f) => (f.net?.length || 0) > DIFF_COLLAPSE_ROWS).map((f) => f.path));
  const layout = el('div', 'mr');
  const side = el('aside', 'mr-files');
  const column = el('div', 'mr-col');  // the review bar stays on top, the diffs scroll under it
  const main = el('div', 'mr-main');
  tab.mrMain = main;
  // Comment boxes sit in rows as wide as the longest code line; they take the width in view.
  tab.mrResize?.disconnect();
  tab.mrResize = new ResizeObserver(() => main.style.setProperty('--mr-width', `${main.clientWidth}px`));
  tab.mrResize.observe(main);

  const head = el('div', 'mr-files-head');
  const title = el('div', 'mr-files-title');
  title.append(el('strong', '', t('changes.filesTitle')), el('span', 'count-badge', String(files.length)));
  const modes = el('div', 'mr-modes');
  for (const mode of ['list', 'tree']) {
    const button = el('button', `icon-btn${(store.get('changesTree', true) ? 'tree' : 'list') === mode ? ' on' : ''}`);
    button.title = t(`changes.${mode}`);
    button.append(icon(mode === 'tree' ? 'tree' : 'list'));
    button.onclick = () => {
      store.set('changesTree', mode === 'tree');
      // The diffs take the list's order too, but not over a comment being written: they follow
      // once it is saved or dropped, as after a refresh.
      if (tab.changesInner.querySelector('.cform')) {
        for (const other of modes.children) other.classList.toggle('on', other === button);
        tab.changesStale = true;
        renderFileList(tab);
      } else {
        renderChanges(tab);
      }
    };
    modes.append(button);
  }
  head.append(title, modes);
  const search = el('label', 'search mr-search');
  const query = el('input');
  query.type = 'search';
  query.placeholder = t('changes.search');
  query.value = tab.fileQuery || '';
  query.autocomplete = 'off';
  query.spellcheck = false;
  query.oninput = () => {
    tab.fileQuery = query.value;
    renderFileList(tab);
  };
  const glass = el('span');
  glass.append(icon('search'));
  search.append(glass, query);
  tab.mrQuery = query;
  const list = el('div', 'mr-tree');
  tab.mrList = list;
  side.append(head, search, list);

  main.append(changesTop(tab));
  tab.mrReview = el('div', 'mr-review');
  renderReviewBar(tab);
  if (!files.length) main.append(el('div', 'empty-note', t('changes.none')));
  // Diffs are drawn when they come near the screen: a chat can change hundreds of files.
  tab.mrObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) entry.target.fill?.();
  }, { root: main, rootMargin: '600px 0px' });
  tab.mrBlocks = new Map();
  // In the order of the file list: repository by repository, files outside any last, and in each
  // the tree's order (folders before the files next to them) or, as a list, by path.
  const byPath = pathCompare();
  const ordered = [...files].sort((a, b) => (!a.repo) - (!b.repo) || (a.repo?.top || '').localeCompare(b.repo?.top || '')
    || byPath(groupPath(a), groupPath(b)));
  for (const file of ordered) {
    const block = fileBlock(tab, file);
    tab.mrBlocks.set(file.path, block);
    main.append(block);
    tab.mrObserver.observe(block);
  }
  column.append(tab.mrReview, main);
  layout.append(side, column);
  tab.changesInner.replaceChildren(layout);
  renderFileList(tab);
  const anchored = keep.anchor && tab.mrBlocks.get(keep.anchor.path);
  if (anchored) {
    anchored.fill();
    main.scrollTop = anchored.offsetTop - main.offsetTop + keep.anchor.offset;
  } else {
    main.scrollTop = keep.main;
  }
  list.scrollTop = keep.side;
}

// The file at the top of the view and how far into it the view is.
function viewAnchor(tab) {
  if (!tab.mrMain || !tab.mrBlocks || !tab.mrMain.scrollTop) return null;
  const top = tab.mrMain.getBoundingClientRect().top;
  for (const [path, block] of tab.mrBlocks) {
    const rect = block.getBoundingClientRect();
    if (rect.bottom > top) return { path, offset: top - rect.top };
  }
  return null;
}

function changesTop(tab) {
  const { files, git, commits = [] } = tab.changes;
  const top = el('div', 'mr-top');
  const line = el('div', 'changes-sum');
  if (git) {
    const where = el('span', 'changes-branch');
    where.append(icon('branch'), git.branch || t('changes.detached'));
    line.append(where, el('span', 'muted', t('changes.dirty', { n: git.dirty })));
  }
  for (const status of ['added', 'modified', 'deleted']) {
    const n = files.filter((f) => f.status === status).length;
    if (n) line.append(el('span', `status-text ${status}`, t(`changes.n.${status}`, { n })));
  }
  const added = files.reduce((n, f) => n + (f.added || 0), 0);
  const removed = files.reduce((n, f) => n + (f.removed || 0), 0);
  if (added || removed) line.append(el('span', 'diff-add', `+${added}`), el('span', 'diff-del', `−${removed}`));
  // Will it be committed? Counted by where each file stands in git now.
  const pending = files.filter((f) => ['staged', 'unstaged', 'partly', 'untracked'].includes(f.state)).length;
  const kinds = [['committed', files.filter((f) => f.state === 'committed').length], ['pending', pending],
    ['ignored', files.filter((f) => f.state === 'ignored').length], ['outside', files.filter((f) => !f.repo).length]];
  for (const [kind, n] of kinds) if (n) line.append(el('span', `git-count ${kind}`, t(`git.n.${kind}`, { n })));
  const hint = el('span', 'mr-hint', 'ⓘ');
  hint.title = t('changes.hint');
  line.append(hint);
  top.append(line);
  if (commits.length) top.append(commitList(tab, commits));
  return top;
}

// ---- file list: tree or list, filtered by the search -------------------------------------

// A search like GitLab's: *.vue or src/**/x.js as a pattern, anything else as part of the path.
function fileMatcher(query) {
  const q = query.trim().toLowerCase();
  if (!q) return () => true;
  if (!/[*?]/.test(q)) return (path) => path.toLowerCase().includes(q);
  const pattern = q.split('**').map((part) => part.split('*').map((s) => s.split('?')
    .map((x) => x.replace(/[.+^${}()|[\]\\]/g, '\\$&')).join('[^/]')).join('[^/]*')).join('.*');
  const re = new RegExp(`(^|/)${pattern}$`);
  return (path) => re.test(path.toLowerCase());
}

// A file's path in its group: inside its repository, or as labelled outside of one.
const groupPath = (file) => (file.repo ? file.rel : file.label);

// One group per repository (with its branch), and one for files outside any: what can be
// committed where, and what never will be.
function renderFileList(tab) {
  const match = fileMatcher(tab.fileQuery || '');
  const files = tab.changes.files.filter((f) => match(groupPath(f)) || match(f.label));
  const list = tab.mrList;
  if (!files.length) {
    list.replaceChildren(el('div', 'mr-none', t(tab.changes.files.length ? 'changes.noMatch' : 'changes.none')));
    return;
  }
  const groups = new Map();
  for (const file of files) {
    const key = file.repo ? file.repo.top : '';
    if (!groups.has(key)) groups.set(key, { repo: file.repo, files: [] });
    groups.get(key).files.push(file);
  }
  const rows = [];
  const byPath = pathCompare();
  for (const [key, group] of [...groups].sort(([a], [b]) => (!a) - (!b) || a.localeCompare(b))) {
    const head = el('div', `mr-group${group.repo ? '' : ' outside'}`);
    if (group.repo) {
      head.append(icon('branch'), el('strong', '', group.repo.name), el('span', 'muted', group.repo.branch || t('changes.detached')));
      head.title = group.repo.top;
    } else {
      head.append(el('strong', '', t('git.outside')));
      head.title = t('git.outsideHint');
    }
    rows.push(head);
    rows.push(...(store.get('changesTree', true) ? treeRows(tab, group.files)
      : [...group.files].sort((a, b) => byPath(groupPath(a), groupPath(b))).map((file) => fileRow(tab, file, groupPath(file), 0))));
  }
  list.replaceChildren(...rows);
}

// The order of the file list, which the diffs follow: the tree's, or by path as a list.
const pathCompare = () => (store.get('changesTree', true) ? treeCompare : (a, b) => a.localeCompare(b));

// The tree's order for two paths: by folder, a folder before the files beside it.
function treeCompare(a, b) {
  const x = a.split('/');
  const y = b.split('/');
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    if (x[i] === y[i]) continue;
    const xFile = i === x.length - 1;
    const yFile = i === y.length - 1;
    return xFile !== yFile ? (xFile ? 1 : -1) : x[i].localeCompare(y[i]);
  }
  return x.length - y.length;
}

// Folders with a single folder in them and no files are one row, as in GitLab: group/project.
function treeRows(tab, files) {
  const root = { dirs: new Map(), files: [] };
  for (const file of files) {
    const parts = groupPath(file).split('/');
    let node = root;
    for (const part of parts.slice(0, -1)) {
      if (!node.dirs.has(part)) node.dirs.set(part, { dirs: new Map(), files: [] });
      node = node.dirs.get(part);
    }
    node.files.push(file);
  }
  const rows = [];
  const walk = (node, depth) => {
    for (let [name, dir] of [...node.dirs].sort(([a], [b]) => a.localeCompare(b))) {
      while (dir.dirs.size === 1 && !dir.files.length) {
        const [[inner, next]] = dir.dirs;
        name = `${name}/${inner}`;
        dir = next;
      }
      const row = el('div', 'mr-row dir');
      row.style.setProperty('--depth', depth);
      row.append(icon('folder'), el('span', 'mr-dirname', name));
      rows.push(row);
      walk(dir, depth + 1);
    }
    for (const file of node.files.sort((a, b) => groupPath(a).localeCompare(groupPath(b)))) {
      rows.push(fileRow(tab, file, groupPath(file).split('/').pop(), depth));
    }
  };
  walk(root, 0);
  return rows;
}

function fileRow(tab, file, name, depth) {
  const row = el('div', `mr-row file ${file.status}`);
  row.style.setProperty('--depth', depth);
  row.title = file.path;
  row.tabIndex = 0;
  row.append(icon('file'), middleEllipsis(name));
  if (file.added != null && (file.added || file.removed)) {
    row.append(el('span', 'diff-add', `+${file.added}`), el('span', 'diff-del', `-${file.removed}`));
  }
  row.append(gitMark(file), statusIcon(file.status));
  const go = () => {
    const block = tab.mrBlocks.get(file.path);
    if (!block) return;
    if (tab.collapsed.delete(file.path)) block.setCollapsed(false);
    tab.mrMain.scrollTop = block.offsetTop - tab.mrMain.offsetTop;
    block.fill();  // it is in view now; not left to the observer's next round
  };
  row.onclick = go;
  row.onkeydown = (ev) => { if (ev.key === 'Enter') go(); };
  return row;
}

// Long names keep their end in view: "DeliveryQuant…tyHelper.php", as in GitLab.
function middleEllipsis(name) {
  const box = el('span', 'mid');
  const cut = name.length > 16 ? name.length - 12 : name.length;
  box.append(el('span', 'mid-a', name.slice(0, cut)), el('span', 'mid-b', name.slice(cut)));
  return box;
}

// Where a file stands in git, for "will it be committed?": a small mark in the file list ...
const GIT_MARKS = { committed: '✓', staged: '+', partly: '±', unstaged: '●', untracked: '?', ignored: '⊘', unknown: '…' };

function gitState(file) {
  return file.repo ? file.state : 'outside';
}

function gitText(file) {
  const state = gitState(file);
  return state === 'committed' && file.commit
    ? t('git.committedIn', { sha: file.commit.sha.slice(0, 7) })
    : t(`git.${state}`);
}

function gitMark(file) {
  const state = gitState(file);
  const mark = el('span', `git-mark ${state}`, GIT_MARKS[state] || '');
  mark.title = [gitText(file), file.commit?.subject].filter(Boolean).join(' · ');
  return mark;
}

// ... and in words above its diff.
function gitChip(file) {
  const state = gitState(file);
  const chip = el('span', `git-chip ${state}`, gitText(file));
  chip.title = state === 'outside' ? t('git.outsideHint') : [file.repo.name, file.commit?.subject].filter(Boolean).join(' · ');
  return chip;
}

const STATUS_ICONS = {
  added: '<path d="M12 8.5v7M8.5 12h7"/>',
  modified: '<circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/>',
  deleted: '<path d="M8.5 12h7"/>',
};

function statusIcon(status) {
  const box = el('span', `status-icon ${status}`);
  box.title = t(`changes.status.${status}`);
  const inner = STATUS_ICONS[status === 'gone' ? 'deleted' : status] || '';
  box.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="3"/>${inner}</svg>`;
  return box;
}

// The commits made while the chat ran, newest first, like the commits tab of a merge request.
function commitList(tab, commits) {
  const box = el('details', 'change-commits');
  box.open = !!tab.commitsOpen;
  box.addEventListener('toggle', () => { tab.commitsOpen = box.open; });
  box.append(el('summary', '', t('changes.commits', { n: commits.length })));
  const repos = new Set(commits.map((c) => c.repo)).size;
  for (const commit of commits) {
    const row = el('div', 'commit');
    const when = new Date(commit.time * 1000);
    row.append(el('code', 'commit-sha', commit.sha.slice(0, 7)), el('span', 'commit-subject', commit.subject),
      el('span', 'commit-when', [repos > 1 && commit.repo, timeLabel(commit.time)].filter(Boolean).join(' · ')));
    row.title = `${commit.sha} · ${when.toLocaleString(locale())}`;
    box.append(row);
  }
  return box;
}

// ---- diffs --------------------------------------------------------------------------------

function fileBlock(tab, file) {
  const block = el('section', `mr-file ${file.status}`);
  const head = el('header', 'mr-file-head');
  const toggle = el('button', 'icon-btn');
  const path = el('span', 'mr-file-path');
  const slash = file.label.lastIndexOf('/');
  path.append(el('span', 'muted', file.label.slice(0, slash + 1)), el('strong', '', file.label.slice(slash + 1)));
  path.title = file.path;
  head.append(toggle, statusIcon(file.status), path);
  if (file.status === 'gone' || file.status === 'unchanged') head.append(el('span', `status-text ${file.status}`, t(`changes.status.${file.status}`)));
  if (file.source === 'git') {
    const via = el('span', 'change-via', t('changes.viaShell'));
    via.title = t('changes.viaShellHint');
    head.append(via);
  }
  head.append(gitChip(file));
  if (file.added != null && (file.added || file.removed)) {
    head.append(el('span', 'diff-add', `+${file.added}`), el('span', 'diff-del', `−${file.removed}`));
  }
  const body = el('div', 'mr-file-body');
  // Until drawn, a body holds about its height (rows × row height): without it all the empty
  // blocks would fit on screen at once and the observer would draw every one of them.
  const steps = !file.net?.length && !file.known ? file.steps : [];
  const height = (file.net?.length || 0) * rowHeight()
    + steps.reduce((sum, step) => sum + step.lines.length * stepSizes().line + stepSizes().extra, 0);
  body.style.minHeight = `${Math.max(height, 40)}px`;
  block.append(head, body);
  const showCollapsed = (collapsed) => {
    block.classList.toggle('collapsed', collapsed);
    toggle.replaceChildren(icon(collapsed ? 'chevronRight' : 'chevronDown'));
    toggle.title = t(collapsed ? 'changes.expand' : 'changes.collapse');
  };
  block.setCollapsed = (collapsed) => {
    showCollapsed(collapsed);
    if (!collapsed) block.fill();  // opened by hand or by a jump: drawn now, it is in view
  };
  head.onclick = (ev) => {
    if (ev.target.closest('a')) return;
    const collapsed = !block.classList.contains('collapsed');
    if (collapsed) tab.collapsed.add(file.path); else tab.collapsed.delete(file.path);
    block.setCollapsed(collapsed);
  };
  block.fill = () => {
    if (block.dataset.filled || block.classList.contains('collapsed')) return;
    block.dataset.filled = '1';
    // Drawn above the view, the browser keeps the view in place (scroll anchoring); Safari has
    // none, so there the view moves along by as much as the diff grew.
    const main = tab.mrMain;
    // Only a diff wholly above the view: inside one that reaches into it, the reader is in it.
    const above = !SCROLL_ANCHORING && main && block.getBoundingClientRect().bottom <= main.getBoundingClientRect().top + 1;
    const before = block.offsetHeight;
    fillFile(tab, file, body);
    body.style.minHeight = '';
    if (above) main.scrollTop += block.offsetHeight - before;
  };
  showCollapsed(tab.collapsed.has(file.path));  // the diff itself waits for the observer
  return block;
}

function fillFile(tab, file, body) {
  const note = file.note ? t(`changes.note.${file.note}`)
    : !file.known ? t('changes.note.unknown')
      : file.status === 'gone' ? t('changes.note.gone')
        : file.status === 'unchanged' ? t('changes.note.unchanged')
          : !file.net?.length ? t('changes.note.empty') : '';
  const parts = [];
  if (note) parts.push(el('p', 'change-note', note));
  if (file.net?.length) parts.push(diffTable(tab, file));
  else if (!file.known && file.steps.length) parts.push(...file.steps.map(stepBlock));
  body.replaceChildren(...parts);
}

// What one Edit or Write call did; shown only for a file whose state before the chat is not known.
function stepBlock(step) {
  const box = el('div', 'mr-step');
  const when = step.ts ? dates().clock.format(new Date(step.ts)) : '';
  box.append(el('div', 'hunk-head', [step.tool, step.replaced && t('changes.replaced'), when].filter(Boolean).join(' · ')));
  const pre = el('pre', 'diff');
  for (const line of step.lines) {
    const cls = line.startsWith('+') ? 'diff-add' : line.startsWith('-') ? 'diff-del' : line === '⋯' ? 'diff-gap' : '';
    pre.append(el('span', cls, line + '\n'));
  }
  box.append(pre);
  return box;
}

// A row's place for a comment: its line in the new file, or in the old one for a removed line.
const rowAnchor = (row) => (row[2] != null ? { side: 'new', line: row[2] } : { side: 'old', line: row[1] });
const findRow = (rows, anchor) => rows.findIndex((row) => row[0] !== '@'
  && (anchor.side === 'new' ? row[2] === anchor.line : row[2] == null && row[1] === anchor.line));

// The diff with old and new line numbers. Click a number to comment, Shift+click for a range.
function diffTable(tab, file) {
  const rows = file.net;
  const box = el('div', 'net-diff');
  const table = el('div', 'net-rows');
  const digits = String(Math.max(...rows.map((r) => Math.max(r[1] || 0, r[2] || 0)))).length;
  table.style.setProperty('--lnw', `${digits + 1}ch`);
  const nodes = rows.map(([kind, oldNo, newNo, text], i) => {
    const cls = { '+': 'add', '-': 'del', '@': 'hunk' }[kind] || '';
    const row = el('div', `dl ${cls}`);
    if (kind === '@') {
      row.append(el('span', 'code hunk-text', text));
      return row;
    }
    const gutter = el('span', 'ln-pair');
    gutter.append(el('span', 'ln', oldNo ?? ''), el('span', 'ln', newNo ?? ''));
    const add = el('button', 'cbtn');
    add.title = t('review.addHint');
    add.append(icon('comment'));
    gutter.append(add);
    gutter.onpointerdown = (ev) => {
      if (ev.button !== 0) return;
      ev.preventDefault();  // no text selection
      if (ev.shiftKey) selectRows(tab, file, i, true);
      else dragRows(tab, file, i, gutter, ev.pointerId);
    };
    // The mouse's own default (focus to the clicked button) would take the focus from the new box.
    gutter.onmousedown = (ev) => ev.preventDefault();
    row.append(gutter, el('span', 'sign', kind === ' ' ? '' : kind), el('span', 'code', text));
    return row;
  });
  table.append(...nodes);
  // Saved comments under their last line; those whose lines left the diff on top.
  const lost = [];
  for (const comment of reviewOf(tab).filter((c) => c.path === file.path)) {
    const at = findRow(rows, comment.to);
    if (at < 0) lost.push(comment);
    else nodes[at].after(commentCard(tab, file, comment));
  }
  if (lost.length) table.prepend(...lost.map((c) => commentCard(tab, file, c, true)));
  box.append(table);
  file.nodes = nodes;
  return box;
}

// Shift+click: from the line clicked before to this one.
function selectRows(tab, file, index, extend) {
  const prev = tab.mrSelection;
  const start = extend && prev && prev.path === file.path ? prev.start : index;
  selectRange(tab, file, start, index);
}

// Press on a line number and drag over the lines, as in GitLab: the range follows the pointer
// and the comment box opens on release. Near the top or bottom edge the diffs scroll along.
function dragRows(tab, file, start, handle, pointerId) {
  closeCommentForm(tab);
  // Captured: the release arrives even outside the window, so a drag never stays stuck.
  try { handle.setPointerCapture(pointerId); } catch { /* the pointer is already gone */ }
  const main = tab.mrMain;
  let end = start;
  let lastY = null;
  const mark = () => markRows(file, Math.min(start, end), Math.max(start, end));
  const follow = (y) => {
    const row = document.elementFromPoint(main.getBoundingClientRect().left + 30, y)?.closest('.dl');
    const index = row ? file.nodes.indexOf(row) : -1;
    if (index >= 0 && index !== end) {
      end = index;
      mark();
    }
  };
  // While held near an edge, the view keeps scrolling even without moving the pointer.
  const edge = () => {
    if (!tab.mrDragging) return;
    const box = main.getBoundingClientRect();
    if (lastY !== null && (lastY < box.top + 40 || lastY > box.bottom - 40)) {
      main.scrollTop += lastY < box.top + 40 ? -18 : 18;
      follow(Math.min(Math.max(lastY, box.top + 2), box.bottom - 2));
    }
    requestAnimationFrame(edge);
  };
  const move = (ev) => {
    lastY = ev.clientY;
    follow(ev.clientY);
  };
  const up = (ev) => {
    if (!tab.mrDragging) return;
    tab.mrDragging = false;
    document.body.classList.remove('mr-dragging');
    for (const [type, fn] of events) handle.removeEventListener(type, fn);
    if (ev.type === 'pointerup') selectRange(tab, file, start, end);
    else markRows(file, -1, -1);  // cancelled (the capture got lost): no comment box
    if (tab.changesStale) renderChanges(tab);  // a refresh that came during the drag
  };
  const events = [['pointermove', move], ['pointerup', up], ['pointercancel', up], ['lostpointercapture', up]];
  tab.mrDragging = true;
  document.body.classList.add('mr-dragging');  // no text selection on the way
  mark();
  for (const [type, fn] of events) handle.addEventListener(type, fn);
  requestAnimationFrame(edge);
}

function markRows(file, from, to) {
  file.nodes.forEach((node, i) => node.classList.toggle('sel', i >= from && i <= to && file.net[i][0] !== '@'));
}

// Lines from..to (either order) selected, with the comment box under the last of them.
function selectRange(tab, file, start, end) {
  const from = Math.min(start, end);
  const to = Math.max(start, end);
  closeCommentForm(tab);
  tab.mrSelection = { path: file.path, start, from, to };
  markRows(file, from, to);
  const rows = file.net;
  const ends = [rows.slice(from, to + 1).find((r) => r[0] !== '@'), [...rows.slice(from, to + 1)].reverse().find((r) => r[0] !== '@')];
  if (!ends[0]) return;
  const form = commentForm(tab, '', (text) => {
    reviewOf(tab).push({ id: crypto.randomUUID(), path: file.path, label: file.label, from: rowAnchor(ends[0]),
      to: rowAnchor(ends[1]), text, code: codeLines(rows, from, to) });
    saveReview(tab);
    afterReviewChange(tab, file);
  });
  file.nodes[to].after(form);
  const area = form.querySelector('textarea');
  area.focus();
  requestAnimationFrame(() => { if (area.isConnected) area.focus(); });  // after the click's own handling
}

function codeLines(rows, from, to) {
  return rows.slice(from, to + 1).filter((r) => r[0] !== '@').map((r) => `${r[0] === ' ' ? ' ' : r[0]}${r[3]}`);
}

function commentForm(tab, initial, onSave, onCancel = null) {
  const form = el('div', 'cform');
  const area = el('textarea');
  area.value = initial;
  area.rows = 3;
  area.placeholder = t('review.placeholder');
  const actions = el('div', 'cform-actions');
  const cancel = el('button', 'btn', t('cancel'));
  const save = el('button', 'btn primary', t('review.add'));
  const done = (text) => {
    closeCommentForm(tab);
    if (text) onSave(text);
    else if (tab.changesStale) renderChanges(tab);
    else onCancel?.();
  };
  cancel.onclick = () => done('');
  save.onclick = () => done(area.value.trim());
  area.onkeydown = (ev) => {
    if (ev.key === 'Escape') { ev.preventDefault(); done(''); }
    if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); done(area.value.trim()); }
  };
  actions.append(cancel, save);
  form.append(area, actions);
  return form;
}

function closeCommentForm(tab) {
  for (const form of tab.changesInner.querySelectorAll('.cform')) form.remove();
  for (const node of tab.changesInner.querySelectorAll('.dl.sel')) node.classList.remove('sel');
  tab.mrSelection = null;
}

const rangeText = (comment) => {
  const old = comment.from.side === 'old' && comment.to.side === 'old';
  const from = comment.from.line;
  const to = comment.to.line;
  // Removed line 12 and added line 12 (a replaced line) are two rows: "line 12 (before and after)".
  if (from === to && comment.from.side !== comment.to.side) return t('review.lineBoth', { line: from });
  return t('review.lines', { from, to, same: from === to }) + (old ? t('review.oldSide') : '');
};

function commentCard(tab, file, comment, lost = false) {
  const card = el('div', 'ccard');
  const head = el('div', 'ccard-head');
  head.append(icon('comment'), el('span', '', rangeText(comment)));
  const edit = el('button', 'icon-btn');
  edit.title = t('edit');
  edit.append(icon('pencil'));
  const remove = el('button', 'icon-btn');
  remove.title = t('delete');
  remove.append(icon('trash'));
  head.append(edit, remove);
  card.append(head);
  if (lost) card.append(el('div', 'ccard-lost', t('review.lost')));
  card.append(el('div', 'ccard-text', comment.text));
  remove.onclick = () => {
    tab.review = reviewOf(tab).filter((c) => c.id !== comment.id);
    saveReview(tab);
    afterReviewChange(tab, file);
  };
  edit.onclick = () => {
    closeCommentForm(tab);
    const form = commentForm(tab, comment.text, (text) => {
      comment.text = text;
      saveReview(tab);
      afterReviewChange(tab, file);
    }, () => afterReviewChange(tab, file));  // cancelled: the card comes back as it was
    card.replaceWith(form);
    form.querySelector('textarea').focus();
  };
  return card;
}

function afterReviewChange(tab, file) {
  if (tab.changesStale) {
    renderChanges(tab);
    return;
  }
  const block = tab.mrBlocks.get(file.path);
  if (block) fillFile(tab, file, block.querySelector('.mr-file-body'));
  renderReviewBar(tab);
}

// ---- sending the comments to Claude -------------------------------------------------------

function renderReviewBar(tab) {
  const comments = reviewOf(tab);
  const bar = tab.mrReview;
  bar.hidden = !comments.length;
  if (!comments.length) return;
  const send = el('button', 'btn primary', t(tab.mrSending ? 'review.sending' : 'review.send'));
  send.disabled = !!tab.mrSending;
  send.onclick = () => sendReview(tab);
  const discard = el('button', 'btn', t('review.discard'));
  discard.onclick = async () => {
    if (!(await ask({ title: t('review.discardTitle'), text: t('review.discardText', { n: comments.length }), yes: t('review.discard'), danger: true }))) return;
    tab.review = [];
    saveReview(tab);
    renderChanges(tab);
  };
  bar.replaceChildren(el('span', 'mr-review-count', t('review.count', { n: comments.length })), discard, send);
}

function reviewPrompt(tab) {
  const files = new Map(tab.changes.files.map((f) => [f.path, f]));
  const parts = [t('review.intro'), ''];
  reviewOf(tab).forEach((comment, n) => {
    const file = files.get(comment.path);
    const rows = file?.net || [];
    const from = findRow(rows, comment.from);
    const to = findRow(rows, comment.to);
    const code = (from >= 0 && to >= from ? codeLines(rows, from, to) : comment.code).slice(0, PROMPT_CODE_LINES);
    // A path the CLI can open: relative to the chat's folder, else the full one.
    const where = /^[~/]/.test(comment.label) ? comment.path : comment.label;
    parts.push(`${n + 1}. ${where}, ${rangeText(comment)}:`, '```diff', ...code, '```', comment.text, '');
  });
  return parts.join('\n').trim();
}

const sleep = (ms) => new Promise((done) => { setTimeout(done, ms); });

// Into this chat's own session: the running terminal, or the chat resumed (claude --resume, the
// same conversation) once the CLI is ready for input.
async function sendReview(tab) {
  const sid = tabSession(tab);
  // A comment being written is not in the prompt: sending now would drop it without a word.
  const draft = [...tab.changesInner.querySelectorAll('.cform textarea')].find((area) => area.value.trim());
  if (draft) {
    toast(t('review.unsaved'));
    draft.focus();
    return;
  }
  if (state.external.has(sid) && !state.bySession.has(sid)) {
    toast(t('review.external'));
    return;
  }
  tab.mrSending = true;
  renderReviewBar(tab);
  try {
    const text = reviewPrompt(tab);
    if (!state.bySession.has(sid)) await resumeTab(tab);
    let row = state.bySession.get(sid);
    let unreported = 0;  // polls in a row that found the CLI quiet but without its own report
    for (let waited = 0; row && !(row.status === 'idle' && row.reported) && waited < 60000; waited += 500) {
      if (row.status === 'exited') break;
      // A CLI that never reports gets the explanation after a few seconds, not a minute; one that
      // reports late (a resumed one, a session file being rewritten) gets those seconds.
      unreported = row.status === 'idle' && !row.reported ? unreported + 1 : 0;
      if (unreported >= 20) break;  // 10 s
      await sleep(500);
      await refreshStatus();
      row = state.bySession.get(sid);
    }
    if (row && row.status === 'idle' && !row.reported) {
      // Without the CLI's own report, "idle" only means quiet output, as a permission prompt is.
      toast(t('review.noReport'));
      return;
    }
    if (!row || row.status !== 'idle') {
      toast(t('review.notReady'));
      return;
    }
    await api('POST', `/api/terminals/${row.id}/prompt`, { text });
    tab.review = [];
    saveReview(tab);
    // The sent comments' cards go now (one edited before the next load would be lost); the view
    // is drawn afresh when shown again.
    closeCommentForm(tab);  // an edit of a sent comment would go nowhere
    for (const card of tab.changesInner.querySelectorAll('.ccard')) card.remove();
    tab.changesSignature = null;
    setView(tab, 'terminal');
  } catch (e) {
    toast(e.message);
  } finally {
    tab.mrSending = false;
    if (tab.mrReview) renderReviewBar(tab);
  }
}

// F puts the cursor in the file search, as in GitLab, unless something else takes the key.
function changesKey(ev) {
  const tab = activeTab();
  if (ev.key !== 'f' || ev.ctrlKey || ev.altKey || ev.metaKey || !tab || tab.view !== 'changes' || !tab.mrQuery) return;
  if (ev.target.closest?.('input, textarea, select, [contenteditable], .xterm')) return;
  ev.preventDefault();
  tab.mrQuery.focus();
  tab.mrQuery.select();
}

// ---- attachments --------------------------------------------------------------------------
// A browser never tells where a dropped or picked file lives on disk. So these files are copied
// into the session's upload folder (the CLI may read it via --add-dir) and that path is pasted,
// just as a terminal pastes a dragged file's path. Ctrl+V needs none of this: on an empty paste
// the CLI reads the clipboard itself, original paths included. A dropped folder is not copied:
// the server finds it by name and contents (see clida/locate.py), and its real path is pasted.

const UPLOAD_LIMIT = 50 * 1024 * 1024;

function liveTerminalTab() {
  const tab = activeTab();
  const row = tab && state.terminals.get(tab.id);
  return tab && tab.term && tab.view === 'terminal' && row && row.status !== 'exited' ? tab : null;
}

const hasFiles = (ev) => [...(ev.dataTransfer?.types || [])].includes('Files');

// folders: directory entries from a drop (see droppedFiles).
async function attachFiles(tab, files, folders = []) {
  const list = [...files];
  if (!list.length && !folders.length) return;
  if (!tab) {
    toast(t('attach.noSession'));
    return;
  }
  if (list.length) toast(list.length === 1 ? t('attach.one', { name: quote(list[0].name) }) : t('attach.many', { n: list.length }));
  else toast(folders.length === 1 ? t('attach.locating', { name: quote(folders[0].name) }) : t('attach.locatingMany', { n: folders.length }));
  const paths = [];
  for (const file of list) {
    if (file.size > UPLOAD_LIMIT) {
      toast(t('attach.tooLarge', { name: quote(file.name) }));
      continue;
    }
    try {
      const res = await fetch(`/api/terminals/${tab.id}/upload?name=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: file,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(staleServer(res.status, data) ? t('restartNeeded') : data.error || `HTTP ${res.status}`);
      paths.push(data.path);
    } catch (e) {
      toast(t('attach.failed', { name: quote(file.name), error: e.message }));
      return;
    }
  }
  let missing = false;
  for (const folder of folders) {
    try {
      paths.push((await api('POST', '/api/locate-folder', { name: folder.name, entries: await folderNames(folder) })).path);
    } catch (e) {
      toast(e.message);  // the others still come through
      missing = true;
    }
  }
  if (!paths.length) return;
  if (!missing) $('#toast').hidden = true;
  tab.term.paste(paths.map(pastedPath).join(' '));  // a bracketed paste, so the CLI turns image paths into [Image #n]
  tab.term.focus();
}

// A path with spaces in quotes, as a terminal pastes a dragged one; the CLI splits pasted paths at spaces.
const pastedPath = (path) => (/[\s"'\\]/.test(path) ? `"${path.replace(/(["\\$`])/g, '\\$1')}"` : path);

// The names in a dropped folder, so the server can tell it from other folders of the same name.
async function folderNames(folder) {
  const reader = folder.createReader();
  const names = [];
  for (;;) {  // readEntries gives at most 100 at a time
    const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject)).catch(() => []);
    if (!batch.length || names.length >= 1000) break;
    names.push(...batch.map((entry) => entry.name));
  }
  return names.slice(0, 1000);
}

// What was dropped: files, and folders as directory entries. Read during the drop event: after it,
// the browser no longer hands them out.
function droppedFiles(ev) {
  const files = [];
  const folders = [];
  for (const item of ev.dataTransfer.items) {
    if (item.kind !== 'file') continue;
    const entry = item.webkitGetAsEntry?.();
    if (entry?.isDirectory) {
      folders.push(entry);
      continue;
    }
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  return { files, folders };
}

function showDropHint(on) {
  const hint = $('#drop-hint');
  hint.hidden = !on;
  if (on) hint.textContent = t(liveTerminalTab() ? 'attach.drop' : 'attach.dropNoSession');
}

// ---- terminals ----------------------------------------------------------------------------

function ensureTerminal(tab) {
  if (tab.term) {
    if (!tab.ws) connect(tab);
    return;
  }
  const term = new Terminal({
    fontFamily: MONO,
    fontSize: 14,
    lineHeight: 1.15,
    cursorBlink: true,
    scrollback: 10000,
    theme: terminalTheme(),
    allowProposedApi: true,
    linkHandler: { activate: (ev, uri) => openTerminalLink(uri) },
  });
  const fit = new FitAddon();
  term.loadAddon(fit);
  term.loadAddon(new WebLinksAddon((ev, uri) => openExternal(uri)));
  term.open(tab.termHost);
  term.attachCustomKeyEventHandler((ev) => terminalKey(tab, ev));
  term.onData((data) => send(tab, { t: 'i', d: data }));
  term.onResize(({ cols, rows }) => send(tab, { t: 'r', c: cols, r: rows }));
  tab.term = term;
  tab.fit = fit;
  connect(tab);
}

// A link printed with its own text (OSC 8): the text need not match the address, so show it first.
// Without this handler xterm asks with the browser's confirm().
async function openTerminalLink(uri) {
  if (!/^https?:/i.test(uri)) return;
  if (await ask({ title: t('link.title'), text: el('code', '', uri), yes: t('link.open') })) openExternal(uri);
}

// Links go to the system's default browser through the server: opened from this page, they would
// land in the browser that runs the app window (Edge, say), whatever the default is.
async function openExternal(url) {
  try {
    await api('POST', '/api/open-url', { url });
  } catch (e) {
    if (e.status === 404) window.open(url, '_blank', 'noopener');  // a server from before this: open here
    else toast(e.message);
  }
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
      // 129 = the CLI's answer to our SIGHUP from "Stop", not an error.
      const clean = msg.code === 0 || msg.code === 129;
      showOverlay(tab, clean ? 'terminal.ended' : 'terminal.endedCode', { code: msg.code });
      refreshStatus();
    }
  };
  ws.onclose = () => {
    if (tab.ws !== ws) return;
    tab.ws = null;
    if (tab.exited || !state.tabs.includes(tab) || !tab.term) return;
    showOverlay(tab, 'terminal.reconnecting');
    tab.retries = (tab.retries || 0) + 1;
    setTimeout(() => {
      if (tab.term && state.tabs.includes(tab) && state.terminals.has(tab.id)) connect(tab);
    }, Math.min(5000, 300 * 2 ** tab.retries));
  };
}

function showOverlay(tab, key, params = {}) {
  tab.overlayText = [key, params];
  const resume = el('button', 'btn primary', t('resume'));
  resume.onclick = () => resumeTab(tab);
  tab.overlay.replaceChildren(el('span', '', t(key, params)));
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
  // On a Mac, Cmd+C / Cmd+V copy and paste natively, and Ctrl+C / Ctrl+V go to the CLI.
  if (MAC) return true;
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
      if (state.terminals.get(tab.id)?.status === 'exited') api('DELETE', `/api/terminals/${tab.id}`).catch(() => {});
      state.attention.delete(tab.id);
      if (state.active === tab.id) state.active = started.id;
      tab.id = started.id;
    }
    tab.sid = started.session_id;
    tab.since = Date.now();
    tab.exited = false;
    tab.view = 'terminal';
    await refreshStatus();
    activate(tab.id);
  } catch (e) {
    if (e.status === 409 && !force) {
      const text = t('resume.anywayText', { error: e.message });
      if (await ask({ title: t('resume.anywayTitle'), text, yes: t('resume') })) return resumeTab(tab, true);
      return;
    }
    toast(e.message);
  }
}

async function stopTab(tab) {
  if (!(await ask({ title: t('stop.title'), text: t('stop.text'), yes: t('stop') }))) return;
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
  const none = el('option', '', t('new.noFolder'));
  none.value = '';
  $('#new-folder').replaceChildren(none, ...state.folders.map((folder) => {
    const option = el('option', '', folder.name);
    option.value = folder.id;
    return option;
  }));
  $('#new-folder-row').hidden = !state.folders.length;
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
  const folder = $('#new-folder').value || null;
  const submit = $('#new-form [type="submit"]');
  if (submit.disabled) return;
  submit.disabled = true;  // also stops Enter: a form does not submit through a disabled button
  try {
    const started = await api('POST', '/api/terminals', { cwd, title, folder });
    store.set('lastCwd', started.cwd);
    $('#new-dialog').close();
    if (folder) expandFolder(folder);
    await refreshSessions();
    if (!findTab(started.id)) addTab(started.id, 'terminal', started.session_id);
    activate(started.id);
  } catch (e) {
    $('#new-error').textContent = e.message;
  } finally {
    submit.disabled = false;
  }
}

// ---- settings -----------------------------------------------------------------------------
// What the settings dialog offers. A new customization is one entry here, its texts in i18n.js
// and its allowed values in SCHEMA in clida/settings.py, which checks everything it stores.
// value() is what this window uses right now, apply() switches it.

const SETTINGS = [
  {
    section: 'settings.general',
    items: [
      { key: 'language', label: 'settings.language', hint: 'settings.languageHint',
        choices: () => Object.entries(LANGUAGES), value: language, apply: applyLanguage },
    ],
  },
  {
    section: 'settings.appearance',
    items: [
      { key: 'theme', label: 'settings.theme', hint: 'settings.themeHint', hintNodes: () => ({ cmd: el('code', '', '/theme (Auto (match terminal))') }),
        choices: () => [['system', t('theme.system')], ['light', t('theme.light')], ['dark', t('theme.dark')], ...THEMES],
        value: () => theme, apply: applyTheme },
      { key: 'diffColors', label: 'settings.diffColors', hint: 'settings.diffColorsHint',
        choices: () => ['subtle', 'normal', 'strong', 'vivid'].map((level) => [level, t(`diffColors.${level}`)]),
        value: () => diffColors, apply: applyDiffColors },
    ],
  },
];

// How strongly the changes view tints added and removed lines (data-diffs on <html>, see app.css).
let diffColors = store.get('diffColors', 'normal');
function applyDiffColors(level) {
  diffColors = level;
  store.set('diffColors', level);
  document.documentElement.dataset.diffs = level;
}
applyDiffColors(diffColors);

// The color schemes beyond CLIDA's own light and dark, by their usual names (see themes.css).
const THEMES = [
  ['solarized-light', 'Solarized Light'], ['solarized-dark', 'Solarized Dark'],
  ['catppuccin-latte', 'Catppuccin Latte'], ['catppuccin-mocha', 'Catppuccin Mocha'],
  ['nord', 'Nord'], ['dracula', 'Dracula'], ['gruvbox-dark', 'Gruvbox Dark'], ['tokyo-night', 'Tokyo Night'],
];
let theme = store.get('theme', 'system');  // theme.js has already put it on the page

function applyTheme(name) {
  theme = name;
  store.set('theme', name);
  window.clidaTheme(name);  // fires "clida-theme", which recolors the terminals
}

const ANSI_COLORS = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white'];

// Light or dark: each theme in themes.css says which, as its color-scheme.
const colorMode = () => (getComputedStyle(document.documentElement).colorScheme.includes('dark') ? 'dark' : 'light');

// xterm needs real colors, not CSS variables: take the theme's from the page. Light themes bring
// their own 16 ANSI colors (xterm's defaults are made for a dark background); dark ones keep those.
function terminalTheme() {
  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();
  const theme = {
    background: color('--term-bg'), foreground: color('--term-fg'), cursor: color('--term-cursor'),
    cursorAccent: color('--term-bg'), selectionBackground: color('--term-selection'),
  };
  for (const name of ANSI_COLORS) {
    const bright = `bright${name[0].toUpperCase()}${name.slice(1)}`;
    if (color(`--term-${name}`)) theme[name] = color(`--term-${name}`);
    if (color(`--term-bright-${name}`)) theme[bright] = color(`--term-bright-${name}`);
  }
  return theme;
}

// Take over what the server has stored. Until it answers, the window uses what it remembers.
async function loadSettings() {
  let stored;
  try {
    ({ settings: stored } = await api('GET', '/api/settings'));
  } catch {
    return;  // a server from before the settings: the window keeps what it remembers
  }
  state.serverSettings = stored;
  for (const item of SETTINGS.flatMap((group) => group.items)) {
    if (stored[item.key] !== undefined && stored[item.key] !== item.value()) item.apply(stored[item.key]);
  }
}

function openSettings() {
  $('#settings-error').textContent = '';
  renderSettings();
  $('#settings-dialog').showModal();
  $('#settings-body select')?.focus();
}

function renderSettings(focusKey = null) {
  $('#settings-body').replaceChildren(...SETTINGS.map((group) => {
    const section = el('section', 'settings-section');
    section.append(el('h3', '', t(group.section)));
    for (const item of group.items) {
      const text = el('div', 'settings-text');
      const label = el('label', '', t(item.label));
      label.htmlFor = `setting-${item.key}`;
      text.append(label);
      if (item.hint) {
        const hint = el('p', 'settings-hint');
        hint.append(...textWith(item.hint, item.hintNodes?.() || {}));  // {placeholders} become those nodes
        text.append(hint);
      }
      const select = el('select');
      select.id = `setting-${item.key}`;
      for (const [value, name] of item.choices()) {
        const option = el('option', '', name);
        option.value = value;
        select.append(option);
      }
      select.value = item.value();
      select.onchange = () => saveSetting(item, select);
      const row = el('div', 'settings-row');
      row.append(text, select);
      section.append(row);
    }
    return section;
  }));
  if (focusKey) $(`#setting-${focusKey}`)?.focus();
}

// One save at a time, in order: arrow keys in a select fire a change per step, and answers that
// overtook each other would leave the window and the server on different choices.
let settingsSaving = Promise.resolve();
function saveSetting(item, select) {
  const value = select.value;
  item.latest = value;
  settingsSaving = settingsSaving.then(() => storeSetting(item, value));
  return settingsSaving;
}

async function storeSetting(item, value) {
  try {
    await api('PUT', '/api/settings', { [item.key]: value });
  } catch (e) {
    const select = $(`#setting-${item.key}`);
    if (select && item.latest === value) select.value = item.value();
    // A setting the server did not list is one it does not know yet: it runs older code.
    const known = !state.serverSettings || item.key in state.serverSettings;
    $('#settings-error').textContent = known ? e.message : t('restartNeeded');
    return;
  }
  $('#settings-error').textContent = '';
  item.apply(value);
  if (item.latest === value) renderSettings(item.key);  // its texts may have changed (language)
}

// Switch the interface language. Texts the server makes (titles like "New chat", errors, dividers
// in the history) come along with the reloads started here.
function applyLanguage(lang) {
  setLanguage(lang);
  store.set('language', language());
  translatePage();
  for (const tab of state.tabs) {
    labelView(tab);
    if (!tab.sessionNote.querySelector('.note-editor')) renderSessionNote(tab);
    if (tab.loaded) loadHistory(tab, { quiet: true });
  }
  if (!state.renaming) renderSidebar();
  paint();
  refreshSessions();
}

// ---- wiring -------------------------------------------------------------------------------

// An app shortcut: Ctrl+Shift (on a Mac Cmd+Shift) and the given key.
const appKey = (key) => (MAC ? `⌘⇧${key}` : `${t('key.ctrl')}+${t('key.shift')}+${key}`);

// The texts of the page itself (index.html), with the key names of this platform.
function translatePage() {
  for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll('[data-i18n-placeholder]')) node.placeholder = t(node.dataset.i18nPlaceholder);
  for (const node of document.querySelectorAll('[data-i18n-label]')) {
    const label = t(node.dataset.i18nLabel);
    node.setAttribute('aria-label', label);
    node.title = node.dataset.keys ? `${label} (${appKey(node.dataset.keys)})` : label;
  }
  const keys = [
    [appKey('O'), t('chat.new')],
    [appKey('B'), t('keys.sidebar')],
    [MAC ? '⌘⌥←/→' : `${t('key.ctrl')}+${t('key.pages')}`, t('keys.tabs')],
    [MAC ? '⇧↩' : `${t('key.shift')}+Enter`, t('keys.newline')],
  ];
  $('#keys').replaceChildren(...keys.flatMap(([combo, what]) => [el('dt', '', combo), el('dd', '', what)]));
}

function wire() {
  window.addEventListener('pagehide', () => navigator.sendBeacon(`/api/windows/${WINDOW_ID}/closed`));
  window.addEventListener('clida-theme', () => {  // also when "system" follows the OS
    for (const tab of state.tabs) if (tab.term) tab.term.options.theme = terminalTheme();
    // Light to dark or back: the running CLIs redraw to match (see push_theme in clida/app.py).
    const mode = colorMode();
    if (mode === state.colorMode) return;
    state.colorMode = mode;
    api('POST', '/api/terminals/theme', { mode }).catch(() => {});  // a server from before this: nothing to tell
  });
  state.colorMode = colorMode();  // what the running CLIs saw when they started
  for (const node of document.querySelectorAll('[data-icon]')) node.append(icon(node.dataset.icon));
  document.addEventListener('click', (ev) => {
    const action = ev.target.closest('[data-action]')?.dataset.action;
    if (action === 'toggle-sidebar') setCollapsed(!$('#app').classList.contains('collapsed'));
    else if (action === 'new-chat') openNewDialog();
    else if (action === 'new-folder' && ev.detail < 2) newFolder();  // a double click makes one folder
    else if (action === 'settings') openSettings();
    else if (action === 'close-dialog') $('#new-dialog').close();
  });
  $('#new-form').addEventListener('submit', submitNewChat);
  $('#ask-cancel').onclick = () => answer(false);
  $('#ask-yes').onclick = () => answer(true);
  $('#ask-dialog').addEventListener('cancel', (ev) => {  // Esc
    ev.preventDefault();
    answer(false);
  });
  $('#settings-done').onclick = () => $('#settings-dialog').close();
  $('#settings-close').onclick = () => $('#settings-dialog').close();
  dropZone($('#session-list'), null);
  // A file dropped anywhere must not make the window open it and leave CLIDA; onto a running
  // terminal it becomes an attachment.
  window.addEventListener('dragover', (ev) => {
    if (!hasFiles(ev)) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = ev.target.closest?.('#views') && liveTerminalTab() ? 'copy' : 'none';
  });
  window.addEventListener('drop', (ev) => {
    if (hasFiles(ev)) ev.preventDefault();
    showDropHint(false);
  });
  $('#views').addEventListener('dragenter', (ev) => { if (hasFiles(ev)) showDropHint(true); });
  $('#views').addEventListener('dragleave', (ev) => {
    if (!$('#views').contains(ev.relatedTarget)) showDropHint(false);
  });
  $('#views').addEventListener('drop', (ev) => {
    if (!hasFiles(ev)) return;
    ev.preventDefault();
    ev.stopPropagation();
    showDropHint(false);
    const { files, folders } = droppedFiles(ev);
    attachFiles(liveTerminalTab(), files, folders);
  });
  $('#attach-input').addEventListener('change', (ev) => {
    attachFiles(state.attachTarget, ev.target.files);
    ev.target.value = '';
  });
  // Links in rendered messages and notes (DOMPurify gives them target=_blank as a fallback).
  const externalLink = (ev) => {
    const link = ev.target.closest?.('a[href]');
    if (!link || !/^(https?|mailto):/i.test(link.href) || (ev.type === 'auxclick' && ev.button !== 1)) return;
    if (new URL(link.href).origin === location.origin) return;  // a relative link or #anchor: not a web page
    ev.preventDefault();
    openExternal(link.href);
  };
  document.addEventListener('click', externalLink);
  document.addEventListener('auxclick', externalLink);  // middle click
  window.addEventListener('pointermove', tabPointerMove);
  window.addEventListener('pointerup', tabPointerUp);
  window.addEventListener('pointercancel', tabPointerUp);

  // Only chats and folders have a menu. Text fields keep the browser's own (paste, spelling).
  document.addEventListener('contextmenu', (ev) => {
    if (ev.target.closest('input, textarea')) return;
    ev.preventDefault();
    const item = ev.target.closest('#session-list .item');
    const folder = ev.target.closest('#session-list .folder-head');
    if (item) chatMenu(item.dataset.id, ev, item);
    else if (folder) folderMenu(folder.dataset.folder, ev, folder);
    else closeMenu();
  });
  document.addEventListener('mousedown', (ev) => {
    if (state.menu && !state.menu.menu.contains(ev.target)) closeMenu();
  }, true);
  window.addEventListener('blur', closeMenu);
  window.addEventListener('resize', closeMenu);
  $('#session-list').addEventListener('scroll', closeMenu);
  $('#search').addEventListener('input', renderSidebar);
  document.addEventListener('keydown', changesKey);

  // No developer tools from the keyboard: F12, Ctrl+Shift+I/J/C and Ctrl+U (view source); on a Mac
  // Cmd+Option+I/J/C/U. The browser checks with the page before it acts on these. Its own menu in
  // the window's title bar still offers them; no page can reach that.
  window.addEventListener('keydown', (ev) => {
    const letter = /^Key([A-Z])$/.exec(ev.code)?.[1].toLowerCase() || ev.key.toLowerCase();
    const devtools = ev.key === 'F12' || (MAC
      ? ev.metaKey && ev.altKey && 'ijcu'.includes(letter) && letter.length === 1
      : ev.ctrlKey && ((ev.shiftKey && 'ijc'.includes(letter) && letter.length === 1) || (!ev.shiftKey && !ev.altKey && letter === 'u')));
    if (!devtools) return;
    ev.preventDefault();
    // The terminal still gets these two: Ctrl+Shift+C copies there, Ctrl+U clears the input line.
    const terminalToo = !MAC && ev.ctrlKey && (letter === 'u' || (ev.shiftKey && letter === 'c'));
    if (!terminalToo) ev.stopPropagation();
  }, true);

  // F5 reloads, but saves open notes first, as after a server restart; the browser's own reload
  // would drop what is being written.
  window.addEventListener('keydown', (ev) => {
    if (!['F5', 'BrowserRefresh'].includes(ev.key) || ev.ctrlKey || ev.altKey || ev.metaKey || ev.shiftKey) return;
    ev.preventDefault();
    ev.stopPropagation();
    reloadSafely();
  }, true);

  // Nor the browser's own shortcuts that make no sense in an app: print, save or open a page,
  // bookmarks, history, downloads, Ctrl+R reload, caret browsing, Edge's reader and read aloud, back and
  // forward. Only preventDefault: the terminal still gets these keys (Ctrl+R searches the CLI's
  // history, Ctrl+O shows its transcript, Ctrl+G opens the editor). Find (Ctrl+F) and zoom stay.
  // Ctrl+W, Ctrl+N and Ctrl+T cannot be taken from the browser by any page.
  window.addEventListener('keydown', (ev) => {
    // By the key's label, as the browser matches its own shortcuts: by position (ev.code), the Z of
    // a German keyboard is a Y, and Ctrl+Shift+Z (redo) would be taken for Edge's Ctrl+Shift+Y.
    const letter = /^[a-z]$/i.test(ev.key) ? ev.key.toLowerCase() : '';
    const mod = MAC ? ev.metaKey && !ev.ctrlKey : ev.ctrlKey && !ev.metaKey;
    const browserKey = ['F1', 'F5', 'F6', 'F7', 'F9', 'BrowserBack', 'BrowserForward', 'BrowserRefresh', 'BrowserHome'].includes(ev.key)  // F5 with a modifier: hard reload
      || (mod && !ev.altKey && !ev.shiftKey && 'psodhjr'.includes(letter) && letter)
      || (mod && !ev.altKey && ev.shiftKey && 'drsuy'.includes(letter) && letter)  // bookmark all, hard reload, web capture, read aloud, collections
      || (!MAC && ev.ctrlKey && ev.shiftKey && ev.key === 'Delete')  // clear browsing data
      || (!MAC && ev.altKey && !ev.ctrlKey && ['ArrowLeft', 'ArrowRight', 'Home'].includes(ev.key))
      || (MAC && ev.metaKey && !ev.altKey && ['[', ']'].includes(ev.key));  // not Cmd+Left/Right: line start/end in text
    if (browserKey) ev.preventDefault();
  }, true);
  // The mouse's back and forward buttons. Capture phase: the terminal stops mouse events itself
  // while the CLI tracks the mouse, and they would never get here.
  for (const type of ['mouseup', 'auxclick']) {
    window.addEventListener(type, (ev) => { if (ev.button === 3 || ev.button === 4) ev.preventDefault(); }, true);
  }

  // Capture phase, so the terminal never sees the app's own shortcuts.
  window.addEventListener('keydown', (ev) => {
    const key = ev.key.toLowerCase();
    const mod = MAC ? ev.metaKey && !ev.ctrlKey : ev.ctrlKey && !ev.metaKey;
    // Switch tabs: Ctrl+PgUp/PgDn, on a Mac Cmd+Option+Left/Right (no PgUp key, layout-independent).
    const step = MAC
      ? ev.metaKey && ev.altKey && { ArrowLeft: -1, ArrowRight: 1 }[ev.key]
      : ev.ctrlKey && !ev.shiftKey && { PageUp: -1, PageDown: 1 }[ev.key];
    if (mod && ev.shiftKey && key === 'b') setCollapsed(!$('#app').classList.contains('collapsed'));
    else if (mod && ev.shiftKey && key === 'o') openNewDialog();
    else if (step) cycleTab(step);
    else if (mod && ev.shiftKey && key === 'f') { setCollapsed(false); $('#search').focus(); }
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
  setLanguage(store.get('language', 'de'));
  translatePage();
  if (!(await claimWindow())) {
    stepAside();
    return;
  }
  state.claimed = true;
  wire();
  if (store.get('collapsed', false)) {
    $('#app').classList.add('collapsed');
    $('.sidebar').inert = true;
  }
  setHistoryWidth(store.get('historyWidth', HISTORY_WIDTH.start));
  await loadSettings();
  await refreshSessions();
  const wanted = store.get('active', null);  // read first: addTab saves the tabs, and the active one with them
  for (const saved of store.get('tabs', [])) {
    if (!saved || findTab(saved.id)) continue;
    const sid = saved.sid || saved.id;
    const view = ['terminal', 'changes'].includes(saved.view) ? saved.view : 'history';
    if (state.terminals.has(saved.id)) addTab(saved.id, view, sid);
    else if (state.byId.has(sid) && !state.tabs.some((tab) => tabSession(tab) === sid)) addTab(sid, view === 'terminal' ? 'history' : view, sid);
  }
  const linked = location.hash.slice(1);
  // A terminal gone with a restart: its chat now sits in a history tab of its own id.
  const wantedSid = store.get('tabs', []).find((saved) => saved?.id === wanted)?.sid;
  if (state.byId.has(linked) || state.bySession.has(linked)) {
    history.replaceState(null, '', location.pathname);
    openSession(linked);
  } else if (findTab(wanted)) activate(wanted);
  else if (wantedSid && findTab(wantedSid)) activate(wantedSid);
  else if (state.tabs.length) activate(state.tabs[0].id);
  paint();
  setInterval(refreshStatus, 2000);
  setInterval(refreshSessions, 20000);
}

start();
