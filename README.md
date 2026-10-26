# CLIDA

A desktop window for the Claude Code CLI, similar to Claude Desktop, for Windows (WSL) and macOS. Every chat has a rendered history, the real `claude` CLI in a terminal, and a merge-request view of what it changed.

The interface is in German (default) or English. Labels below are quoted in German with the English meaning.

## Install

You need Python 3.9+, the `claude` CLI, and a Chromium browser: Edge or Chrome on the Windows side for WSL; Chrome, Edge, Brave or Chromium on macOS (without one, CLIDA opens in a normal browser tab).

```bash
git clone https://github.com/S34L-Nhan/clida.git ~/clida && ~/clida/install.sh
clida
```

`install.sh` puts `clida` into `~/.local/bin`, fetches the frontend libraries (installing npm if it is missing) and offers a desktop shortcut. It is safe to run again.

## Features

### Chats

- **Sidebar**: all past chats from `~/.claude/projects`, grouped by date, with search.
- **Search**: finds chats by title, folder and first or last prompt. Tick *Erweiterte Suche* (advanced search) to search what was said in them too: every word of three or more letters must occur in one of your prompts or Claude's answers, in any case and also inside longer words. The first advanced search builds an index of all chats once, which can take a moment with a long history. With very many matches, the 300 chats with the newest ones are shown. A found chat shows the passage; a click opens it at that message, with the words marked.
- **Rename**: double-click a title, use the pencil icon, or click the heading.
- **Folders**: create one with the folder icon, then drag chats in and out. Right-click a folder to rename or delete it.
- **Archive and delete**: right-click a chat. *Archivieren* (archive) hides it but keeps it; *Löschen* (delete) removes it from disk for good, after asking.
- **Parallel sessions**: every session has its own tab and keeps running when the tab is closed. The dot shows its state: pulsing orange working, yellow waiting for you, green ready, ring running in a terminal outside CLIDA. A finished background session turns bold, and the window title shows `(n)`.
- **Cost**: the header shows what the chat has cost so far (hover for tokens), the sidebar shows today's total.

### Each chat

The switch in the header has three views:

- **Verlauf** (history): the conversation rendered as Markdown, with syntax-highlighted, copyable code. The slider sets the text width.
- **Terminal**: the real `claude` CLI. Everything works as usual: permission prompts, slash commands, plan mode.
- **Änderungen** (changes): see below.

**Fortsetzen** (resume) restarts a finished chat with `claude --resume`. **Beenden** (stop) ends a running one. Closing a tab does neither.

### Back to a message

Hover a message in the history for two more buttons next to the note icon:

- **Abzweigen** (fork): a new chat with the conversation up to that point starts in the terminal. From an answer it ends with that answer; from one of your prompts it ends just before it, and the prompt is typed in again, unsent, for you to change. The chat you forked from stays as it is.
- **Dateien zurücksetzen** (restore files), on your prompts: what Claude changed with Edit or Write from that prompt on goes back to how it was before, from the CLI's own checkpoints (what `/rewind` uses). Files it created are deleted; changes made by shell commands stay. Only while no CLI works in the chat's folder; this uses an option of the CLI that is not documented, so a future CLI may need an update of CLIDA.

Together they are the CLI's `/rewind`, without losing the conversation as it was.

### Changes

A merge-request view of everything the chat changed:

- **Files** on the left, as a tree or a list, grouped by git repository. Search with part of a path or a pattern like `*.vue` (press F to jump there).
- **Diffs** on the right, from before the chat to now, with line numbers. Commits made during the chat are listed on top.
- **Git state** per file: ✓ committed (with the commit), ● not committed, + staged, ± partly staged, ? untracked, ⊘ ignored. Files outside any repository, like Claude's memory, form their own group: they are never committed.
- **Comments**: click a line number, or drag over several lines, and write a question. *An Claude senden* (send to Claude) sends all comments to this chat's session as one message, with file, lines and code. If the chat is not running, CLIDA resumes it first.

Files come from two sources: Claude's Edit and Write calls, and the git repositories the chat worked in (which also catches shell commands and commits). Git cannot tell who changed a file, so other changes in the same repository during the chat show up too. Files over 512 KB and binary files get no diff.

### Worktrees

Tick *In eigenem Git-Worktree* (in its own git worktree) when you start a chat, and it works in a folder of its own inside the repository, where the CLI keeps its worktrees too: `<repo>/.claude/worktrees/<title>`. Parallel chats on one repository then never write into each other's files, and the changes view shows only that chat's work. If the repository does not ignore that folder yet, CLIDA adds `**/.claude/worktrees/` to its `.git/info/exclude` (local, unlike `.gitignore`).

The worktree takes one of two branches:

