// Every text of the interface, in each language CLIDA speaks. t('key', { name }) fills in {name};
// an entry can also be a function of those values, for plurals. A key missing in one language
// falls back to German. Texts the server makes (error messages, "New chat") follow the same
// setting there (clida/settings.py).

export const LANGUAGES = { de: 'Deutsch', en: 'English' };  // each in its own language
const LOCALES = { de: 'de-DE', en: 'en-GB' };  // for dates; en-GB keeps the 24-hour clock

const TEXTS = {
  de: {
    'chat.new': 'Neuer Chat',
    'folder.new': 'Neuer Ordner',
    'sidebar.collapse': 'Seitenleiste einklappen',
    'sidebar.expand': 'Seitenleiste ausklappen',
    'search.placeholder': 'Chats durchsuchen',
    'empty.title': 'Womit legen wir los?',
    'empty.text': 'Starte einen neuen Chat oder öffne links einen früheren.',
    'empty.background': 'Laufende Sessions arbeiten im Hintergrund weiter, auch wenn ihr Tab geschlossen ist.',
    'keys.sidebar': 'Seitenleiste ein/aus',
    'keys.tabs': 'Tab wechseln',
    'keys.newline': 'Zeilenumbruch im Terminal',
    'key.ctrl': 'Strg',
    'key.shift': 'Umschalt',
    'key.pages': 'Bild↑/↓',

    'new.cwd': 'Arbeitsverzeichnis',
    'new.title': 'Titel',
    'new.titlePlaceholder': 'wird sonst automatisch vergeben',
    'new.folder': 'Ordner',
    'new.noFolder': 'Kein Ordner',
    'new.start': 'Starten',
    'optional': '(optional)',
    'cancel': 'Abbrechen',
    'save': 'Speichern',
    'delete': 'Löschen',
    'edit': 'Bearbeiten',
    'rename': 'Umbenennen',
    'done': 'Fertig',
    'quoted': '„{text}“',

    'delete.title': 'Sitzung löschen?',
    'delete.text': '{name} wird dauerhaft gelöscht. Dies kann nicht rückgängig gemacht werden.',

    'banner.offline': 'Server nicht erreichbar – läuft {cmd} noch?',
    'banner.expired': 'Anmeldung abgelaufen – bitte CLIDA über die Verknüpfung oder {cmd} neu öffnen.',
    'restartNeeded': 'Diese Funktion braucht einen Neustart: clida restart',

    'status.busy': 'arbeitet',
    'status.waiting': 'wartet auf dich',
    'status.idle': 'bereit',
    'status.starting': 'startet',
    'status.exited': 'beendet',
    'status.external': 'läuft in anderem Terminal ({status})',
    'status.elsewhere': 'läuft in einem anderen Terminal',

    'group.today': 'Heute',
    'group.yesterday': 'Gestern',
    'group.week': 'Letzte 7 Tage',
    'group.month': 'Letzte 30 Tage',
    'list.noMatches': 'Keine Treffer',
    'list.empty': 'Noch keine Chats',
    'folder.dropHere': 'Chats hierher ziehen',
    'folder.delete': 'Ordner löschen',
    'archive.title': 'Archiv',
    'archive': 'Archivieren',
    'restore': 'Wiederherstellen',

    'view.clickToRename': 'Klicken zum Umbenennen',
    'view.history': 'Verlauf',
    'view.terminal': 'Terminal',
    'view.resumeFirst': 'Erst „Fortsetzen“, dann läuft die Session hier im Terminal',
    'width': 'Textbreite',
    'width.title': 'Textbreite (Doppelklick: Standard)',
    'history.reload': 'Verlauf neu laden',
    'resume': 'Fortsetzen',
    'stop': 'Beenden',
    'tab.close': 'Tab schließen',
    'tab.closeRunning': 'Tab schließen (Session läuft im Hintergrund weiter)',

    'history.loading': 'Lade Verlauf …',
    'history.more': 'Frühere Einträge anzeigen ({n})',
    'history.truncated': 'Sehr lange Unterhaltung – nur die letzten Einträge werden angezeigt.',
    'history.emptyLive': 'Noch keine Nachrichten – schreib im Terminal los.',
    'history.empty': 'Keine Nachrichten.',
    'steps': ({ n }) => `${n} ${n === 1 ? 'Schritt' : 'Schritte'}`,
    'thinking': 'Gedankengang',
    'error': 'Fehler',
    'errors': '{n} Fehler',
    'copy': 'Kopieren',
    'copy.title': 'In die Zwischenablage kopieren',
    'copied': 'Kopiert',

    'note': 'Notiz',
    'note.tooltip': 'Notiz: {note}',
    'note.session': 'Notiz zu dieser Session (nur für dich, Claude sieht sie nie)',
    'note.message': 'Notiz zu dieser Nachricht',
    'note.placeholder': 'Notiz in Markdown – nur für dich, Claude sieht sie nie',
    'note.keys': '{mod}+Enter speichert · Esc verwirft',
    'note.clickToEdit': 'Klicken zum Bearbeiten',
    'note.confirmDelete': 'Notiz löschen?',
    'note.orphans': 'Notizen zu Nachrichten, die nicht mehr im Verlauf stehen',

    'attach.title': 'Datei anhängen (oder einfach ins Terminal ziehen)',
    'attach.noSession': 'Anhänge gehen nur in eine laufende Session: erst im Terminal öffnen.',
    'attach.one': 'Hänge {name} an …',
    'attach.many': 'Hänge {n} Dateien an …',
    'attach.tooLarge': '{name} ist größer als 50 MB.',
    'attach.failed': '{name} konnte nicht angehängt werden: {error}',
    'attach.folder': 'Ordner lassen sich nicht anhängen, nur einzelne Dateien.',
    'attach.drop': 'Zum Anhängen loslassen',
    'attach.dropNoSession': 'Anhänge gehen nur in eine laufende Session im Terminal',

    'terminal.ended': 'Session beendet. Der Verlauf ist gespeichert.',
    'terminal.endedCode': 'Session beendet (Code {code}). Der Verlauf ist gespeichert.',
    'terminal.reconnecting': 'Verbindung getrennt – verbinde neu …',
    'resume.anyway': '{error}\n\nTrotzdem hier fortsetzen? Dann schreiben zwei Prozesse in denselben Verlauf.',
    'stop.confirm': 'Session beenden?\n\nDer Verlauf bleibt erhalten und kann jederzeit fortgesetzt werden.',

    'settings': 'Einstellungen',
    'settings.general': 'Allgemein',
    'settings.language': 'Sprache',
    'settings.languageHint': 'Sprache der Oberfläche. Claude antwortet weiter in der Sprache, in der du schreibst.',
  },

  en: {
    'chat.new': 'New chat',
    'folder.new': 'New folder',
    'sidebar.collapse': 'Collapse sidebar',
    'sidebar.expand': 'Expand sidebar',
    'search.placeholder': 'Search chats',
    'empty.title': 'Where shall we start?',
    'empty.text': 'Start a new chat or open an earlier one on the left.',
    'empty.background': 'Running sessions keep working in the background, even when their tab is closed.',
    'keys.sidebar': 'Show or hide the sidebar',
    'keys.tabs': 'Switch tabs',
    'keys.newline': 'New line in the terminal',
    'key.ctrl': 'Ctrl',
    'key.shift': 'Shift',
    'key.pages': 'PgUp/PgDn',

    'new.cwd': 'Working directory',
    'new.title': 'Title',
    'new.titlePlaceholder': 'chosen automatically otherwise',
    'new.folder': 'Folder',
    'new.noFolder': 'No folder',
    'new.start': 'Start',
    'optional': '(optional)',
    'cancel': 'Cancel',
    'save': 'Save',
    'delete': 'Delete',
    'edit': 'Edit',
    'rename': 'Rename',
    'done': 'Done',
    'quoted': '“{text}”',

    'delete.title': 'Delete session?',
    'delete.text': '{name} will be permanently deleted. This cannot be undone.',

    'banner.offline': 'Server unreachable – is {cmd} still running?',
    'banner.expired': 'Sign-in expired – please reopen CLIDA from the shortcut or with {cmd}.',
    'restartNeeded': 'This feature needs a restart: clida restart',

    'status.busy': 'working',
    'status.waiting': 'waiting for you',
    'status.idle': 'ready',
    'status.starting': 'starting',
    'status.exited': 'ended',
    'status.external': 'running in another terminal ({status})',
    'status.elsewhere': 'running in another terminal',

    'group.today': 'Today',
    'group.yesterday': 'Yesterday',
    'group.week': 'Previous 7 days',
    'group.month': 'Previous 30 days',
    'list.noMatches': 'No matches',
    'list.empty': 'No chats yet',
    'folder.dropHere': 'Drag chats here',
    'folder.delete': 'Delete folder',
    'archive.title': 'Archive',
    'archive': 'Archive',
    'restore': 'Restore',

    'view.clickToRename': 'Click to rename',
    'view.history': 'History',
    'view.terminal': 'Terminal',
    'view.resumeFirst': 'Click “Resume” first, then the session runs here in the terminal',
    'width': 'Text width',
    'width.title': 'Text width (double-click: default)',
    'history.reload': 'Reload history',
    'resume': 'Resume',
    'stop': 'Stop',
    'tab.close': 'Close tab',
    'tab.closeRunning': 'Close tab (the session keeps running in the background)',

    'history.loading': 'Loading history …',
    'history.more': 'Show earlier entries ({n})',
    'history.truncated': 'Very long conversation – only the latest entries are shown.',
    'history.emptyLive': 'No messages yet – start typing in the terminal.',
    'history.empty': 'No messages.',
    'steps': ({ n }) => `${n} ${n === 1 ? 'step' : 'steps'}`,
    'thinking': 'Thinking',
    'error': 'Error',
    'errors': ({ n }) => `${n} ${n === 1 ? 'error' : 'errors'}`,
    'copy': 'Copy',
    'copy.title': 'Copy to clipboard',
    'copied': 'Copied',

    'note': 'Note',
    'note.tooltip': 'Note: {note}',
    'note.session': 'Note on this session (only for you, Claude never sees it)',
    'note.message': 'Note on this message',
    'note.placeholder': 'Note in Markdown – only for you, Claude never sees it',
    'note.keys': '{mod}+Enter saves · Esc discards',
    'note.clickToEdit': 'Click to edit',
    'note.confirmDelete': 'Delete note?',
    'note.orphans': 'Notes on messages that are no longer in the history',

    'attach.title': 'Attach a file (or just drag it into the terminal)',
    'attach.noSession': 'Attachments only go into a running session: open it in the terminal first.',
    'attach.one': 'Attaching {name} …',
    'attach.many': 'Attaching {n} files …',
    'attach.tooLarge': '{name} is larger than 50 MB.',
    'attach.failed': 'Could not attach {name}: {error}',
    'attach.folder': 'Folders cannot be attached, only single files.',
    'attach.drop': 'Drop to attach',
    'attach.dropNoSession': 'Attachments only go into a running session in the terminal',

    'terminal.ended': 'Session ended. The history is saved.',
    'terminal.endedCode': 'Session ended (code {code}). The history is saved.',
    'terminal.reconnecting': 'Connection lost – reconnecting …',
    'resume.anyway': '{error}\n\nResume here anyway? Then two processes write to the same history.',
    'stop.confirm': 'Stop the session?\n\nThe history is kept and can be resumed at any time.',

    'settings': 'Settings',
    'settings.general': 'General',
    'settings.language': 'Language',
    'settings.languageHint': 'Language of the interface. Claude still answers in the language you write in.',
  },
};

let current = 'de';

export const language = () => current;
export const locale = () => LOCALES[current];

export function setLanguage(lang) {
  current = TEXTS[lang] ? lang : 'de';
  document.documentElement.lang = current;
}

export function t(key, params = {}) {
  const entry = TEXTS[current][key] ?? TEXTS.de[key];
  if (entry === undefined) return key;
  const text = typeof entry === 'function' ? entry(params) : entry;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}
