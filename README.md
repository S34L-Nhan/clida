# Claude Desk

A desktop window for the Claude Code CLI, similar to Claude Desktop. The UI is in German; UI labels below are quoted as they appear.

- **Sidebar** with all past chats from `~/.claude/projects`, grouped by date (today, yesterday, last 7 days …), with search. It collapses and expands.
- **Rename chats**: pencil icon, double-click the title in the list or on a tab, or click the heading.
- **Folders**: the folder icon at the top of the sidebar creates a folder. Drag chats into it, and drag them out again to put them back in the main list. Right-click a folder to rename or delete it. Deleting a folder moves its chats back to the main list.
- **Right-click on a chat**: *Archivieren* (archive) takes it out of the list but keeps its history. It can be restored from the *Archiv* section at the bottom. *Löschen* (delete) asks first, then removes the chat from disk for good: transcript, tool output, file backups and env snapshot. A running session must be stopped first. Nothing else has a right-click menu, except text fields (paste, spelling).
- **Hybrid view** per chat:
  - *Verlauf* (history): the chat as a rendered conversation (Markdown, tool calls collapsed). Code blocks are syntax-highlighted (SQL, PHP, JS, Bash, JSON …) and have a copy button. A slider in the header sets the text width; the middle is the default width, and a double-click resets it.
  - *Terminal*: the real `claude` CLI in an embedded terminal (xterm.js). Everything works as usual: permission prompts, slash commands, plan and auto mode.
- **Parallel sessions**: each session has its own tab and keeps working in the background, even when its tab is closed. The dots show the state:
  - pulsing orange = working
  - yellow = waiting for you (e.g. a permission prompt)
  - green = ready
  - ring = running in another terminal outside Claude Desk

  When a background session finishes, its title turns bold and the window title shows `(n)`.

## Requirements and setup

- WSL 2 with Python 3.12 (stdlib only, no pip), Node.js/npm (only to fetch the frontend libraries), and the `claude` CLI
- Microsoft Edge or Google Chrome on the Windows side

```bash
git clone https://github.com/S34L-Nhan/claude-desk.git ~/claude-desk
ln -s ~/claude-desk/bin/claude-desk ~/.local/bin/claude-desk   # put the launcher on PATH
claude-desk shortcut                                           # optional: Windows desktop shortcut
claude-desk                                                    # first start runs npm install
```

## Usage

```bash
claude-desk            # start the server if needed and open the window
claude-desk status     # is the server running, which sessions are running
claude-desk stop       # stop the server; asks first if sessions are running (--force: no question)
claude-desk restart
claude-desk serve      # run the server in the foreground, logs to the terminal
claude-desk url        # one-time login URL (valid for 60 s), e.g. for another browser
claude-desk shortcut   # create/update the "Claude Desk" shortcut on the Windows desktop
```

The window is an Edge app window (`msedge --app=…`): no address bar, and its own taskbar entry. If Edge is missing, Chrome is used.

The desktop shortcut runs `claude-desk app` via `conhost.exe --headless wsl.exe …`, so no console window appears. Its icon lives in `%LOCALAPPDATA%\claude-desk\claude-desk.ico`. `tools/make_icon.py` renders it from the same motif as `static/icon.svg`.

### Keeping WSL alive

WSL shuts down once no `wsl.exe` is left on the Windows side, and takes the server with it. So `claude-desk` keeps a hidden `wsl.exe` process open (`claude-desk keepalive`) while the server runs. After the server stops, it exits by itself within about 45 s. Only one runs at a time (lock in `~/.claude-desk/keepalive.lock`).

### Keys

| Key | Action |
|---|---|
| Ctrl+Shift+O | New chat |
| Ctrl+Shift+B | Toggle sidebar |
| Ctrl+Shift+F | Search chats |
| Ctrl+PgUp / Ctrl+PgDn | Switch tab |
| Shift+Enter | New line in the terminal (instead of sending) |
| Ctrl+C with a selection | Copy (without a selection: a normal Ctrl+C to the CLI) |
| Ctrl+V | Paste |
| Middle-click on a tab | Close tab |
| Tab key, then Enter | Open a chat or tab with the keyboard |
| F2 | Rename the selected chat or tab |

