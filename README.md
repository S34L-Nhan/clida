# CLIDA

A desktop window for the Claude Code CLI, similar to Claude Desktop. It runs on Windows (WSL) and macOS. The UI is in German; UI labels below are quoted as they appear.

- **Sidebar** with all past chats from `~/.claude/projects`, grouped by date (today, yesterday, last 7 days …), with search. It collapses and expands.
- **Rename chats**: pencil icon, double-click the title in the list or on a tab, or click the heading.
- **Folders**: the folder icon at the top of the sidebar creates a folder. Drag chats into it, and drag them out again to put them back in the main list. Right-click a folder to rename or delete it. Deleting a folder moves its chats back to the main list.
- **Right-click on a chat**: *Archivieren* (archive) takes it out of the list but keeps its history. It can be restored from the *Archiv* section at the bottom. *Löschen* (delete) asks first, then removes the chat from disk for good: transcript, tool output, file backups and env snapshot. A running session must be stopped first. Nothing else has a right-click menu, except text fields (paste, spelling).
- **Notes**, private to you:
  - A *session note* per chat (note icon in the header), e.g. "waits for review of MR 4027". It shows under the header in both views, marks the chat in the sidebar and sits in the tab's tooltip, so with several sessions running you see at once where each one stands.
  - *Message notes*: hover a message in the history and click the note icon; the note sits right under the message.
  - Both are markdown. Pasting rendered output keeps lists, bold and code: the converter is ported from Pablo Oliva's [Session Notes plugin for bb](https://github.com/pablooliva/bb-ide-session-notes-plugin) (MIT).
  - Notes never reach Claude: CLIDA keeps them in its own store and never types them into a terminal or writes them to a transcript. They go when the chat is deleted and stay when it is archived.
- **Attachments** in the terminal:
  - *Ctrl+V* (⌘V on a Mac) pastes a screenshot or a copied image file just as in the plain CLI: the CLI reads the clipboard itself, with the file's real path.
  - *Drag a file onto the terminal* or use the *paperclip* in the header. A browser never reveals where a file lives on disk, so CLIDA copies it into `~/.clida/uploads/<session>/` and pastes that path; images become `[Image #n]`.
- **Hybrid view** per chat:
  - *Verlauf* (history): the chat as a rendered conversation (Markdown, tool calls collapsed). Code blocks are syntax-highlighted (SQL, PHP, JS, Bash, JSON …) and have a copy button. A slider in the header sets the text width; the middle is the default width, and a double-click resets it.
  - *Terminal*: the real `claude` CLI in an embedded terminal (xterm.js). Everything works as usual: permission prompts, slash commands, plan and auto mode.
- **Parallel sessions**: each session has its own tab and keeps working in the background, even when its tab is closed. The dots show the state:
  - pulsing orange = working
  - yellow = waiting for you (e.g. a permission prompt)
  - green = ready
  - ring = running in another terminal outside CLIDA

  When a background session finishes, its title turns bold and the window title shows `(n)`.

## Requirements and setup

Common to both: Python 3.9 or newer (stdlib only, no pip), Node.js/npm (only to fetch the frontend libraries on the first start), and the `claude` CLI.

### Windows (WSL)

- WSL 2, plus Microsoft Edge or Google Chrome on the Windows side

```bash
git clone https://github.com/S34L-Nhan/clida.git ~/clida
ln -s ~/clida/bin/clida ~/.local/bin/clida   # put the launcher on PATH
clida shortcut                               # optional: Windows desktop shortcut
clida                                        # first start runs npm install
```

### macOS

- `python3` from the Xcode Command Line Tools or Homebrew
- Google Chrome, Microsoft Edge, Brave or Chromium for an app window. Without one of them, CLIDA opens in a normal tab of the default browser (Safari has no app windows).

```bash
git clone https://github.com/S34L-Nhan/clida.git ~/clida
mkdir -p ~/.local/bin && ln -s ~/clida/bin/clida ~/.local/bin/clida   # the claude installer puts ~/.local/bin on PATH
clida shortcut                               # optional: ~/Applications/CLIDA.app (Launchpad, Spotlight, Dock)
clida                                        # first start runs npm install
```

## Usage

```bash
clida            # start the server if needed and open the window
clida status     # is the server running, which sessions are running
clida stop       # stop the server; asks first if sessions are running (--force: no question)
clida restart
clida serve      # run the server in the foreground, logs to the terminal
clida url        # one-time login URL (valid for 60 s), e.g. for another browser
clida shortcut   # create/update the shortcut (WSL: Windows desktop, macOS: ~/Applications/CLIDA.app)
```

The window is a browser app window (`--app=…`): no address bar, and its own taskbar or Dock entry. On WSL, Edge comes first and Chrome second; on macOS, Chrome, Edge, Brave and Chromium in that order.

On WSL, the desktop shortcut runs `clida app` via `conhost.exe --headless wsl.exe …`, so no console window appears. Its icon lives in `%LOCALAPPDATA%\clida\clida.ico`. On macOS, `clida shortcut` builds a small AppleScript app in `~/Applications` with the icon from `static/icon-1024.png`. `tools/make_icon.py` renders both icons from the same motif as `static/icon.svg`.

### Keeping WSL alive

WSL shuts down once no `wsl.exe` is left on the Windows side, and takes the server with it. So `clida` keeps a hidden `wsl.exe` process open (`clida keepalive`) while the server runs. After the server stops, it exits by itself within about 45 s. Only one runs at a time (lock in `~/.clida/keepalive.lock`).

