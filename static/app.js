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
const TERM_THEME = {
  background: '#1d1c1a', foreground: '#e8e6e1', cursor: '#d97757', cursorAccent: '#1d1c1a',
  selectionBackground: 'rgba(217, 119, 87, 0.35)',
};
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
const PURIFY = { FORBID_TAGS: ['style', 'form', 'input', 'button', 'textarea', 'select'], FORBID_ATTR: ['style'] };
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

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
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
  state.terminals = new Map(data.terminals.map((row) => [row.id, row]));
  state.bySession = new Map(data.terminals.filter((row) => row.status !== 'exited').map((row) => [row.session_id, row]));
  state.external = new Map(data.external.map((e) => [e.session_id, e]));
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
  try {
    finished = applyStatus(await api('GET', '/api/status'));
    setOnline(true);
  } catch (e) {
    setOnline(false, e.status);
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

function setOnline(online, status) {
  state.online = online;
  const banner = $('#banner');
  banner.hidden = online;
  if (online) return;
  // 403: the server runs but no longer knows this window (new token), so a reload cannot help.
  banner.replaceChildren(...textWith(status === 403 ? 'banner.expired' : 'banner.offline', { cmd: el('code', '', 'clida') }));
}

const tabSession = (tab) => state.terminals.get(tab.id)?.session_id || tab.id;
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
  let folder;
  try {
    folder = await change('POST', '/api/folders', { name: t('folder.new') });
  } catch (e) {
    toast(e.message);
    return;
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
  if (folderId) {  // open the target folder, so the chat does not seem to vanish
    const collapsed = store.get('collapsedFolders', {});
    delete collapsed[folderId];
    store.set('collapsedFolders', collapsed);
  }
  renderSidebar();
  paintSidebar();
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
  store.set('collapsed', collapsed);
  setTimeout(() => fitTab(activeTab()), 200);
}

// ---- tabs ---------------------------------------------------------------------------------

function saveTabs() {
  store.set('tabs', state.tabs.map((tab) => ({ id: tab.id, view: tab.view })));
  store.set('active', state.active);
}

function openSession(sid) {
  const term = state.bySession.get(sid);
  const id = term ? term.id : sid;
  if (!findTab(id)) addTab(id, term ? 'terminal' : 'history');
  activate(id);
}

function addTab(id, view) {
  const tab = { id, view, term: null, fit: null, ws: null, loaded: false, showAll: false, items: [],
    notes: { session: null, messages: [] } };
  buildView(tab);
  state.tabs.push(tab);
  saveTabs();
  loadNotes(tab);
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
  histBtn.onclick = () => setView(tab, 'history');
  termBtn.onclick = () => setView(tab, 'terminal');
  seg.append(histBtn, termBtn);

  const actions = el('div', 'view-actions');
  const refresh = el('button', 'icon-btn');
  refresh.append(icon('refresh'));
  refresh.onclick = () => loadHistory(tab);
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
  const termWrap = el('div', 'term-wrap');
  const termHost = el('div', 'term-host');
  const overlay = el('div', 'term-overlay');
  overlay.hidden = true;
  termWrap.append(termHost, overlay);
  body.append(hist, termWrap);
  const sessionNote = el('div', 'session-note');
  sessionNote.hidden = true;
  root.append(head, sessionNote, body);
  $('#views').append(root);
  Object.assign(tab, { root, title, meta, widthCtl, widthRange, histBtn, termBtn, refresh, attach, noteBtn, resume, stop,
    sessionNote, hist, histInner, termWrap, termHost, overlay });
  labelView(tab);
}

// The view's fixed texts, set again after a language switch.
function labelView(tab) {
  tab.title.title = t('view.clickToRename');
  tab.widthCtl.title = t('width.title');
  tab.widthRange.setAttribute('aria-label', t('width'));
  tab.histBtn.textContent = t('view.history');
  tab.termBtn.textContent = t('view.terminal');
  tab.refresh.title = t('history.reload');
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
  if (!tab.title.querySelector('input')) tab.title.textContent = titleOf(sid);
  const parts = [session?.cwd_label || row?.cwd || ''];
  if (row) parts.push(t(`status.${row.status}`));
  else if (ext) parts.push(t('status.elsewhere'));
  tab.meta.textContent = parts.filter(Boolean).join(' · ');
  tab.histBtn.classList.toggle('on', !showTerm);
  tab.termBtn.classList.toggle('on', showTerm);
  tab.termBtn.disabled = !row;
  tab.termBtn.title = row ? '' : t('view.resumeFirst');
  tab.resume.hidden = live;
  tab.stop.hidden = !live;
  tab.refresh.hidden = showTerm;
  tab.attach.hidden = !(showTerm && live);
  tab.widthCtl.hidden = showTerm;
  tab.hist.hidden = showTerm;
  tab.termWrap.hidden = !showTerm;
}

function paint() {
  renderTabs();
  paintSidebar();
  for (const tab of state.tabs) paintView(tab);
  $('#empty').hidden = state.tabs.length > 0;
  const waiting = state.attention.size;
  document.title = waiting ? `(${waiting}) CLIDA` : 'CLIDA';
}

// ---- history ------------------------------------------------------------------------------

async function loadHistory(tab, { quiet = false } = {}) {
  const sid = tabSession(tab);
  const box = tab.hist;
  // A background refresh would throw away a note being written; a later one catches up.
  if (quiet && tab.histInner.querySelector('.note-editor')) return;
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
  renderHistory(tab);
  if (!quiet || atBottom) box.scrollTop = box.scrollHeight;
}

function renderHistory(tab) {
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
    nodes.push(...withNotes(tab, item));
  }
  // Notes whose message is no longer in the transcript still deserve a place.
  const shown = new Set(items.map((item) => item.uid));
  const orphans = tab.notes.messages.filter((note) => !shown.has(note.anchor));
  if (orphans.length && items.length) {
    nodes.push(el('div', 'divider', t('note.orphans')));
    for (const note of orphans) nodes.push(noteCard(tab, note, true));
  }
  tab.histInner.replaceChildren(...nodes);
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
  renderSessionNote(tab);
  if (render && tab.loaded) rerenderHistory(tab);
}