- **Neuer Branch clida/… von** (new branch from): a branch of its own, `clida/<title>`, from the base in the field. The field proposes the remote's default branch (`origin/HEAD`): the local branch of that name, or `origin/<name>` when the local one only lags behind it. Any local or remote branch goes; an empty field starts from where the repository stands. The new branch has no upstream.
- **Bestehender Branch** (existing branch): a branch there is already, such as a ticket's branch made in GitLab. One only a remote has gets a local branch that tracks it. A branch made on the remote after the last fetch shows after **Branches vom Remote holen (git fetch)**, under the fields or at the end of their list: CLIDA runs `git fetch --all` without a terminal, so a remote that would ask for a login fails with git's message. Git gives a branch to one worktree only, so a branch checked out elsewhere shows greyed out and cannot be taken.

In the chat:

- A bar under the header shows the branch, how many commits it is ahead of its base, and what is not committed yet.
- **In … mergen** (merge into …) merges a `clida/…` branch into its base, where that is checked out. It refuses while changes in the worktree are not committed; a conflict aborts the merge and leaves everything as it was. A remote base and an existing branch have no merge button: they go by push and merge request.
- **Worktree entfernen** (remove worktree) deletes the folder once no session works in it, and the branch if CLIDA made it; an existing branch stays. The history stays; the question names any commits that would be lost.
- A chat that runs in its repository without a worktree can get one later, once the ticket and its branch are there: the branch button in its header (**In eigenen Worktree verschieben**, move into a worktree of its own) offers the same two branches. CLIDA makes the worktree and types a request into the session to switch in with the CLI's `EnterWorktree` tool, only while the CLI is idle. The CLI moves the transcript to the worktree's project and goes on there, also when the chat is resumed later; until it has switched, the bar says the session still works in the repository. Uncommitted changes stay in the repository.
- A chat that goes on under a new id (`/clear`, `/resume`) and a fork of the chat work in the same worktree and show the same bar. Deleting the chat hands the worktree to one of them; a chat that holds its worktree alone asks first, as without it CLIDA could not reach the worktree any more.

Files git does not track (`.env`, `node_modules`) are not in a new worktree, and the CLI asks once whether you trust the new folder. On WSL, keep such repositories in the Linux file system: a worktree made from `/mnt/c/...` works in WSL, but Windows git and IDEs cannot use it, and checking out there is slow.

### Notes

Private notes that Claude never sees:

- **Session note**: the note icon in the header, e.g. "waiting for review of MR 4027". It shows under the header and in the sidebar.
- **Message notes**: hover a message and click its note icon.

