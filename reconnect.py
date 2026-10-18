"""Gets back into a run after a Roblox disconnect.

Disconnected popup: Reconnect. Title screen: Character Select. Character list: Enter (slot 1).
Unfinished Battle: Resume Battle (never Abandon). Castle: Set Out, Play Solo, Torment card,
the target tier, Set Out!

The target tier is set by typing T=52 (any number) in the bot window, and saved in
reconnect_tier.txt (default 53). To reach a tier it hasn't seen before, the bot presses "<" until
the tier stops changing (tier 1), then ">" T-1 times, and saves a picture of that tier label
(reconnect_tier_<T>.png) so next time it recognizes it straight away.

To remove this feature: delete reconnect.py, reconnect_tier.txt and the reconnect_tier_*.png
pictures, and the lines marked "reconnect" in bot.py.

All positions are on a 1920x1080 screen.
"""
import re
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

import stats  # stats

ROOT = Path(__file__).parent
TARGET_FILE = ROOT / "reconnect_tier.txt"
DEFAULT_TIER = 53

TAN = ((15, 60, 150), (35, 255, 255))
WHITE = ((0, 0, 230), (180, 25, 255))
GREEN = ((50, 80, 100), (75, 255, 255))
RED = (((0, 120, 120), (8, 255, 255)), ((170, 120, 120), (180, 255, 255)))
BLUE = ((95, 80, 120), (125, 255, 255))
PURPLE = ((130, 80, 120), (160, 255, 255))
GREY = ((0, 0, 40), (180, 20, 75))

# (box to check, color ranges, minimum cover)
DISCONNECT_BTN = ((990, 636, 1160, 662), (WHITE,), 0.8)
DISCONNECT_PANEL = ((740, 460, 1180, 500), (GREY,), 0.9)
TITLE_BTN = ((110, 752, 580, 782), (TAN,), 0.8)
CHAR_ENTER = ((580, 724, 830, 750), (TAN,), 0.8)
UNFINISHED_RESUME = ((630, 722, 930, 758), (GREEN,), 0.8)
UNFINISHED_ABANDON = ((990, 722, 1290, 758), RED, 0.8)
CASTLE_SET_OUT = ((1660, 1022, 1880, 1060), (TAN,), 0.8)
TRAVEL_SOLO_TAG = ((525, 409, 630, 428), (TAN,), 0.7)
TRAVEL_PARTY_TAG = ((837, 409, 945, 428), (BLUE,), 0.7)
SOLO_SET_OUT = ((1100, 805, 1400, 848), (TAN,), 0.8)
TORMENT_SELECTED = ((1220, 730, 1395, 752), (PURPLE,), 0.8)
GAUNTLET_ROW = ((510, 376, 795, 382), (PURPLE,), 0.3)  # purple outlines of Today's Gauntlet

CLICK = {
    "reconnect": (1075, 649),
    "character select": (348, 768),
    "enter": (705, 737),
    "resume battle": (780, 740),
    "castle set out": (1768, 1041),
    "play solo": (651, 812),
    "torment card": (1307, 640),
    "tier down": (1232, 531),
    "tier up": (1380, 531),
    "set out!": (1252, 826),
}
LABEL_BOX = (1250, 520, 1365, 544)  # "TIER 53 / 54" label
LABEL_SEARCH = 6  # pixels searched around it when matching a saved picture
CHANGE_PIXELS = 8  # this many clearly different pixels = the label changed
PRESS_TIMEOUT = 1.0  # no change this long after a press = end of the list (or a missed press)
MAX_UP_RETRIES = 3

ACTION_GAP = 2.0  # seconds before the same screen's button is clicked again
TIER_GAP = 0.25

_last = {}
_tier = {"phase": None, "count": 0, "pending": None, "pending_t": 0.0, "retries": 0,
         "torment_tries": 0}
_templates = {}


def _load_target():
    try:
        return max(1, int(TARGET_FILE.read_text().strip()))
    except (OSError, ValueError):
        return DEFAULT_TIER


target_tier = _load_target()


def set_target(tier):
    global target_tier
    target_tier = tier
    _tier.update(phase=None, count=0, pending=None, retries=0)
    try:
        TARGET_FILE.write_text(str(tier))
    except OSError:
        pass
    print(f"[reconnect] torment tier for reconnects set to {tier}")


def _console():
    for line in sys.stdin:
        m = re.fullmatch(r"\s*[Tt]\s*=\s*(\d{1,3})\s*", line)
        if m and int(m.group(1)) >= 1:
            set_target(int(m.group(1)))
        elif line.strip():
            try:
                import item_db  # top % commands (items, top ..., help)
                handled = item_db.command(line)
            except Exception as e:
                print(f"[autosell] command error {e}")
                handled = True
            if not handled:
                print("[reconnect] type T=<tier> (like T=52), or help for item commands")


def start_console():
    """Read T=<tier> lines typed into the bot window."""
    print(f"[reconnect] torment tier for reconnects: {target_tier} (type T=52 to change)")
    print("[autosell] type help for item commands (items, top tempest hat 3, top all 5)")
    threading.Thread(target=_console, daemon=True).start()


def _cover(frame, spec):
    box, ranges, need = spec
    s = frame.shape[1] / 1920
    x0, y0, x1, y1 = (int(v * s) for v in box)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], bool)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, lo, hi) > 0
    return mask.mean() >= need


def _pt(frame, name):
    s = frame.shape[1] / 1920
    x, y = CLICK[name]
    return int(x * s), int(y * s)


