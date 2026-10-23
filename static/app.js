import { Terminal } from '/vendor/xterm.mjs';
import { FitAddon } from '/vendor/addon-fit.mjs';
import { WebLinksAddon } from '/vendor/addon-web-links.mjs';
import { marked } from '/vendor/marked.esm.js';
import DOMPurify from '/vendor/purify.es.mjs';
import hljs from '/vendor/highlight.mjs';

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
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
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
const STATUS_LABEL = { busy: 'arbeitet', waiting: 'wartet auf dich', idle: 'bereit', starting: 'startet', exited: 'beendet' };
const HISTORY_WINDOW = 400;
// Text width slider 0..100: 0 = narrowest, 50 = the classic 800px column, 100 = full width.
const HISTORY_WIDTH = { min: 480, normal: 800, start: 50 };
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
  copy.title = 'In die Zwischenablage kopieren';
  copy.append(icon('copy'), el('span', '', 'Kopieren'));
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
  button.replaceChildren(icon('check'), el('span', '', 'Kopiert'));
  button.classList.add('done');
  clearTimeout(button.resetTimer);
  button.resetTimer = setTimeout(() => {
    button.replaceChildren(icon('copy'), el('span', '', 'Kopieren'));
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
  banner.replaceChildren(...(status === 403
    ? ['Anmeldung abgelaufen – bitte CLIDA über die Verknüpfung oder ', el('code', '', 'clida'), ' neu öffnen.']
    : ['Server nicht erreichbar – läuft ', el('code', '', 'clida'), ' noch?']));
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
  if (!nodes.length) nodes.push(el('div', 'list-empty', query ? 'Keine Treffer' : 'Noch keine Chats'));
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
    body.append(...(chats.length ? chats.map(sessionItem) : [el('div', 'folder-empty', 'Chats hierher ziehen')]));
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
    el('span', 'folder-name', 'Archiv'), el('span', 'folder-count', String(chats.length)));
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
    folder = await change('POST', '/api/folders', { name: 'Neuer Ordner' });
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

function confirmDelete(name) {
  const dialog = $('#delete-dialog');
  $('#delete-name').textContent = `„${name}“`;
  dialog.returnValue = '';
  dialog.showModal();
  $('#delete-cancel').focus();
  return new Promise((resolve) => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'delete'), { once: true });
  });
}

async function deleteChat(sid) {
  if (!(await confirmDelete(titleOf(sid)))) return;
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
      ? { label: 'Wiederherstellen', icon: 'restore', action: () => setArchived(sid, false) }
      : { label: 'Archivieren', icon: 'archive', action: () => setArchived(sid, true) },
    { label: 'Löschen', icon: 'trash', danger: true, action: () => deleteChat(sid) },
  ]);
}

function folderMenu(folderId, ev, anchor) {
  const folder = state.folders.find((f) => f.id === folderId);
  if (!folder) return;
  showMenu(ev, anchor, [
    { label: 'Umbenennen', icon: 'pencil', action: () => renameFolder(folder.id) },
    { label: 'Ordner löschen', icon: 'trash', danger: true, action: () => deleteFolder(folder) },
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

  const widthCtl = el('label', 'width-ctl');
  widthCtl.title = 'Textbreite (Doppelklick: Standard)';
  const widthRange = el('input');
  widthRange.type = 'range';
  widthRange.min = '0';
  widthRange.max = '100';
  widthRange.value = String(store.get('historyWidth', HISTORY_WIDTH.start));
  widthRange.setAttribute('aria-label', 'Textbreite');
  widthRange.oninput = () => setHistoryWidth(Number(widthRange.value));
  widthRange.ondblclick = () => setHistoryWidth(HISTORY_WIDTH.start);
  widthCtl.append(icon('width'), widthRange);

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
  root.append(head, body);
  $('#views').append(root);
  Object.assign(tab, { root, title, meta, widthCtl, widthRange, histBtn, termBtn, refresh, resume, stop, hist, histInner, termWrap, termHost, overlay });
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
  // Polling repaints every 2 s; rebuilding unchanged tabs would only throw away focus and hover.
  const signature = JSON.stringify(state.tabs.map((tab) => {
    const sid = tabSession(tab);
    return [tab.id, sid, titleOf(sid), state.terminals.get(tab.id)?.status, statusFor(sid).cls,
      state.attention.has(tab.id), tab.id === state.active];
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
    node.onkeydown = (ev) => onItemKey(ev, node, () => activate(tab.id), () => startRename(label, sid));
    node.append(dot, label, close);
    return node;
  });
  $('#tabs').replaceChildren(...nodes);
  const again = focusId && $(`#tabs .tab[data-id="${focusId}"]`);
  if (again) (focusClose ? again.querySelector('.icon-btn') : again).focus();
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
    renderMarkdown(node, item.text);
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

// Show the Mac key names in tooltips and in the key list of the start page.
function macKeyLabels() {
  const swap = (text) => text.replace(/Strg\+Umschalt\+/g, '⌘⇧').replace('Strg+Bild↑/↓', '⌘⌥←/→')
    .replace('Umschalt+Enter', '⇧↩');
  for (const node of document.querySelectorAll('[title]')) node.title = swap(node.title);
  for (const node of document.querySelectorAll('.keys dt')) node.textContent = swap(node.textContent);
}

function wire() {
  if (MAC) macKeyLabels();
  for (const node of document.querySelectorAll('[data-icon]')) node.append(icon(node.dataset.icon));
  document.addEventListener('click', (ev) => {
    const action = ev.target.closest('[data-action]')?.dataset.action;
    if (action === 'toggle-sidebar') setCollapsed(!$('#app').classList.contains('collapsed'));
    else if (action === 'new-chat') openNewDialog();
    else if (action === 'new-folder') newFolder();
    else if (action === 'close-dialog') $('#new-dialog').close();
  });
  $('#new-form').addEventListener('submit', submitNewChat);
  $('#delete-cancel').onclick = () => $('#delete-dialog').close('cancel');
  $('#delete-confirm').onclick = () => $('#delete-dialog').close('delete');
  dropZone($('#session-list'), null);

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
  wire();
  if (store.get('collapsed', false)) $('#app').classList.add('collapsed');
  setHistoryWidth(store.get('historyWidth', HISTORY_WIDTH.start));
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