- **New chat**: pick a working directory (recently used ones are suggested) and optionally a title. The title goes to the CLI via `--name`.
- **Open an earlier chat**: shows the history first. *Fortsetzen* (resume) runs `claude --resume <id>` in the original working directory. If the chat already runs in another terminal, Claude Desk asks first.
- **Closing a tab** does not end the session. Use *Beenden* (stop) for that. The history is kept.

## How it works

- `desk/` is a small server built on the Python stdlib only (no pip). It listens on `127.0.0.1:47321`.
  - `terminals.py` starts each session with `pty.fork()` as the real `claude` CLI. Up to 2 MB of output is buffered, so a newly opened tab can rebuild the screen. Each tab gets its own send queue, so a slow tab never stalls a session.
  - `transcripts.py` reads the transcripts in `~/.claude/projects/*/*.jsonl`. Files are read incrementally; the index is cached in `~/.claude-desk/index.json`.
  - `registry.py` reads `~/.claude/sessions/<pid>.json`, where every running CLI reports its state (busy/idle/waiting).
  - `library.py` stores folders and the archive.
  - `ws.py` is a minimal WebSocket implementation for the terminal stream.
- `static/` is the frontend: vanilla JS, no build step. xterm.js, marked, DOMPurify and highlight.js come from `npm install` into `node_modules/` (`claude-desk` does this on first start) and are served locally.

### Titles

Titles set in Claude Desk are stored in `~/.claude-desk/titles.json` and take precedence there. Claude Desk also appends a `custom-title` entry to the transcript, exactly like `/rename` does, so `claude --resume` shows the new name too.

### Security

Whoever can reach the server can start terminals, so it is protected in several layers:

- **Localhost only:** it listens on `127.0.0.1` only.
- **Token cookie:** every request needs a token cookie (`HttpOnly`, `SameSite=Strict`). The token lives in `~/.claude-desk/token` (mode 0600).
- **One-time tickets:** `claude-desk` logs the window in with a ticket that is valid once and for 60 s only. The real token therefore never appears in a URL, the browser history or the process list.
- **Host and Origin checks:** foreign `Host` headers (DNS rebinding) and foreign `Origin` headers (other websites, WebSockets included) are rejected.
- **Content Security Policy:** scripts come only from the server itself, no external images, no embedding in other pages. Rendered histories also go through DOMPurify, without `<style>` and without form elements. So HTML injected into a transcript (e.g. from a fetched web page) cannot run anything.
- **Private data folder:** `~/.claude-desk` has mode 0700, because the index, titles and log quote your prompts.
- **Isolated sessions:** a session does not inherit the terminals of earlier sessions.

One limit comes from the browser: cookies do not distinguish ports, so other local services on `localhost` receive the cookie too. They cannot use it, because the Origin check rejects their requests.

### Data

| Path | Contents |
|---|---|
| `~/.claude-desk/server.log` | Server log |
| `~/.claude-desk/index.json` | Chat index cache (safe to delete) |
| `~/.claude-desk/titles.json` | Titles set in Claude Desk |
| `~/.claude-desk/library.json` | Folders and archived chats |
| `~/.claude-desk/token` | Login token of the window |

Port and paths can be changed with `CLAUDE_DESK_PORT`, `CLAUDE_DESK_HOME` and `CLAUDE_DESK_CLAUDE` (path to the CLI).

## Limitations

- Sessions live in the server process. `claude-desk stop`, `wsl --shutdown` or a Windows restart ends them. The history is kept, and *Fortsetzen* brings them back.
- If you switch sessions inside the CLI with `/clear` or `/resume`, the tab follows the new session id from the CLI's registry. This is not tested much yet.
- Pasting images from the clipboard does not work directly, as in any WSL terminal.
