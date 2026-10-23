"""The JSON files in ~/.clida that hold what the user made: titles, folders, notes, settings."""

import json
import os
import sys
import time


def load(path, valid=lambda data: isinstance(data, dict)):
    """The data in path, or None when there is none yet.

    A file that does not parse (or has the wrong shape) is moved aside, not overwritten by the
    next save, so whatever is in it can still be recovered by hand.
    """
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
        if valid(data):
            return data
    except ValueError:
        pass
    aside = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
    os.replace(path, aside)
    print(f"clida: {path} could not be read; moved to {aside.name}, starting empty", file=sys.stderr, flush=True)
    return None


def save(path, data):
    """Write data atomically: a crash leaves the old file or the new one, never half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
