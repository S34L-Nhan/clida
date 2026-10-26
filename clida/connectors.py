"""The accesses Claude reaches other services with, besides its own login: the GitLab tokens glab
holds, the GitHub accounts of Git Credential Manager and the CLI's MCP servers (the claude.ai
connectors among them, Jira through Atlassian's). The settings list them with their scopes, renew
and revoke them.

Tokens stay in the server: the page gets names, scopes and dates only.
"""

import datetime
import fcntl
import json
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import termios
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote

from . import browser, locate
from .settings import tr
from .terminals import child_env
from .transcripts import strip_ansi

TIMEOUT = 30  # seconds for a call that needs no one at the browser
LOGIN_TIMEOUT = 300  # seconds a login may wait for the user to finish it in the browser
CLAUDE_AI_CONNECTORS = "https://claude.ai/customize/connectors"  # where claude.ai connectors are disconnected
GITLAB_LIFETIME_MAX = 365  # days; GitLab's default limit for a token's lifetime
GCM_GITHUB_APP = "0120e057bd645470c1ed"  # Git Credential Manager's OAuth app on GitHub
_URL = re.compile(r"https?://[^\s\x07\x1b\"'<>]+")
_MCP_LINE = re.compile(r"(?P<name>.+?): (?P<target>.*) - (?P<mark>[^\w\s])\ufe0f? (?P<status>.+)")
_MCP_STATES = {"✔": "connected", "!": "auth", "✗": "failed", "⏸": "pending"}
_GLAB_ENV_TOKENS = ("GITLAB_TOKEN", "GITLAB_ACCESS_TOKEN", "OAUTH_TOKEN")  # would win over the stored token


class ConnectorError(Exception):
    pass


def _run(argv, stdin=None, env=None, timeout=TIMEOUT, cwd=None):
    """(exit code, stdout, stderr) of a program; ConnectorError if it does not run or answer."""
    try:
        done = subprocess.run(argv, input=stdin, capture_output=True, text=True, env=env, timeout=timeout, cwd=cwd)
    except FileNotFoundError:
        raise ConnectorError(tr(f"{argv[0]} ist nicht installiert", f"{argv[0]} is not installed"))
    except OSError as e:
        raise ConnectorError(str(e))
    except subprocess.TimeoutExpired:
        raise ConnectorError(tr(f"{os.path.basename(argv[0])} hat nach {timeout} s nicht geantwortet",
                                f"{os.path.basename(argv[0])} did not answer within {timeout} s"))
    return done.returncode, done.stdout, done.stderr


def _said(*texts) -> str:
    """The last line a program said, for an error message."""
    for text in texts:
        lines = [line.strip() for line in strip_ansi(text or "").splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return ""


# -- GitLab: glab's tokens ---------------------------------------------------------------------

_glab_lock = threading.Lock()  # one change of a token at a time


def _glab_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _GLAB_ENV_TOKENS}


def _glab_config() -> Path:
    if os.environ.get("GLAB_CONFIG_DIR"):
        return Path(os.environ["GLAB_CONFIG_DIR"]) / "config.yml"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "glab-cli" / "config.yml"


def _glab_hosts() -> list:
    """The hosts in glab's config, in its order. glab writes the file itself, so a look at the
    indentation under hosts: is enough."""
    try:
        lines = _glab_config().read_text().splitlines()
    except OSError:
        return []
    hosts, inside, indent = [], False, None
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        depth = len(line) - len(line.lstrip())
        if depth == 0:
            inside = text == "hosts:"
        elif inside:
            indent = indent or depth
            if depth == indent and text.endswith(":"):
                hosts.append(text[:-1].strip("'\""))
    return hosts


def _glab_token(host: str) -> str:
    code, out, _ = _run(["glab", "config", "get", "token", "--host", host], env=_glab_env())
    return out.strip() if code == 0 else ""


