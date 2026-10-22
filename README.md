# Claude Desk

Ein Desktop-Fenster für die Claude Code CLI, ähnlich wie Claude Desktop:

- **Seitenleiste** mit allen bisherigen Chats aus `~/.claude/projects`, gruppiert nach Datum (Heute, Gestern, Letzte 7 Tage …), mit Suche. Sie lässt sich ein- und ausklappen.
- **Chats umbenennen**: Stift-Symbol, Doppelklick auf den Titel in Liste oder Tab, oder Klick auf die Überschrift.
- **Hybrid-Ansicht** pro Chat:
  - *Verlauf*: der Chat als gerenderte Unterhaltung (Markdown, Tool-Aufrufe zusammengeklappt).
  - *Terminal*: die echte `claude` CLI im eingebetteten Terminal (xterm.js). Alles funktioniert wie gewohnt: Berechtigungsabfragen, Slash-Commands, Plan- und Auto-Mode.
- **Parallele Sessions**: Jede Session hat einen eigenen Tab und arbeitet im Hintergrund weiter, auch wenn ihr Tab geschlossen ist. Die Punkte zeigen den Zustand:
  - orange pulsierend = arbeitet
  - gelb = wartet auf dich (z.B. Berechtigung)
  - grün = bereit
  - Ring = läuft in einem anderen Terminal außerhalb von Claude Desk

  Ist eine Session im Hintergrund fertig, wird ihr Titel fett und der Fenstertitel zeigt `(n)`.

## Start

```bash
claude-desk            # Server starten (falls nötig) und Fenster öffnen
claude-desk status     # läuft der Server, welche Sessions laufen
claude-desk stop       # Server stoppen; fragt nach, wenn noch Sessions laufen (--force: ohne Rückfrage)
claude-desk restart
claude-desk serve      # Server im Vordergrund, Logs im Terminal
claude-desk url        # einmalige Login-URL (60 s gültig), z.B. für einen anderen Browser
claude-desk shortcut   # Verknüpfung „Claude Desk“ auf dem Windows-Desktop anlegen/aktualisieren
```

Das Fenster ist ein Edge-App-Fenster (`msedge --app=…`), also ohne Adressleiste und mit eigenem Taskleisten-Eintrag. Ist Edge nicht vorhanden, wird Chrome genutzt.

Die Desktop-Verknüpfung startet `claude-desk app` über `conhost.exe --headless wsl.exe …`, also ohne Konsolenfenster. Das Icon liegt unter `%LOCALAPPDATA%\claude-desk\claude-desk.ico`. `tools/make_icon.py` erzeugt es aus demselben Motiv wie `static/icon.svg`.

### WSL am Laufen halten

WSL fährt herunter, sobald auf Windows-Seite kein `wsl.exe` mehr läuft, und nimmt dabei den Server mit. Deshalb hält `claude-desk` einen unsichtbaren `wsl.exe`-Prozess offen (`claude-desk keepalive`), solange der Server läuft. Wird der Server gestoppt, beendet er sich nach spätestens ca. 45 s von selbst. Es läuft immer nur einer davon (Lock in `~/.claude-desk/keepalive.lock`).

## Bedienung

| Taste | Aktion |
|---|---|
| Strg+Umschalt+O | Neuer Chat |
| Strg+Umschalt+B | Seitenleiste ein/aus |
| Strg+Umschalt+F | Chats durchsuchen |
| Strg+Bild↑ / Strg+Bild↓ | Tab wechseln |
| Umschalt+Enter | Zeilenumbruch im Terminal (statt Absenden) |
| Strg+C mit Markierung | Kopieren (ohne Markierung: normales Strg+C an die CLI) |
| Strg+V | Einfügen |
| Mittelklick auf Tab | Tab schließen |

- **Neuer Chat**: Arbeitsverzeichnis wählen (zuletzt genutzte Verzeichnisse werden vorgeschlagen) und optional einen Titel angeben. Der Titel geht per `--name` an die CLI.
- **Früheren Chat öffnen**: zeigt zuerst den Verlauf. Mit *Fortsetzen* läuft `claude --resume <id>` im ursprünglichen Arbeitsverzeichnis. Läuft der Chat schon in einem anderen Terminal, fragt Claude Desk vorher nach.
- **Tab schließen** beendet die Session nicht. Dafür gibt es *Beenden*. Der Verlauf bleibt dabei erhalten.

