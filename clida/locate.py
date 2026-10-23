"""Find a folder that was dropped into a tab.

A browser gives a dropped folder's name and contents, never where it lives. So look where it
was most likely dragged from: the open Explorer windows (WSL) or Finder windows (macOS), then
the Desktop, Downloads and Documents. The contents decide between folders of the same name.
"""

import base64
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
# Paths go out as base64: PowerShell's console output mangles umlauts on their way into WSL.
_EXPLORER = r"""
$shell = New-Object -ComObject Shell.Application
$paths = @(foreach ($w in $shell.Windows()) { try { $w.Document.Folder.Self.Path } catch {} })
$paths += [Environment]::GetFolderPath('Desktop')
$paths += $shell.NameSpace('shell:Downloads').Self.Path
$paths += [Environment]::GetFolderPath('MyDocuments')
$paths | Where-Object { $_ } | ForEach-Object { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($_)) }
"""
_FINDER = """tell application "Finder"
  set out to ""
  repeat with w in Finder windows
    try
      set out to out & POSIX path of (target of w as alias) & linefeed
    end try
  end repeat
  return out
end tell"""


def on_wsl() -> bool:
    return bool(os.environ.get("WSL_DISTRO_NAME")) and os.path.exists(POWERSHELL)


def _output(argv, cwd=None) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=10, cwd=cwd).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _explorer_folders() -> list:
    found = []
    for line in _output([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", _EXPLORER], cwd="/mnt/c").split():
        try:
            windows_path = base64.b64decode(line).decode()
        except ValueError:
            continue
        # C:\... becomes /mnt/c/..., \\wsl.localhost\<distro>\... becomes /...; a search window has no path.
        path = _output(["wslpath", "-u", windows_path]).strip()
        if path.startswith("/"):
            found.append(path)
    return found


def places() -> list:
    """Folders that probably hold the dropped one, most likely first."""
    if on_wsl():
        found = _explorer_folders()
    elif sys.platform == "darwin":
        found = [line for line in _output(["osascript", "-e", _FINDER]).splitlines() if line.startswith("/")]
    else:
        found = []
    home = Path.home()
    found += [str(home / name) for name in ("Desktop", "Downloads", "Documents")]
    return list(dict.fromkeys(os.path.normpath(path) for path in found))


def find(name: str, entries: list, where=None):
    """The folder called name in one of the places, or None.

    entries: what the browser listed inside it. With several candidates the one holding the most
    of them wins; one holding fewer than 90 % of them is a different folder of the same name.
    """
    nfc = lambda names: {unicodedata.normalize("NFC", n) for n in names}  # macOS may store names decomposed
    wanted = nfc(entries)
    best, best_share = None, 0.0
    for place in places() if where is None else where:
        candidate = os.path.join(place, name)
        try:
            present = nfc(os.listdir(candidate))
        except OSError:
            continue  # not there, or not a folder
        share = len(wanted & present) / len(wanted) if wanted else 1.0
        if share > best_share:
            best, best_share = candidate, share
    return best if best_share >= 0.9 else None