Both are Markdown. Pasting rendered text keeps lists, bold and code (converter from Pablo Oliva's [Session Notes plugin for bb](https://github.com/pablooliva/bb-ide-session-notes-plugin), MIT).

### Attachments

- **Ctrl+V** (⌘V on a Mac) pastes a screenshot into the terminal, as in the plain CLI.
- **Drop a file** on the terminal, or use the paperclip. CLIDA copies it to `~/.clida/uploads/` and pastes the path (browsers never reveal the original path). Up to 50 MB.
- **Drop a folder** and CLIDA pastes its real path, after finding it in the open Explorer/Finder windows or in Desktop, Downloads and Documents.

### Settings

*Einstellungen* (settings) at the bottom of the sidebar. Changes apply at once.

- **Sprache** (language): German or English. Claude still answers in the language you write in.
- **Benachrichtigungen** (notifications): while CLIDA is not in front, a system notification when a session waits for you, and by default also when one is done. A click on it opens the chat. They need a CLI that reports its state (any recent one). The browser asks on your first click whether CLIDA may show them (a dismissed question comes again a few times); on Windows they appear in the notification center (unless Focus Assist holds them back).
- **Farbschema** (color theme): System, light, dark, Solarized, Catppuccin, Nord, Dracula, Gruvbox and Tokyo Night. It colors the terminal too. Set the CLI's own theme once with `/theme` to *Auto (match terminal)*.
- **Diff-Farben** (diff colors): how strongly added and removed lines are tinted, from subtle to very strong. Comments and selected lines have their own color.

The tab **Tastenkürzel** (keyboard shortcuts) lists CLIDA's own shortcuts and the Claude CLI's, each with its keys now. *Ändern* (change) waits for the new key (Esc gives up), the arrow next to it goes back to the default, and nothing is stored before *Speichern* (save). A key taken twice is shown and cannot be saved; keys that never reach the CLI (Ctrl+C, the Windows or ⌘ key, a key CLIDA takes itself) are refused or marked. The CLI's shortcuts go to `~/.claude/keybindings.json`, which every running session reads again at once; what else that file holds stays. A handy one: *Eingabe beiseitelegen* (stash) on Ctrl+A empties the input in one go, and a second press brings the text back.

## Commands

```bash
clida            # open the window (starts the server if needed)
clida status     # is the server running, and which sessions
clida stop       # stop the server (asks if sessions are running; --force skips that)
clida restart    # stop and start; an open window reloads by itself
clida update     # pull the newest version of the current branch and restart
clida serve      # run the server in the foreground with logs
clida url        # a one-time login link (60 s) for another browser
clida shortcut   # create the desktop shortcut again
```

A restart or update ends running sessions, so both ask first. Their history is kept, and *Fortsetzen* brings them back.

## Keys

The defaults; CLIDA's own can be changed in the settings (see above).

| Windows (WSL) | macOS | Action |
|---|---|---|
| Ctrl+Shift+O | ⌘⇧O | New chat |
| Ctrl+Shift+B | ⌘⇧B | Toggle sidebar |
| Ctrl+Shift+F | ⌘⇧F | Search chats |
| Ctrl+PgUp / PgDn | ⌘⌥← / → | Switch tab |
| Shift+Enter | ⇧↩ | New line in the terminal |
| Ctrl+C with a selection | ⌘C | Copy (without a selection, Ctrl+C goes to the CLI) |
| F2 | F2 | Rename the selected chat or tab |
| F5 | F5 | Reload the window (open notes are saved first) |
| Middle-click a tab | Middle-click a tab | Close it |

Tabs can be reordered by dragging. Browser shortcuts that make no sense in an app (print, save, history, back/forward, developer tools) are switched off outside the terminal; in the terminal those keys go to the CLI as usual.

## Limitations

- Sessions live in the server. `clida stop`, `wsl --shutdown` or a reboot ends them; resume them afterwards.
- On WSL with NAT networking, Windows reaches CLIDA through WSL's localhost relay, which sometimes hangs. CLIDA detects this and says so; `wsl --shutdown` fixes it. Mirrored networking (`networkingMode=mirrored` in `.wslconfig`) avoids the relay.
- Dropped files are copies, so Claude's edits to them do not reach the original. For project files, use `@` in the CLI.
- macOS support has only been tested in a simulation, not on a real Mac.

## For developers

### Layout

- `clida/`: the server, Python stdlib only. It listens on `127.0.0.1:47321`.
  - `terminals.py` runs each session as the real `claude` CLI in a pty.
  - `transcripts.py` indexes the transcripts in `~/.claude/projects/` incrementally, sums tokens and cost, finds the files each chat edited, and copies a chat up to a message for a fork.
  - `search.py` keeps the full-text index of all prompts and answers (SQLite FTS5 with trigrams), read on incrementally like the chat index.
  - `gitrepo.py` adds what changed in the chat's git repositories. Every git call uses `--no-optional-locks`, so it never blocks Claude's own commits.
  - `registry.py` reads the state each running CLI reports in `~/.claude/sessions/`.
  - `worktrees.py` makes, merges and removes the worktrees of chats started in one, and lists the branches the new-chat dialog offers.
  - `keybindings.py` reads and writes the shortcuts: CLIDA's own and the CLI's `~/.claude/keybindings.json`, with the CLI actions the settings list and their defaults.
  - `library.py` (folders, archive), `notes.py`, `settings.py`, `ws.py` (WebSocket for the terminal).
- `static/`: the frontend, plain JavaScript without a build step. `i18n.js` holds all texts in both languages. `tick.js` is a worker that times the status poll, so a minimized window still notices a session that waits.
- `bin/clida`: the launcher, plain bash that also runs on macOS's bash 3.2.

### Adding a setting

1. Allowed values and default in `SCHEMA` (`clida/settings.py`).
2. Control and effect in `SETTINGS` (`static/app.js`).
3. Texts in `static/i18n.js`.

A new color theme is one block in `static/themes.css`, its name in `THEMES` (`static/app.js`) and its id in `SCHEMA`.

### Security

Anyone who reaches the server can start terminals, so:

- it only listens on `127.0.0.1`;
- every request needs a token cookie (`HttpOnly`, `SameSite=Strict`), and the window logs in with a one-time ticket, so the token never appears in a URL;
- foreign `Host` and `Origin` headers are rejected (DNS rebinding, other websites);
- a Content Security Policy allows only the server's own scripts, and rendered histories go through DOMPurify, so HTML in a transcript cannot run anything;
- `~/.clida` is private (mode 0700), since the index and log quote your prompts.

### Data

Everything CLIDA stores is in `~/.clida`: settings, its own keyboard shortcuts, titles, folders, notes, which chat has which worktree, the chat index and the search index (caches, safe to delete), uploads and the server log. The worktrees themselves live in their repositories, in `.claude/worktrees/` (before, next to them in `<repo>.worktrees/`, where older ones stay). A fork is a new transcript in `~/.claude/projects/` next to its original, with a copy of the original's file backups in `~/.claude/file-history/`. Shortcuts for the CLI are saved in its own `~/.claude/keybindings.json`. A file that cannot be read is moved aside as `<name>.corrupt-<time>` instead of being overwritten.

`CLIDA_PORT`, `CLIDA_HOME` and `CLIDA_CLAUDE` (path to the CLI) change the port and paths.