## Wie es funktioniert

- `desk/` ist ein kleiner Server, nur mit der Python-Stdlib (kein pip). Er läuft auf `127.0.0.1:47321`.
  - `terminals.py` startet jede Session per `pty.fork()` als echte `claude`-CLI. Bis zu 2 MB Ausgabe werden gepuffert, damit ein neu geöffneter Tab den Bildschirm wieder aufbauen kann.
  - `transcripts.py` liest die Verläufe aus `~/.claude/projects/*/*.jsonl`. Die Dateien werden nur inkrementell gelesen, der Index liegt in `~/.claude-desk/index.json`.
  - `registry.py` liest `~/.claude/sessions/<pid>.json`. Dort meldet jede laufende CLI ihren Status (busy/idle/wartet).
  - `ws.py` ist eine minimale WebSocket-Implementierung für den Terminal-Stream.
- `static/` ist das Frontend: Vanilla-JS, ohne Build-Schritt. xterm.js, marked und DOMPurify kommen per `npm install` nach `node_modules/` (macht `claude-desk` beim ersten Start automatisch) und werden lokal ausgeliefert.

### Titel

Umbenannte Titel landen in `~/.claude-desk/titles.json` und haben in Claude Desk Vorrang. Zusätzlich hängt Claude Desk einen `custom-title`-Eintrag an das Transcript an, genau wie `/rename` es tut. Dadurch zeigt auch `claude --resume` den neuen Namen.

### Sicherheit

Wer den Server erreicht, kann Terminals starten. Deshalb ist er mehrfach abgesichert:

- **Nur localhost:** Er lauscht ausschließlich auf `127.0.0.1`.
- **Token-Cookie:** Jede Anfrage braucht ein Token-Cookie (`HttpOnly`, `SameSite=Strict`). Das Token liegt in `~/.claude-desk/token` (Rechte 0600).
- **Einmal-Tickets:** `claude-desk` meldet das Fenster mit einem Ticket an, das nur einmal und nur 60 s gilt. Das eigentliche Token taucht deshalb nie in einer URL, im Browser-Verlauf oder in der Prozessliste auf.
- **Host- und Origin-Prüfung:** Fremde `Host`-Header (DNS-Rebinding) und fremde `Origin`-Header (andere Webseiten, auch WebSockets) werden abgewiesen.
- **Content-Security-Policy:** Skripte kommen nur vom Server selbst, keine externen Bilder, kein Einbetten in fremde Seiten. Gerenderte Verläufe laufen zusätzlich durch DOMPurify, ohne `<style>` und ohne Formularelemente. Selbst eingeschleustes HTML in einem Verlauf (etwa aus einer abgerufenen Webseite) kann damit nichts ausführen.
- **Privater Datenordner:** `~/.claude-desk` hat die Rechte 0700, denn Index, Titel und Log zitieren deine Prompts.

Eine Einschränkung macht der Browser: Cookies unterscheiden nicht zwischen Ports. Andere lokale Dienste auf `localhost` bekommen das Cookie also mitgeschickt. Benutzen können sie es nicht, weil die Origin-Prüfung ihre Anfragen abweist.

### Daten

| Pfad | Inhalt |
|---|---|
| `~/.claude-desk/server.log` | Server-Log |
| `~/.claude-desk/index.json` | Cache des Chat-Index (darf gelöscht werden) |
| `~/.claude-desk/titles.json` | in Claude Desk vergebene Titel |
| `~/.claude-desk/token` | Login-Token des Fensters |

Port und Pfade lassen sich über `CLAUDE_DESK_PORT`, `CLAUDE_DESK_HOME` und `CLAUDE_DESK_CLAUDE` (Pfad zur CLI) ändern.

## Grenzen

- Die Sessions leben im Server-Prozess. `claude-desk stop`, `wsl --shutdown` oder ein Windows-Neustart beendet sie. Der Verlauf bleibt erhalten, und *Fortsetzen* holt sie zurück.
- Wechselt man innerhalb der CLI per `/clear` oder `/resume` die Session, übernimmt der Tab die neue Session-ID aus der Registry der CLI. Das ist noch nicht ausgiebig getestet.
- Bilder aus der Zwischenablage einfügen geht, wie in jedem WSL-Terminal, nicht direkt.
