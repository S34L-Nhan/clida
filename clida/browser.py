"""Open a link in the system's default browser.

The window is an Edge or Chrome app window, and a link opened from the page would land in that
browser, whatever the user's default is. So the page hands links to the server instead.
"""

import os
import subprocess
import sys
from urllib.parse import urlsplit

from . import locate

# Only these: other schemes start programs (ms-msdt:, search-ms:, file:) and a transcript can hold any link.
SCHEMES = ("http", "https", "mailto")


def allowed(url) -> bool:
    if not isinstance(url, str) or len(url) > 8192 or any(ch.isspace() or ord(ch) < 32 for ch in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in SCHEMES and (parts.scheme.lower() == "mailto" or bool(parts.netloc))


def open_url(url: str) -> bool:
    """Hand url to the default browser; False if that could not be started."""
    env = dict(os.environ)
    if locate.on_wsl():
        # The URL goes in through the environment: no quoting of & ' " for the command line.
        env.update(CLIDA_URL=url, WSLENV=":".join(filter(None, [env.get("WSLENV"), "CLIDA_URL"])))
        argv = [locate.POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", "Start-Process $env:CLIDA_URL"]
        cwd = "/mnt/c"
    else:
        argv = ["open" if sys.platform == "darwin" else "xdg-open", url]
        cwd = None
    try:
        done = subprocess.run(argv, env=env, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0
