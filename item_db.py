"""Knows every gear item: recognizes it from its icon and says how much Magic a top roll has.

autosell_items.json comes from the drop calculator (elClie/Pixel-Lineage-Drop-Calculator):
each item's pixel-art icon, and for items with Magic, the Magic value of the top 1% to 50% of
Legendary and Secret rolls (torment run, unforged +0).

autosell_settings.json holds which top % to keep, for all items or per item. Change it by typing
in the bot window:
    items              list items and their current setting
    items hat          only items with "hat" in the name
    top tempest hat 3  keep only the top 3% of Tempest Hats
    top all 5          every item: top 5%
    help               show these commands
"""
import json
import re
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
ITEMS_FILE = ROOT / "autosell_items.json"
SETTINGS_FILE = ROOT / "autosell_settings.json"
DEFAULT_TOP = 5
MIN_TOP, MAX_TOP = 1, 50

# Icons up to 12 art pixels wide are drawn at 5 screen pixels per art pixel, bigger ones at 3.75.
SMALL_CELL, BIG_CELL, SMALL_MAX = 5, 3.75, 12
MATCH_TOL = 40  # max color difference for an art pixel to count as matching
MIN_SCORE = 0.85  # share of art pixels that must match
MIN_MARGIN = 0.03  # best item must beat the runner-up by this much

_items = None
_by_kind = {}
_settings = None


def _render(entry):
    rows, pal = entry["rows"], entry["palette"]
    h, w = len(rows), len(rows[0])
    img = np.zeros((h, w, 3), np.uint8)
    mask = np.zeros((h, w), np.uint8)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            color = pal.get(ch)
            if color:  # "K" outline and "." are not in the palette: skipped
                img[y, x] = (int(color[5:7], 16), int(color[3:5], 16), int(color[1:3], 16))
                mask[y, x] = 255
    cell = SMALL_CELL if max(h, w) <= SMALL_MAX else BIG_CELL
    size = (max(1, round(w * cell)), max(1, round(h * cell)))
    img = cv2.resize(img, size, interpolation=cv2.INTER_NEAREST)
    mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
    return img, mask


def load():
    global _items
    if _items is None:
        try:
            data = json.loads(ITEMS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("[autosell] autosell_items.json missing, item recognition is off")
            _items = []
            return _items
        _items = data["items"]
        for e in _items:
            e["_img"], e["_mask"] = _render(e)
            _by_kind.setdefault(e["kind"], []).append(e)
    return _items


def identify(frame, i, kind, slot_box):
    """Which item sits in slot i, or None if unsure. slot_box(i) gives its top-left corner."""
    load()
    s = frame.shape[1] / 1920
    x0, y0 = slot_box(i)
    area = frame[int(y0 * s):int((y0 + 84) * s), int(x0 * s):int((x0 + 84) * s)]
    if abs(s - 1) > 0.01:
        area = cv2.resize(area, None, fx=1 / s, fy=1 / s, interpolation=cv2.INTER_AREA)
    scores = []
    for e in _by_kind.get(kind, ()):
        img, mask = e["_img"], e["_mask"]
        if img.shape[0] > area.shape[0] or img.shape[1] > area.shape[1]:
            continue
        res = cv2.matchTemplate(area, img, cv2.TM_SQDIFF, mask=cv2.merge([mask] * 3))
        _, _, (x, y), _ = cv2.minMaxLoc(np.nan_to_num(res, nan=1e18, posinf=1e18))
        part = area[y:y + img.shape[0], x:x + img.shape[1]].astype(int)
        on = mask > 0
        ok = (np.abs(part - img.astype(int)).max(axis=2) <= MATCH_TOL) & on
        scores.append((ok.sum() / max(1, on.sum()), e))
    if not scores:
        return None
    scores.sort(key=lambda t: -t[0])
    best, entry = scores[0]
    second = scores[1][0] if len(scores) > 1 else 0
    if best < MIN_SCORE or best - second < MIN_MARGIN:
        return None
    return entry


def _load_settings():
    global _settings
    if _settings is None:
        try:
            _settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _settings = {}
        _settings.setdefault("default_top", DEFAULT_TOP)
        _settings.setdefault("items", {})
    return _settings


def _save_settings():
    try:
        SETTINGS_FILE.write_text(json.dumps(_settings, indent=2), encoding="utf-8")
    except OSError:
        print("[autosell] couldn't save autosell_settings.json")


def top_pct(entry):
    st = _load_settings()
    return st["items"].get(entry["id"], st["default_top"])


def min_magic(entry, rarity):
    """Flat Magic needed to keep this item at its rarity, or None if there's no table for it."""
    table = (entry.get("top") or {}).get(rarity.capitalize())
    if not table:
        return None
    return table[str(top_pct(entry))]


def _line(e):
    pct = top_pct(e)
    leg = e["top"]["Legendary"]
    return f"  {e['name']:<30} {e['kind']:<7} top {pct:>2}%  keep at {leg[str(pct)]}+ Magic (best roll ~{leg['max']})"


def _matches(text):
    text = text.strip().lower()
    with_top = [e for e in load() if e.get("top")]
    exact = [e for e in with_top if e["name"].lower() == text]
    return exact or [e for e in with_top if text in e["name"].lower()]


def command(line):
    """Handle an items/top/help command typed in the bot window. Returns True if it was one."""
    words = line.strip()
    low = words.lower()
    if low in ("help", "?"):
        print("[autosell] items | items <part of name> | top <item> <1-50> | top all <1-50>")
        return True
    if low == "items" or low.startswith("items "):
        found = _matches(words[5:]) if low.startswith("items ") else [e for e in load() if e.get("top")]
        if not found:
            print("[autosell] no items match")
        for e in sorted(found, key=lambda e: (e["kind"], e["name"])):
            print(_line(e))
        print(f"[autosell] default for everything else: top {_load_settings()['default_top']}%")
        return True
    m = re.fullmatch(r"top\s+(.+?)\s+(\d{1,2})\s*%?", words, re.I)
    if not m:
        if low.startswith("top"):
            print("[autosell] use: top <item> <1-50>, for example: top tempest hat 3")
            return True
        return False
    name, pct = m.group(1), int(m.group(2))
    if not MIN_TOP <= pct <= MAX_TOP:
        print(f"[autosell] pick a number from {MIN_TOP} to {MAX_TOP}")
        return True
    st = _load_settings()
    if name.lower() == "all":
        st["default_top"] = pct
        st["items"] = {}
        _save_settings()
        print(f"[autosell] every item: top {pct}%")
        return True
    found = _matches(name)
    if not found:
        print(f"[autosell] no item called '{name}'. Type: items")
        return True
    if len(found) > 1:
        print(f"[autosell] '{name}' matches {len(found)} items, be more specific:")
        for e in found[:15]:
            print("   " + e["name"])
        return True
    e = found[0]
    st["items"][e["id"]] = pct
    _save_settings()
    print("[autosell] set:")
    print(_line(e))
    return True
