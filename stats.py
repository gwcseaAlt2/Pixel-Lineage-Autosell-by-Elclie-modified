"""Session summary (bot_stats.txt) and stuck-screen screenshots (stuck_screens folder).

To remove: delete stats.py, then the lines marked "stats" in bot.py, autosell.py and
reconnect.py.
"""
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).parent
STATS_FILE = ROOT / "bot_stats.txt"
STUCK_DIR = ROOT / "stuck_screens"
STUCK_KEEP = 50  # oldest stuck screenshots are deleted past this many

ORDER = (
    "runs finished", "battles", "boss fights", "gear checks",
    "items sold", "reconnect clicks", "stuck screenshots",
)
_counts = {name: 0 for name in ORDER}
_started = time.strftime("%Y-%m-%d %H:%M:%S")


def _write():
    lines = [f"Bot session started {_started}", f"Last update      {time.strftime('%H:%M:%S')}", ""]
    lines += [f"{name:<18} {_counts.get(name, 0)}" for name in ORDER]
    try:
        STATS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def bump(name, n=1):
    """Add n to a counter and rewrite bot_stats.txt."""
    if n:
        _counts[name] = _counts.get(name, 0) + n
        _write()


def save_stuck(frame):
    """Save a screenshot of a screen the bot seems stuck on. Returns the file path."""
    try:
        STUCK_DIR.mkdir(exist_ok=True)
        path = STUCK_DIR / time.strftime("stuck_%m%d_%H%M%S.png")
        cv2.imwrite(str(path), frame)
        old = sorted(STUCK_DIR.glob("stuck_*.png"))
        for p in old[:-STUCK_KEEP]:
            p.unlink()
    except OSError:
        return None
    bump("stuck screenshots")
    return path


_write()