def _crop(frame, box, pad=0):
    s = frame.shape[1] / 1920
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = (int(v * s) for v in (x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    crop = frame[max(0, y0):y1, max(0, x0):x1]
    if abs(s - 1) > 0.01:
        crop = cv2.resize(crop, None, fx=1 / s, fy=1 / s, interpolation=cv2.INTER_AREA)
    return crop


def _template_file(tier):
    return ROOT / f"reconnect_tier_{tier}.png"


def _on_tier(frame, tier):
    """True if the label matches the saved picture of this tier."""
    if tier not in _templates:
        _templates[tier] = cv2.imread(str(_template_file(tier)))
    tpl = _templates[tier]
    area = _crop(frame, LABEL_BOX, LABEL_SEARCH)
    if tpl is None or area.shape[0] < tpl.shape[0] or area.shape[1] < tpl.shape[1]:
        return False
    # Line the picture up, then require it to be the same pixel for pixel: a near match isn't
    # enough, since 52, 53 and 54 only differ in one digit.
    res = cv2.matchTemplate(area, tpl, cv2.TM_SQDIFF)
    _, _, (x, y), _ = cv2.minMaxLoc(res)
    h, w = tpl.shape[:2]
    return not _changed(area[y:y + h, x:x + w], tpl)


def _changed(a, b):
    """True if enough pixels of the label changed (one digit changing is only a small area)."""
    if a.shape != b.shape:
        return True
    diff = np.abs(a.astype(int) - b.astype(int)).max(axis=2)
    return np.count_nonzero(diff > 60) >= CHANGE_PIXELS


def _press(frame, click, name, gap=ACTION_GAP):
    """Click a named button, at most once per `gap` seconds. Returns True if clicked."""
    now = time.time()
    if now - _last.get(name, 0) < gap:
        return True  # still waiting for the screen to react; nothing else should act
    _last[name] = now
    print(f"[reconnect] {name}")
    if name == "reconnect":
        stats.bump("reconnect clicks")  # stats
    click(_pt(frame, name))
    return True


def _solo_run(frame, click):
    """Solo Run popup: pick Torment, get to the target tier, Set Out!"""
    if not (_cover(frame, TORMENT_SELECTED) and _cover(frame, GAUNTLET_ROW)):
        _tier["torment_tries"] += 1
        if _tier["torment_tries"] > 5:
            if _tier["torment_tries"] == 6:
                print("[reconnect] couldn't get Torment / Today's Gauntlet selected, waiting for you")
            return True
        return _press(frame, click, "torment card", 1.0)
    target = target_tier
    if _on_tier(frame, target):
        _tier.update(phase=None, pending=None)
        return _press(frame, click, "set out!", 5.0)
    if _tier["phase"] == "failed":
        return True

    # Count the way there: "<" until the tier stops changing (tier 1), then ">" target-1 times.
    now = time.time()
    label = _crop(frame, LABEL_BOX)
    if _tier["pending"] is not None:
        if _changed(label, _tier["pending"]):
            _tier["pending"] = None
            if _tier["phase"] == "up":
                _tier["count"] += 1
        elif now - _tier["pending_t"] < PRESS_TIMEOUT:
            return True
        else:
            _tier["pending"] = None
            if _tier["phase"] == "down":
                _tier.update(phase="up", count=1, retries=0)
                print("[reconnect] at tier 1, counting up")
            else:
                _tier["retries"] += 1
                if _tier["retries"] >= MAX_UP_RETRIES:
                    _tier["phase"] = "failed"
                    print(f"[reconnect] tier {target} can't be reached (stuck at {_tier['count']}), "
                          "waiting for you")
                    return True
    if _tier["phase"] is None:
        _tier.update(phase="down", count=0, retries=0)
        print(f"[reconnect] finding tier {target}")
    if _tier["phase"] == "up" and _tier["count"] >= target:
        try:
            cv2.imwrite(str(_template_file(target)), label)
            _templates.pop(target, None)
        except Exception:
            pass
        _tier.update(phase=None, pending=None)
        print(f"[reconnect] tier {target} reached, saved its picture")
        return _press(frame, click, "set out!", 5.0)
    if now - _last.get("tier", 0) < TIER_GAP:
        return True
    _last["tier"] = now
    _tier.update(pending=label, pending_t=now)
    click(_pt(frame, "tier up" if _tier["phase"] == "up" else "tier down"))
    return True


def step(frame, click):
    """Handle one recovery screen if it's showing. Returns True if this frame was one of them."""
    if _cover(frame, DISCONNECT_BTN) and _cover(frame, DISCONNECT_PANEL):
        return _press(frame, click, "reconnect", 5.0)
    if _cover(frame, UNFINISHED_RESUME) and _cover(frame, UNFINISHED_ABANDON):
        return _press(frame, click, "resume battle")
    if _cover(frame, SOLO_SET_OUT):
        return _solo_run(frame, click)
    _tier.update(phase=None, count=0, pending=None, retries=0, torment_tries=0)
    if _cover(frame, TRAVEL_SOLO_TAG) and _cover(frame, TRAVEL_PARTY_TAG):
        return _press(frame, click, "play solo")
    if _cover(frame, CHAR_ENTER):
        return _press(frame, click, "enter")
    if _cover(frame, TITLE_BTN):
        return _press(frame, click, "character select")
    if _cover(frame, CASTLE_SET_OUT):
        return _press(frame, click, "castle set out")
    return False
