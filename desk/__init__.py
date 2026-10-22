"""claude-desk: a desktop-style window around the Claude Code CLI."""

import os
from pathlib import Path

CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
STATE_DIR = Path(os.environ.get("CLAUDE_DESK_HOME") or Path.home() / ".claude-desk")
ROOT = Path(__file__).resolve().parent.parent