// Re-render the history without losing the reader's place in it.
function rerenderHistory(tab) {
  const top = tab.hist.scrollTop;
  renderHistory(tab);
  tab.hist.scrollTop = top;
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

function noteEditor({ initial = '', onSave, onCancel, onDelete }) {
  const box = el('div', 'note-editor');
  const area = el('textarea');
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
  if (!note) return;
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
  }));
}

// A user or assistant message, with its add-note button and the notes anchored to it.
function withNotes(tab, item) {
  const node = renderItem(item);
  if (!item.uid || (item.k !== 'user' && item.k !== 'assistant')) return [node];
  const wrap = el('div', `msg-wrap ${item.k}`);
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
        rerenderHistory(tab);
      },
      onCancel: () => editor.remove(),
    });
    wrap.after(editor);
  };
  wrap.append(node, add);
  const cards = tab.notes.messages.filter((note) => note.anchor === item.uid).map((note) => noteCard(tab, note));
  return [wrap, ...cards];
}

function noteCard(tab, note, withPreview = false) {
  const card = el('div', 'note-card');
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
    card.replaceWith(noteEditor({
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
        rerenderHistory(tab);
      },
      onCancel: () => rerenderHistory(tab),
      onDelete: remove,
    }));
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
        ? `${t('steps', { n: tools })} · ${names.slice(0, 4).join(', ')}${names.length > 4 ? ' …' : ''}`
        : t('thinking');
      summary.replaceChildren(el('span', '', label));
      if (errors) summary.append(el('span', 'badge', t('errors', { n: errors })));
    },
  };
}