def _glab_api(host: str, path: str, *args, token: str = None):
    """GitLab's answer to an API call through glab, parsed; ConnectorError with GitLab's message.
    token: use this one instead of the stored one."""
    env = _glab_env()
    if token:
        env["GITLAB_TOKEN"] = token
    code, out, err = _run(["glab", "api", "--hostname", host, *args, path], env=env)
    if code != 0:
        raise ConnectorError(_said(err, out).removeprefix("glab: ") or f"glab exit {code}")
    try:
        return json.loads(out) if out.strip() else None
    except ValueError:
        raise ConnectorError(tr("GitLab gab keine lesbare Antwort", "GitLab gave no readable answer"))


def _unauthorized(error: ConnectorError) -> bool:
    return "401" in str(error)


def gitlab() -> dict:
    if not shutil.which("glab"):
        return {"available": False}
    accounts = []
    for host in _glab_hosts():
        row = {"host": host, "signed_in": False,
               "new_token_url": f"https://{host}/-/user_settings/personal_access_tokens?name=glab&scopes=api,write_repository"}
        accounts.append(row)
        if not _glab_token(host):
            continue
        row["signed_in"] = True
        try:
            row["user"] = (_glab_api(host, "user") or {}).get("username")
        except ConnectorError as e:
            row["error"] = str(e)
            row["invalid"] = _unauthorized(e)
            continue
        try:
            pat = _glab_api(host, "personal_access_tokens/self") or {}
        except ConnectorError:
            continue  # an OAuth token (glab auth login --web): no details to show, nothing to rotate
        row["token"] = {key: pat.get(key) for key in ("name", "scopes", "expires_at", "created_at", "last_used_at")}
    return {"available": True, "accounts": accounts}


def _lifetime(pat: dict) -> int:
    """Days the renewed token gets: as long as the old one had, at most what GitLab allows."""
    try:
        created = datetime.date.fromisoformat(pat["created_at"][:10])
        days = (datetime.date.fromisoformat(pat["expires_at"]) - created).days
    except (KeyError, TypeError, ValueError):
        return GITLAB_LIFETIME_MAX
    return min(max(days, 1), GITLAB_LIFETIME_MAX)


def _glab_store(host: str, token: str):
    code, out, err = _run(["glab", "auth", "login", "--hostname", host, "--stdin"], stdin=token + "\n", env=_glab_env())
    if code != 0 or _glab_token(host) != token:
        raise ConnectorError(_said(err, out) or f"glab exit {code}")


def gitlab_renew(body: dict) -> dict:
    """Rotate the token: GitLab revokes it and makes a new one with the same scopes. glab and git's
    plain-text store then get the new one, so running sessions go on with it at once."""
    host = _gitlab_host(body)
    with _glab_lock:
        old = _glab_token(host)
        if not old:
            raise ConnectorError(tr(f"glab hat keinen Token für {host}", f"glab has no token for {host}"))
        pat = _glab_api(host, "personal_access_tokens/self") or {}
        expires = (datetime.date.today() + datetime.timedelta(days=_lifetime(pat))).isoformat()
        new = (_glab_api(host, "personal_access_tokens/self/rotate", "-X", "POST", "-f", f"expires_at={expires}") or {})
        token = new.get("token")
        if not token:
            raise ConnectorError(tr("GitLab hat keinen neuen Token geschickt", "GitLab sent no new token"))
        try:
            _glab_store(host, token)
        except ConnectorError as e:
            # The old token is gone already: without this one the user would be locked out.
            raise ConnectorError(tr(f"GitLab hat den Token erneuert, glab konnte ihn aber nicht speichern ({e}). "
                                    f"Bitte selbst eintragen (glab auth login --hostname {host} --stdin): {token}",
                                    f"GitLab renewed the token, but glab could not store it ({e}). "
                                    f"Please store it yourself (glab auth login --hostname {host} --stdin): {token}"))
        _swap_stored_credential(host, old, token)
    return {"expires_at": new.get("expires_at") or expires}


