"""The euro rate for the cost figures: the CLI reports cost in US dollars, the window shows euros.

The rate is the ECB's daily reference rate, fetched in the background at most once every 12 hours
and kept in ~/.clida/rate.json, so the window never waits for the network and works offline.
"""

import re
import threading
import time
import urllib.request

from . import STATE_DIR, storage

RATE_FILE = STATE_DIR / "rate.json"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
REFRESH = 12 * 3600
RETRY = 15 * 60  # after a failed fetch (offline), so not every poll of the window tries again
FALLBACK = {"eur_per_usd": 0.89, "date": None}  # until the first fetch works; ECB 2026-10-23: 1 € = 1.1193 $

_USD = re.compile(r"""<Cube\s+currency=['"]USD['"]\s+rate=['"]([0-9.]+)['"]""")
_DATE = re.compile(r"""<Cube\s+time=['"](\d{4}-\d\d-\d\d)['"]""")


def _valid(data) -> bool:
    return isinstance(data, dict) and isinstance(data.get("eur_per_usd"), (int, float)) and data["eur_per_usd"] > 0


class Rates:
    def __init__(self):
        self._lock = threading.Lock()
        self._rate = storage.load(RATE_FILE, _valid)
        self._next_try = 0.0
        self._fetching = False

    def current(self) -> dict:
        """{"eur_per_usd", "date"}: the latest known rate (date None: the fallback); refreshes when due."""
        with self._lock:
            rate = self._rate or FALLBACK
            due = time.time() - (self._rate or {}).get("fetched", 0) > REFRESH and time.monotonic() >= self._next_try
            if due and not self._fetching:
                self._fetching = True
                threading.Thread(target=self._fetch, name="rate-fetch", daemon=True).start()
        return {"eur_per_usd": rate["eur_per_usd"], "date": rate["date"]}

    def _fetch(self):
        try:
            with urllib.request.urlopen(ECB_URL, timeout=10) as res:
                text = res.read(200_000).decode("utf-8", "replace")
            usd, day = _USD.search(text), _DATE.search(text)
            if not usd or not day or float(usd.group(1)) <= 0:
                raise ValueError("no USD rate in the ECB feed")
            rate = {"eur_per_usd": round(1 / float(usd.group(1)), 6), "date": day.group(1), "fetched": time.time()}
            storage.save(RATE_FILE, rate)
            with self._lock:
                self._rate = rate
        except (OSError, ValueError):
            with self._lock:
                self._next_try = time.monotonic() + RETRY  # keep the last rate; try again later
        finally:
            with self._lock:
                self._fetching = False