function renderStep(item) {
  if (item.k === 'thinking') {
    const node = el('div', 'thinking md');
    renderMarkdown(node, item.text);
    return node;
  }
  const node = el('details', 'tool');
  const summary = el('summary');
  summary.append(el('span', 'tool-name', item.name), el('span', 'tool-sum', item.summary));
  if (item.error) summary.append(el('span', 'badge', t('error')));
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

// ---- attachments --------------------------------------------------------------------------
// A browser never tells where a dropped or picked file lives on disk. So these files are copied
// into the session's upload folder (the CLI may read it via --add-dir) and that path is pasted,
// just as a terminal pastes a dragged file's path. Ctrl+V needs none of this: on an empty paste
// the CLI reads the clipboard itself, original paths included.

const UPLOAD_LIMIT = 50 * 1024 * 1024;

function liveTerminalTab() {
  const tab = activeTab();
  const row = tab && state.terminals.get(tab.id);
  return tab && tab.term && tab.view === 'terminal' && row && row.status !== 'exited' ? tab : null;
}

const hasFiles = (ev) => [...(ev.dataTransfer?.types || [])].includes('Files');

async function attachFiles(tab, files) {
  const list = [...files];
  if (!list.length) return;
  if (!tab) {
    toast(t('attach.noSession'));
    return;
  }
  toast(list.length === 1 ? t('attach.one', { name: quote(list[0].name) }) : t('attach.many', { n: list.length }));
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
  if (!paths.length) return;
  $('#toast').hidden = true;
  tab.term.paste(paths.join(' '));  // a bracketed paste, so the CLI turns image paths into [Image #n]
  tab.term.focus();
}

function droppedFiles(ev) {
  const files = [];
  for (const item of ev.dataTransfer.items) {
    if (item.kind !== 'file') continue;
    if (item.webkitGetAsEntry?.()?.isDirectory) {
      toast(t('attach.folder'));
      continue;
    }
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  return files;
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
      if (state.active === tab.id) state.active = started.id;
      tab.id = started.id;
    }
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
  try {
    const started = await api('POST', '/api/terminals', { cwd, title });
    store.set('lastCwd', started.cwd);
    $('#new-dialog').close();
    await refreshSessions();
    if (folder) await moveToFolder(started.session_id, folder);
    if (!findTab(started.id)) addTab(started.id, 'terminal');
    activate(started.id);
  } catch (e) {
    $('#new-error').textContent = e.message;
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
];

// Take over what the server has stored. Until it answers, the window uses what it remembers.
async function loadSettings() {
  let stored;
  try {
    ({ settings: stored } = await api('GET', '/api/settings'));
  } catch {
    return;  // a server from before the settings: the window keeps what it remembers
  }
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
      if (item.hint) text.append(el('p', 'settings-hint', t(item.hint)));
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

async function saveSetting(item, select) {
  const value = select.value;
  try {
    await api('PUT', '/api/settings', { [item.key]: value });
  } catch (e) {
    select.value = item.value();
    $('#settings-error').textContent = e.message;
    return;
  }
  $('#settings-error').textContent = '';
  item.apply(value);
  renderSettings(item.key);  // the dialog's own texts may have changed
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
  for (const node of document.querySelectorAll('[data-icon]')) node.append(icon(node.dataset.icon));
  document.addEventListener('click', (ev) => {
    const action = ev.target.closest('[data-action]')?.dataset.action;
    if (action === 'toggle-sidebar') setCollapsed(!$('#app').classList.contains('collapsed'));
    else if (action === 'new-chat') openNewDialog();
    else if (action === 'new-folder') newFolder();
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
    attachFiles(liveTerminalTab(), droppedFiles(ev));
  });
  $('#attach-input').addEventListener('change', (ev) => {
    attachFiles(state.attachTarget, ev.target.files);
    ev.target.value = '';
  });
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
  wire();
  if (store.get('collapsed', false)) $('#app').classList.add('collapsed');
  setHistoryWidth(store.get('historyWidth', HISTORY_WIDTH.start));
  await loadSettings();
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