def gitlab_revoke(body: dict) -> dict:
    """Revoke the token on GitLab, then remove it from glab and git's plain-text store. local: only
    remove it here, for an OAuth sign-in (glab auth login --web), which is no personal token."""
    host = _gitlab_host(body)
    with _glab_lock:
        old = _glab_token(host)
        if not old:
            raise ConnectorError(tr(f"glab hat keinen Token für {host}", f"glab has no token for {host}"))
        was_valid = not body.get("local")
        try:
            if was_valid:
                _glab_api(host, "personal_access_tokens/self", "-X", "DELETE")
        except ConnectorError as e:
            if not _unauthorized(e):
                raise
            was_valid = False  # expired or revoked already: only the copies here are left to remove
        code, out, err = _run(["glab", "auth", "logout", "--hostname", host], env=_glab_env())
        if code != 0 or _glab_token(host):
            raise ConnectorError(tr("Auf GitLab widerrufen, aber glab hat ihn behalten: ",
                                    "Revoked on GitLab, but glab kept it: ") + (_said(err, out) or f"exit {code}"))
        _swap_stored_credential(host, old, None)
    return {"was_valid": was_valid}


def gitlab_signin(body: dict) -> dict:
    """Store a token made on GitLab's page, once GitLab accepts it."""
    host = _gitlab_host(body)
    token = str(body.get("token") or "").strip()
    if not token or len(token) > 512 or any(ch.isspace() or ord(ch) < 32 for ch in token):
        raise ConnectorError(tr("Das ist kein Token", "That is not a token"))
    with _glab_lock:
        try:
            user = (_glab_api(host, "user", token=token) or {}).get("username")
        except ConnectorError as e:
            raise ConnectorError(tr("GitLab nimmt den Token nicht an: ", "GitLab does not accept the token: ") + str(e))
        _glab_store(host, token)
    return {"user": user}


def _gitlab_host(body: dict) -> str:
    host = body.get("host")
    if host not in _glab_hosts():
        raise ConnectorError(tr("Diesen Host kennt glab nicht", "glab does not know this host"))
    return host


# git's plain-text store (credential.helper = store) keeps a copy of every password git used, so
# also glab's token. The copy goes with it: renewed, it is the new one; revoked, it is removed.

def _credential_files() -> list:
    xdg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return [path for path in (Path.home() / ".git-credentials", xdg / "git" / "credentials") if path.is_file()]


_STORED = re.compile(r"(?P<head>[a-z][a-z0-9+.-]*://[^:@/\s]*):(?P<password>[^@/\s]*)@(?P<rest>.*)")


def _host_of(rest: str) -> str:
    """The host of what follows the @ in a stored URL: host[:port][/path]."""
    return rest.split("/", 1)[0].rsplit(":", 1)[0].lower()


def _swap_stored_credential(host: str, old: str, new):
    """Put new in place of old for host in git's plain-text store, or drop those lines (new None).
    Written through git's own lock file, so a git that stores a password meanwhile waits or fails."""
    for path in _credential_files():
        lines = path.read_text().splitlines(keepends=True)
        kept, changed = [], False
        for line in lines:
            match = _STORED.fullmatch(line.rstrip("\n"))
            if match and _host_of(match["rest"]) == host and unquote(match["password"]) == old:
                changed = True
                if new is None:
                    continue
                line = f"{match['head']}:{quote(new, safe='')}@{match['rest']}\n"
            kept.append(line)
        if not changed:
            continue
        lock = path.with_name(path.name + ".lock")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ConnectorError(tr(f"{path} ist gerade gesperrt ({lock.name}); bitte noch einmal versuchen",
                                    f"{path} is locked right now ({lock.name}); please try again"))
        try:
            with os.fdopen(fd, "w") as f:
                f.write("".join(kept))
                f.flush()
                os.fsync(f.fileno())
            os.replace(lock, path)
        finally:
            lock.unlink(missing_ok=True)


# -- GitHub: the accounts of Git Credential Manager ----------------------------------------------

def _gcm():
    """Git Credential Manager, if git uses it for github.com: its path, or None."""
    code, out, _ = _run(["git", "config", "--get-urlmatch", "credential.helper", "https://github.com"])
    helper = out.strip().strip("'\"").replace("\\ ", " ") if code == 0 else ""
    if helper in ("manager", "manager-core"):
        return shutil.which("git-credential-manager") or shutil.which("git-credential-manager-core")
    name = os.path.basename(helper).removesuffix(".exe")
    if name in ("git-credential-manager", "git-credential-manager-core"):
        return helper if os.path.isfile(helper) else shutil.which(helper)
    return None


