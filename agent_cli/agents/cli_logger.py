"""Live CLI status logger. Color-coded so the user can see flow at a glance."""
from __future__ import annotations

import sys
from datetime import datetime

# ANSI colors per agent role — fall back to plain when not a TTY.
COLORS = {
    "router": "\033[36m",      # cyan
    "planner": "\033[34m",     # blue
    "researcher": "\033[35m",  # magenta
    "advisor": "\033[32m",     # green
    "critic": "\033[33m",      # yellow
    "tester": "\033[36m",      # cyan
    "governance": "\033[31m",  # red
    "approval": "\033[1;33m",  # bold yellow
    "presenter": "\033[1;32m", # bold green
    "history": "\033[90m",     # gray
    "system": "\033[1m",       # bold
    "done": "\033[1;32m",      # bold green
    "blocked": "\033[1;31m",   # bold red
}
RESET = "\033[0m"


def _is_tty() -> bool:
    return sys.stdout.isatty()


def log(agent: str, message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    color = COLORS.get(agent.lower(), "") if _is_tty() else ""
    reset = RESET if color else ""
    print(f"[{ts}] {color}[{agent.upper():>10s}]{reset} {message}", flush=True)