### Keys

| Windows (WSL) | macOS | Action |
|---|---|---|
| Ctrl+Shift+O | ⌘⇧O | New chat |
| Ctrl+Shift+B | ⌘⇧B | Toggle sidebar |
| Ctrl+Shift+F | ⌘⇧F | Search chats |
| Ctrl+PgUp / Ctrl+PgDn | ⌘⌥← / ⌘⌥→ | Switch tab |
| Shift+Enter | ⇧↩ | New line in the terminal (instead of sending) |
| Ctrl+C with a selection | ⌘C | Copy. On Windows, Ctrl+C without a selection goes to the CLI; on macOS Ctrl+C always does. |
| Ctrl+V | ⌘V | Paste. On macOS, Ctrl+V goes to the CLI (for pasting images). |
| Middle-click on a tab | Middle-click on a tab | Close tab |
| Drag a tab left or right | Drag a tab left or right | Reorder tabs (the order is kept) |
| Tab key, then Enter | Tab key, then Enter | Open a chat or tab with the keyboard |
| F2 | F2 | Rename the selected chat or tab |

The tooltips and the start page show the keys of the platform in use.

- **New chat**: pick a working directory (recently used ones are suggested), and optionally a title and a folder. The title goes to the CLI via `--name`; the folder list only shows up once you have folders.
- **Open an earlier chat**: shows the history first. *Fortsetzen* (resume) runs `claude --resume <id>` in the original working directory. If the chat already runs in another terminal, CLIDA asks first.
- **Closing a tab** does not end the session. Use *Beenden* (stop) for that. The history is kept.

## How it works

- `clida/` is a small server built on the Python stdlib only (no pip). It listens on `127.0.0.1:47321`.
  - `terminals.py` starts each session with `pty.fork()` as the real `claude` CLI, with `--add-dir` on the session's upload folder so the CLI may read attached files. Up to 2 MB of output is buffered, so a newly opened tab can rebuild the screen. Each tab gets its own send queue, so a slow tab never stalls a session.
  - `transcripts.py` reads the transcripts in `~/.claude/projects/*/*.jsonl`. Files are read incrementally; the index is cached in `~/.clida/index.json`.
  - `registry.py` reads `~/.claude/sessions/<pid>.json`, where every running CLI reports its state (busy/idle/waiting). It checks that the process still lives via `/proc` on Linux and WSL, and via `ps` on macOS.
  - `library.py` stores folders and the archive, `notes.py` the notes. A message note is anchored to the transcript entry's `uuid`, which stays stable across reloads, resumes and compactions.
  - `ws.py` is a minimal WebSocket implementation for the terminal stream.
- `static/` is the frontend: vanilla JS, no build step. xterm.js, marked, DOMPurify and highlight.js come from `npm install` into `node_modules/` (`clida` does this on first start) and are served locally.

### Titles

Titles set in CLIDA are stored in `~/.clida/titles.json` and take precedence there. CLIDA also appends a `custom-title` entry to the transcript, exactly like `/rename` does, so `claude --resume` shows the new name too.

### Security

Whoever can reach the server can start terminals, so it is protected in several layers:

- **Localhost only:** it listens on `127.0.0.1` only.
- **Token cookie:** every request needs a token cookie (`HttpOnly`, `SameSite=Strict`). The token lives in `~/.clida/token` (mode 0600).
- **One-time tickets:** `clida` logs the window in with a ticket that is valid once and for 60 s only. The real token therefore never appears in a URL, the browser history or the process list.
- **Host and Origin checks:** foreign `Host` headers (DNS rebinding) and foreign `Origin` headers (other websites, WebSockets included) are rejected.
- **Content Security Policy:** scripts come only from the server itself, no external images, no embedding in other pages. Rendered histories also go through DOMPurify, without `<style>` and without form elements. So HTML injected into a transcript (e.g. from a fetched web page) cannot run anything.
- **Private data folder:** `~/.clida` has mode 0700, because the index, titles and log quote your prompts.
- **Isolated sessions:** a session does not inherit the terminals of earlier sessions.

One limit comes from the browser: cookies do not distinguish ports, so other local services on `localhost` receive the cookie too. They cannot use it, because the Origin check rejects their requests.

### Data

| Path | Contents |
|---|---|
| `~/.clida/server.log` | Server log |
| `~/.clida/index.json` | Chat index cache (safe to delete) |
| `~/.clida/titles.json` | Titles set in CLIDA |
| `~/.clida/library.json` | Folders and archived chats |
| `~/.clida/notes.json` | Session and message notes |
| `~/.clida/uploads/` | Copies of attached files, one folder per session (removed when the chat is deleted) |
| `~/.clida/token` | Login token of the window |

Port and paths can be changed with `CLIDA_PORT`, `CLIDA_HOME` and `CLIDA_CLAUDE` (path to the CLI).

## Limitations

- Sessions live in the server process. `clida stop`, `wsl --shutdown` or a Windows restart ends them. The history is kept, and *Fortsetzen* brings them back.
- If you switch sessions inside the CLI with `/clear` or `/resume`, the tab follows the new session id from the CLI's registry. This is not tested much yet.
- Dragged or picked files are copies: Claude sees the copy's path, and its edits do not reach the original. For files of your project, use `@` in the CLI instead. Up to 50 MB per file.
- macOS support is new and has not run on a real Mac yet. Start, window, shortcut, stop, status detection and the Mac shortcuts were checked in a simulation on Linux.