def _gcm_run(gcm: str, *args, stdin="", interactive=False, timeout=TIMEOUT):
    """GCM never asks anything unless interactive: then it may show its own window."""
    env = dict(os.environ, GCM_INTERACTIVE="auto" if interactive else "never")
    cwd = None
    if gcm.endswith(".exe") and locate.on_wsl():  # a Windows program: it sees only variables named in WSLENV
        env["WSLENV"] = ":".join(filter(None, [env.get("WSLENV"), "GCM_INTERACTIVE"]))
        cwd = "/mnt/c"
    return _run([gcm, *args], stdin=stdin, env=env, timeout=timeout, cwd=cwd)


def github() -> dict:
    gcm = _gcm()
    if not gcm:
        return {"available": False}
    code, out, err = _gcm_run(gcm, "github", "list")
    if code != 0:
        raise ConnectorError(_said(err, out) or f"git-credential-manager exit {code}")
    accounts = []
    for user in [line.strip() for line in out.splitlines() if line.strip()]:
        row = {"user": user}
        accounts.append(row)
        # The token only to ask GitHub what it may do.
        code, out, err = _gcm_run(gcm, "get", stdin=f"protocol=https\nhost=github.com\nusername={user}\n\n")
        token = dict(line.split("=", 1) for line in out.splitlines() if "=" in line).get("password") if code == 0 else None
        if not token:
            row["error"] = _said(err) or tr("Kein Token gespeichert", "No token stored")
            continue
        request = urllib.request.Request("https://api.github.com/user", headers={
            "Authorization": f"token {token}", "User-Agent": "clida", "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(request, timeout=15) as answer:
                headers = answer.headers
                row["login"] = json.load(answer).get("login")
        except urllib.error.HTTPError as e:
            row["error"] = f"GitHub: {e.code} {e.reason}"
            row["invalid"] = e.code == 401
            continue
        except (urllib.error.URLError, OSError, ValueError) as e:
            row["error"] = f"GitHub: {getattr(e, 'reason', e)}"
            continue
        scopes = headers.get("X-OAuth-Scopes")
        row["scopes"] = [s.strip() for s in scopes.split(",") if s.strip()] if scopes is not None else None
        row["app"] = "gcm" if headers.get("X-OAuth-Client-Id") == GCM_GITHUB_APP else None
        row["expires_at"] = headers.get("GitHub-Authentication-Token-Expiration")
    return {"available": True, "accounts": accounts, "apps_url": "https://github.com/settings/applications"}


def github_renew(body: dict) -> dict:
    """Sign in again (or for the first time): GCM shows its own window or opens the browser."""
    gcm = _require_gcm()
    user = body.get("user")
    args = ["github", "login"]
    if user:
        args += ["--username", _github_user(user), "--force"]
    code, out, err = _gcm_run(gcm, *args, interactive=True, timeout=LOGIN_TIMEOUT)
    if code != 0:
        raise ConnectorError(_said(err, out) or f"git-credential-manager exit {code}")
    return {}


def github_revoke(body: dict) -> dict:
    """Remove the account from GCM. GitHub keeps the app's grant; that is revoked on GitHub."""
    gcm = _require_gcm()
    code, out, err = _gcm_run(gcm, "github", "logout", _github_user(body.get("user")))
    if code != 0:
        raise ConnectorError(_said(err, out) or f"git-credential-manager exit {code}")
    return {}


def _require_gcm() -> str:
    gcm = _gcm()
    if not gcm:
        raise ConnectorError(tr("git nutzt für github.com keinen Git Credential Manager",
                                "git does not use Git Credential Manager for github.com"))
    return gcm


def _github_user(user) -> str:
    if not isinstance(user, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", user):
        raise ConnectorError(tr("Ungültiger GitHub-Name", "Invalid GitHub name"))
    return user


# -- MCP servers, the claude.ai connectors among them --------------------------------------------

_mcp_logins = set()  # servers a login runs for now
_mcp_lock = threading.Lock()


def mcp(claude: str) -> dict:
    """Every MCP server the CLI has outside a project, with what its health check says."""
    code, out, err = _run([claude, "mcp", "list"], env=child_env(), cwd=str(Path.home()), timeout=90)
    if code != 0:
        raise ConnectorError(_said(err, out) or f"claude exit {code}")
    servers = []
    for line in strip_ansi(out).splitlines():
        match = _MCP_LINE.fullmatch(line.strip())
        if not match:
            continue
        name, target = match["name"], match["target"]
        kind = "claudeai" if name.startswith("claude.ai ") else "remote" if re.match(r"https?://", target) else "local"
        servers.append({"name": name, "target": target, "kind": kind,
                        "state": _MCP_STATES.get(match["mark"], "other"), "status": match["status"]})
    return {"servers": servers, "manage_url": CLAUDE_AI_CONNECTORS}


def mcp_renew(claude: str, body: dict) -> dict:
    """claude mcp login: for a claude.ai connector, it makes a link to authorize it on claude.ai; for
    another server, it runs the OAuth sign-in and waits for its callback. The link goes to the
    browser from here. The CLI wants a terminal for the second, so it gets one."""
    name = _mcp_name(body)
    with _mcp_lock:
        if name in _mcp_logins:
            raise ConnectorError(tr("Diese Anmeldung läuft schon", "This sign-in is already running"))
        _mcp_logins.add(name)
    try:
        code, said, url = _login_in_pty([claude, "mcp", "login", name, "--no-browser"])
    finally:
        with _mcp_lock:
            _mcp_logins.discard(name)
    if code != 0:
        raise ConnectorError(said or f"claude exit {code}")
    return {"url": url, "claudeai": name.startswith("claude.ai ")}


def mcp_revoke(claude: str, body: dict) -> dict:
    """claude mcp logout: revokes and forgets a server's tokens. claude.ai keeps its connectors' own."""
    name = _mcp_name(body)
    if name.startswith("claude.ai "):
        raise ConnectorError(tr("claude.ai-Konnektoren werden auf claude.ai getrennt",
                                "claude.ai connectors are disconnected on claude.ai"))
    code, out, err = _run([claude, "mcp", "logout", name], env=child_env(), cwd=str(Path.home()))
    if code != 0:
        raise ConnectorError(_said(err, out) or f"claude exit {code}")
    return {}


def _mcp_name(body: dict) -> str:
    name = body.get("name")
    if not isinstance(name, str) or not name or name.startswith("-") or len(name) > 200 \
            or any(ord(ch) < 32 for ch in name):
        raise ConnectorError(tr("Ungültiger Servername", "Invalid server name"))
    return name


def _login_in_pty(argv):
    """(exit code, its last line, the first link it printed) of a login run in a terminal of its own.
    The link goes to the browser as soon as it shows."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 4000, 0, 0))  # wide: no link broken over lines
    try:
        proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, env=child_env(), cwd=str(Path.home()),
                                start_new_session=True)
    except OSError as e:
        os.close(master)
        raise ConnectorError(str(e))
    finally:
        os.close(slave)
    output, url, deadline = b"", None, time.monotonic() + LOGIN_TIMEOUT
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise ConnectorError(tr(f"Nach {LOGIN_TIMEOUT // 60} Minuten ohne Anmeldung abgebrochen",
                                        f"Stopped after {LOGIN_TIMEOUT // 60} minutes without a sign-in"))
            if not select.select([master], [], [], min(left, 1))[0]:
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError:  # EIO: the CLI has ended and closed its terminal
                break
            if not chunk:
                break
            output += chunk
            if url is None:
                found = _URL.search(output.decode("utf-8", "replace"))
                if found and not output.endswith(found.group().encode()):  # whole: something follows it
                    url = found.group()
                    if not browser.open_url(url):
                        raise ConnectorError(tr("Der Browser ließ sich nicht öffnen. Link: ",
                                                "The browser did not open. Link: ") + url)
        code = proc.wait(10)
    except subprocess.TimeoutExpired:  # closed its terminal but did not end
        code = None
    finally:
        os.close(master)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)  # with whatever it started
            proc.wait()
    return code, _said(output.decode("utf-8", "replace")), url
