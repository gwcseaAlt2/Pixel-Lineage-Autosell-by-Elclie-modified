"""Auto-sell (Ctrl+4 toggles it). Runs on the "Choose your path" screen after a boss fight,
and halfway through each land (2 progress squares done).

Goes through the WEAPON, HELMET, CHEST, LEGS, RELIC and SCROLL tabs of the gear menu and sells
every item that doesn't pass the rules below. To remove this feature: delete autosell.py,
gear_reader.py, gear_glyphs.npz and autosell_icons, then remove the lines marked "autosell"
in bot.py and hotkeys.py (or restore backup_before_autosell.zip).

Keep rules:
- Equipped items (E badge) and locked items (padlock) are never sold.
- Memos, Staplers and Eye of the Hollow (recognized by their icon) have their own rules:
  Eye of the Hollow: MAGIC % 47+. Memo: SHADOW DMG 10%+ or any MAGIC %.
  Stapler: GOLD 300%+ and one of the bonus stats below.
  The Last Ember: kept when Legendary.
  Tempest Slippers: Legendary, flat MAGIC 100+ and one of the bonus stats below.
- Only Legendary or Secret items can be kept. Epic and Common are sold.
- Weapons, helmets, chests and legs need flat MAGIC over 120.
- Weapons, helmets, chests, legs and scrolls need at least one of: CRIT 10%+,
  SHADOW DMG 10%+, SKILL DMG 10%+, or any MAGIC %.
- Other relics need MAGIC 35%+.
- If anything can't be read clearly, the item is kept.

Top % tables (item_db.py): weapons, helmets, chests and legs that are recognized by their icon
use the drop calculator instead of the flat MAGIC rule above. A Legendary or Secret piece is
kept when its flat MAGIC is in the top X% of rolls for that item (default top 5%). Type
"help" in the bot window to change it. Pieces it doesn't recognize use the rules above.
"""
import re
import time
from pathlib import Path

import cv2
import numpy as np

import gear_reader
import item_db  # top % tables
import stats  # stats

ROOT = Path(__file__).parent
ICON_DIR = ROOT / "autosell_icons"
LOG_DIR = ROOT / "autosell_log"

# True = test mode: never presses SELL. Instead it clicks LOCK on every item it would sell,
# so you can see its choices in the game. Only the first auto-sell after starting the bot does
# this (a second LOCK click would unlock them again); later runs only log.
# Check the locked items, unlock them, then set this to False.
DRY_RUN = False

# (tab name, click point, flat MAGIC must be over this, or None for no MAGIC rule).
# Points are on a 1920x1080 screen.
MAGIC_OVER = 120  # was 130
TABS = (
    ("weapon", (970, 259), MAGIC_OVER),
    ("helmet", (1059, 259), MAGIC_OVER),
    ("chest", (1148, 259), MAGIC_OVER),
    ("legs", (1237, 259), MAGIC_OVER),
    ("relic", (1326, 259), None),
    ("scroll", (1413, 259), None),
)
# Crit, Shadow DMG and Skill DMG only count from this % up. Any Magic % counts.
MIN_BONUS_PCT = 10
TAB_KIND = {"weapon": "Weapon", "helmet": "Helmet", "chest": "Chest", "legs": "Legs"}
GEAR_BTN = (261, 972)
GEAR_BTN_BOX = (200, 955, 320, 990)  # tan when the GEAR button is usable
CLOSE_BTN = (1519, 193)
CLOSE_BOX = (1505, 180, 1535, 206)  # red X of the gear menu
# The panel moves up or down depending on the grid, so SELL and the popup are searched for.
# Column of the item panel's SELL button text (white "SELL"), searched between these heights.
SELL_TEXT_X = (1345, 1386)
SELL_SEARCH_Y = (690, 860)
SELL_BTN_X = 1365
# Popup after SELL: tan "SELL +xG" on the left, red DELETE next to it, on the same rows.
POPUP_SELL_X = (880, 1050)
POPUP_DELETE_X = (1100, 1220)
POPUP_SELL_BTN_X = 935  # well left of center, away from DELETE
# LOCK button sits under SELL, a bit to the right (test mode only).
LOCK_OFFSET = (1429 - 1365, 53)
LOCK_TEXT_BOX = (1408, -8, 1450, 8)  # x0, y0, x1, y1 around the LOCK center (y relative)

# Item grid: 7 per row, 90 px apart, first slot's top-left corner at (848, 298).
SLOT_X0, SLOT_Y0, SLOT_STEP, COLS, MAX_SLOTS = 848, 298, 90, 7, 28

RED_RANGES = (((0, 100, 100), (8, 255, 255)), ((170, 100, 100), (180, 255, 255)))
TAN_RANGES = (((15, 60, 150), (35, 255, 255)),)
WHITE_RANGES = (((0, 0, 200), (180, 40, 255)),)
ICON_MATCH = 0.7

SELECT_DELAY = 0.5  # test mode only, after clicking LOCK
OPEN_TIMEOUT = 3.0
# Instead of fixed waits, the screen is checked every POLL seconds until it has changed and
# looks the same twice in a row. If that takes longer than the timeout, the item is kept.
POLL = 0.05
TAB_TIMEOUT = 1.5
PANEL_TIMEOUT = 2.0
PANEL_SETTLE = 0.2  # after the panel starts changing, so the new item's text is fully drawn
POPUP_TIMEOUT = 2.0
SOLD_TIMEOUT = 2.0
# Item panel area used to see when it has switched to the clicked item.
PANEL_SIG_BOX = (850, 625, 1300, 900)
# Tab buttons turn tan when selected.
TAB_HALF = (35, 10)  # half width/height of the part of a tab button that is checked
# Remembered look of every tab after it was checked, so unchanged tabs are skipped.
_tab_prints = {}

MAGIC_RE = re.compile(r"\+(\d+) MAGIC")
MAGIC_PCT_RE = re.compile(r"\+(\d+)% MAGIC")
GOLD_PCT_RE = re.compile(r"\+(\d+)% GOLD")
SHADOW_RE = re.compile(r"\+(\d+)% SHADOW DMG")
EYE_MIN_MAGIC_PCT = 47
RELIC_MIN_MAGIC_PCT = 35
SLIPPERS_MIN_MAGIC = 100  # was 110; Tempest Slippers: Legendary, flat MAGIC 100+, plus a bonus stat
SLIPPERS_MAX_HUE = 120  # other relics (not Stapler/Eye/Last Ember) need MAGIC 35%+
STAPLER_MIN_GOLD_PCT = 300
BONUS_RE = re.compile(r"\+(\d+)% (CRIT|SHADOW DMG|SKILL DMG)")

_icons = None
LOG_FILE = LOG_DIR / "log.txt"

# drop log: one line per item in drops.csv (open it in Excel). Kept items are checked again
# later, so their exact stats are remembered and they are only written once.
DROPS_FILE = ROOT / "drops.csv"
_last_read = {}
_drops_seen = None


def _drop_log(tab, name, keep, reason):
    global _drops_seen
    read = _last_read.get("v")
    if not read:
        return
    rarity, lines = read
    magic = next((int(m.group(1)) for m in map(MAGIC_RE.fullmatch, lines) if m), "")
    others = " | ".join(l for l in lines if not MAGIC_RE.fullmatch(l))
    key = f"{name},{rarity},{magic},{others}"
    try:
        import csv
        if _drops_seen is None:
            _drops_seen = set()
            if DROPS_FILE.exists():
                with open(DROPS_FILE, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if row.get("result", "").startswith("kept"):
                            _drops_seen.add(f"{row['item']},{row['rarity']},{row['magic']},{row['other stats']}")
        if key in _drops_seen:
            return
        if keep:
            _drops_seen.add(key)
        new = not DROPS_FILE.exists()
        with open(DROPS_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "tab", "item", "rarity", "magic", "other stats", "result"])
            unsure = keep and reason.startswith(("unsure", "rarity color unknown", "read error"))
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), tab, name, rarity, magic, others,
                        "kept (unsure read)" if unsure else ("kept" if keep else "sold")])
    except Exception as e:
        log(f"[autosell] drops.csv error {e}")
LOG_MAX_BYTES = 300_000


def log(msg):
    """Print and also append to autosell_log/log.txt, so runs can be checked afterwards."""
    print(msg)
    try:
        LOG_DIR.mkdir(exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            LOG_FILE.replace(LOG_DIR / "log_old.txt")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def _scale(frame):
    return frame.shape[1] / 1920


def _pt(frame, pt):
    s = _scale(frame)
    return int(pt[0] * s), int(pt[1] * s)


def _cover(frame, box, ranges):
    s = _scale(frame)
    x0, y0, x1, y1 = (int(v * s) for v in box)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, *ranges[0])
    for lo, hi in ranges[1:]:
        mask |= cv2.inRange(hsv, lo, hi)
    return cv2.countNonZero(mask) / mask.size


def gear_ready(frame):
    return _cover(frame, GEAR_BTN_BOX, TAN_RANGES) >= 0.6


def menu_open(frame):
    return _cover(frame, CLOSE_BOX, RED_RANGES) >= 0.6


def _slot_box(i):
    x0 = SLOT_X0 + SLOT_STEP * (i % COLS)
    y0 = SLOT_Y0 + SLOT_STEP * (i // COLS)
    return x0, y0


def slot_center(i):
    x0, y0 = _slot_box(i)
    return x0 + 42, y0 + 42


def count_items(frame):
    """Number of filled slots; items are packed from the first slot with no gaps."""
    s = _scale(frame)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    n = 0
    for i in range(MAX_SLOTS):
        x0, y0 = _slot_box(i)
        # The slot's left and right borders (middle part), so vertical shift doesn't matter.
        # Both are needed: a selected neighbour's thick border can reach into one side.
        ys = slice(int((y0 + 20) * s), int((y0 + 64) * s))
        left = hsv[ys, int((x0 - 3) * s):int((x0 + 4) * s), 2]
        right = hsv[ys, int((x0 + 80) * s):int((x0 + 88) * s), 2]
        if (left.size == 0 or right.size == 0 or (left > 110).mean(axis=0).max() < 0.6
                or (right > 110).mean(axis=0).max() < 0.6):
            break
        n += 1
    return n


def equipped(frame, i):
    x0, y0 = _slot_box(i)
    return _cover(frame, (x0 + 6, y0 + 6, x0 + 22, y0 + 20), TAN_RANGES) >= 0.5


PADLOCK_FILE = ROOT / "autosell_padlock.png"
PADLOCK_MATCH = 0.75
_padlock = None


def locked(frame, i):
    """Padlock badge in the slot's top-right corner, matched by shape.

    (A plain color check mistook gold horns on some icons, like the Tempest Mantle, for it.)
    """
    global _padlock
    if _padlock is None:
        _padlock = cv2.imread(str(PADLOCK_FILE))
    if _padlock is None:
        return False
    s = _scale(frame)
    x0, y0 = _slot_box(i)
    crop = frame[int((y0 + 1) * s):int((y0 + 35) * s), int((x0 + 54) * s):int((x0 + 84) * s)]
    if abs(s - 1) > 0.01:
        crop = cv2.resize(crop, None, fx=1 / s, fy=1 / s, interpolation=cv2.INTER_AREA)
    if crop.shape[0] < _padlock.shape[0] or crop.shape[1] < _padlock.shape[1]:
        return False
    return cv2.matchTemplate(crop, _padlock, cv2.TM_CCOEFF_NORMED).max() >= PADLOCK_MATCH


def _navy_band(frame, i):
    """Tempest Slippers have a navy band (hue about 115); Apprentice Trousers a purple one (125)."""
    s = _scale(frame)
    x0, y0 = _slot_box(i)
    band = frame[int((y0 + 28) * s):int((y0 + 38) * s), int((x0 + 20) * s):int((x0 + 64) * s)]
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    m = (hsv[:, 1] > 80) & (hsv[:, 2] > 60)
    return bool(m.any()) and np.median(hsv[m, 0]) <= SLIPPERS_MAX_HUE


def protected_icon(frame, i):
    """Return 'memo', 'stapler' or 'hollow_eye' if the slot shows one of those icons."""
    global _icons
    if _icons is None:
        _icons = {p.stem: cv2.imread(str(p)) for p in ICON_DIR.glob("*.png")}
    s = _scale(frame)
    x0, y0 = _slot_box(i)
    # Template was cut at (x0+14, y0+22); search a few pixels around it.
    crop = frame[int((y0 + 16) * s):int((y0 + 66) * s), int((x0 + 8) * s):int((x0 + 76) * s)]
    if abs(s - 1) > 0.01:
        crop = cv2.resize(crop, None, fx=1 / s, fy=1 / s, interpolation=cv2.INTER_AREA)
    for name, icon in _icons.items():
        if icon is None or crop.shape[0] < icon.shape[0] or crop.shape[1] < icon.shape[1]:
            continue
        score = cv2.matchTemplate(crop, icon, cv2.TM_CCOEFF_NORMED).max()
        if score >= ICON_MATCH:
            if name == "tempest_slippers" and not _navy_band(frame, i):
                continue  # same shape as the purple Apprentice Trousers
            return name
    return None


def _rows(frame, x_range, ranges, min_cover):
    """Screen rows (1920 scale) between SELL_SEARCH_Y where the x range is mostly that color."""
    s = _scale(frame)
    y0, y1 = int(SELL_SEARCH_Y[0] * s), int(SELL_SEARCH_Y[1] * s)
    x0, x1 = int(x_range[0] * s), int(x_range[1] * s)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, *ranges[0])
    for lo, hi in ranges[1:]:
        mask |= cv2.inRange(hsv, lo, hi)
    cover = (mask > 0).mean(axis=1)
    return [(y0 + i) / s for i in np.where(cover >= min_cover)[0]]


def find_sell_button(frame):
    """Center of the item panel's SELL button, or None."""
    ys = _rows(frame, SELL_TEXT_X, WHITE_RANGES, 0.15)
    if not ys:
        return None
    # First block of text rows is SELL (GIFT is further right, LOCK is lower).
    block = [ys[0]]
    for y in ys[1:]:
        if y - block[-1] > 2:
            break
        block.append(y)
    if not 6 <= len(block) <= 14:
        return None
    # Starter gear shows "STARTER OUTFIT - BOUND TO YOU" here instead; that text starts further left.
    s = _scale(frame)
    y0, y1 = int(block[0] * s), int(block[-1] * s) + 1
    hsv = cv2.cvtColor(frame[y0:y1, int(1312 * s):int(1340 * s)], cv2.COLOR_BGR2HSV)
    if cv2.inRange(hsv, *WHITE_RANGES[0]).mean() / 255 > 0.05:
        return None
    return SELL_BTN_X, (block[0] + block[-1]) / 2


def find_popup_sell(frame):
    """Center of the popup's SELL +xG button, only when DELETE sits next to it."""
    tan = set(int(y) for y in _rows(frame, POPUP_SELL_X, TAN_RANGES, 0.8))
    red = set(int(y) for y in _rows(frame, POPUP_DELETE_X, RED_RANGES, 0.8))
    both = sorted(tan & red)
    if len(both) < 20:
        return None
    return POPUP_SELL_BTN_X, (both[0] + both[-1]) / 2


def _sig(frame, box):
    s = _scale(frame)
    x0, y0, x1, y1 = (int(v * s) for v in box)
    g = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (g.shape[1] // 4, g.shape[0] // 4), interpolation=cv2.INTER_AREA).astype(np.int16)


def _same(a, b):
    return a is not None and b is not None and a.shape == b.shape and np.abs(a - b).mean() < 1.0


def wait_panel(grab, wait, before):
    """Wait until the item panel differs from `before`, then PANEL_SETTLE more. Frame or None.

    (It used to wait for the panel to look the same twice in a row, but animated icons in the
    panel meant that never happened, so every item timed out and was kept.)
    """
    end = time.time() + PANEL_TIMEOUT
    while time.time() < end:
        if wait(POLL):
            return None
        if not _same(_sig(grab(), PANEL_SIG_BOX), before):
            if wait(PANEL_SETTLE):
                return None
            return grab()
    return None


def tab_selected(frame, tab_pt):
    x, y = tab_pt
    hx, hy = TAB_HALF
    return _cover(frame, (x - hx, y - hy, x + hx, y + hy), TAN_RANGES) >= 0.5


def tab_print(frame):
    """Edge map of every filled slot: unchanged when only the selection highlight differs."""
    s = _scale(frame)
    prints = []
    for i in range(count_items(frame)):
        x0, y0 = _slot_box(i)
        crop = frame[int((y0 + 8) * s):int((y0 + 76) * s), int((x0 + 8) * s):int((x0 + 76) * s)]
        prints.append(cv2.Canny(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 60, 150) > 0)
    return prints


def same_print(a, b):
    if a is None or b is None or len(a) != len(b):
        return False
    # 10%: the white highlight on a selected slot changes its edges by about 5 to 7%.
    return all(x.shape == y.shape and (x != y).mean() < 0.10 for x, y in zip(a, b))


def judge(frame, min_magic, kind=None, tab=None, entry=None):
    """Return (keep, reason) for the item shown in the panel.

    kind is 'memo', 'stapler' or 'hollow_eye' when the slot showed that icon.
    """
    rarity = gear_reader.rarity(frame)
    _last_read["v"] = (rarity, []) if rarity else None  # drop log
    if rarity is None:
        return True, "rarity color unknown"
    if kind is None and rarity not in ("legendary", "secret"):
        return False, rarity
    try:
        lines = gear_reader.read_stats(frame)
        _last_read["v"] = (rarity, lines)  # drop log
    except Exception as e:  # missing glyph file etc.: never sell blind
        return True, f"read error {e}"
    if not lines:
        return True, f"{rarity}, no stats read"
    magic = None
    bonus = []
    for line in lines:
        m = MAGIC_RE.fullmatch(line)
        if m:
            magic = int(m.group(1))
        if MAGIC_PCT_RE.fullmatch(line):
            bonus.append(line)
        m = BONUS_RE.fullmatch(line)
        if m and int(m.group(1)) >= MIN_BONUS_PCT:
            bonus.append(line)
    # Only an unreadable number matters: every label the rules use is made of letters the
    # reader knows, so a "?" in a label (like FURY) means it's some other stat.
    unsure = any("?" in line.split()[0] for line in lines if line.startswith("+"))
    magic_pct = max([int(m.group(1)) for m in map(MAGIC_PCT_RE.fullmatch, lines) if m] or [0])
    if entry is not None:  # top % table
        need = item_db.min_magic(entry, rarity)
        ok = need is not None and magic is not None and magic >= need
        summary = (f"{entry['name']}, {rarity}, magic {magic}, need {need} "
                   f"(top {item_db.top_pct(entry)}%), {lines}")
        if ok:
            return True, summary
        if unsure or magic is None:
            return True, "unsure read, " + summary
        return False, summary
    if kind == "last_ember":
        return rarity == "legendary", f"the last ember, {rarity}"
    if kind == "tempest_slippers":
        if rarity != "legendary":
            return False, f"tempest slippers, {rarity}"
    if kind == "hollow_eye":
        ok = magic_pct >= EYE_MIN_MAGIC_PCT
        summary = f"eye of the hollow, magic {magic_pct}%, {lines}"
    elif kind == "memo":
        shadow = max([int(m.group(1)) for m in map(SHADOW_RE.fullmatch, lines) if m] or [0])
        ok = shadow >= MIN_BONUS_PCT or magic_pct > 0
        summary = f"memo, shadow dmg {shadow}%, magic {magic_pct}%, {lines}"
    elif kind == "stapler":
        gold = max([int(m.group(1)) for m in map(GOLD_PCT_RE.fullmatch, lines) if m] or [0])
        ok = gold >= STAPLER_MIN_GOLD_PCT and bool(bonus)
        summary = f"stapler, gold {gold}%, bonus {bonus or 'none'}, {lines}"
    elif kind == "tempest_slippers":
        ok = magic is not None and magic >= SLIPPERS_MIN_MAGIC and bool(bonus)
        summary = f"tempest slippers, magic {magic}, bonus {bonus or 'none'}, {lines}"
    elif tab == "relic":
        ok = magic_pct >= RELIC_MIN_MAGIC_PCT
        summary = f"relic, magic {magic_pct}%, {lines}"
    else:
        ok = (min_magic is None or (magic is not None and magic > min_magic)) and bool(bonus)
        summary = f"{rarity}, magic {magic}, bonus {bonus or 'none'}, {lines}"
    if ok:
        return True, summary
    if unsure:
        return True, "unsure read, " + summary
    return False, summary


def _save_log(frame, tab, n, keep, reason):
    s = _scale(frame)
    panel = frame[int(620 * s):int(905 * s), int(835 * s):int(1300 * s)]
    name = f"{tab}_{n:02d}_{'KEEP' if keep else 'SELL'}.png"
    try:
        cv2.imwrite(str(LOG_DIR / name), panel)
    except Exception:
        pass
    log(f"[autosell] {tab} #{n}: {'keep' if keep else 'SELL'} ({reason})")


_test_locked = False


def _lock(frame, click, sell_pt):
    """Test mode: click LOCK under the SELL button. Returns True if it was clicked."""
    x, y = sell_pt[0] + LOCK_OFFSET[0], sell_pt[1] + LOCK_OFFSET[1]
    x0, y0, x1, y1 = LOCK_TEXT_BOX
    if _cover(frame, (x0, int(y + y0), x1, int(y + y1)), WHITE_RANGES) < 0.05:
        log("[autosell] test mode: LOCK button not found")
        return False
    click(_pt(frame, (x, y)))
    return True


def stopping_now(wait):
    return wait(0)


# Land progress squares under the land name (top left): tan = done, white = current,
# dark = still to go, red = boss. Centers on a 1920x1080 screen.
PROGRESS_X = (157, 182, 207, 232)
PROGRESS_Y = (121, 129)
HALFWAY_DONE = 2  # check gear when this many squares are done


def stages_done(frame):
    """Number of tan (finished) progress squares in this land."""
    y0, y1 = PROGRESS_Y
    return sum(_cover(frame, (x - 5, y0, x + 5, y1), TAN_RANGES) >= 0.5 for x in PROGRESS_X)


def halfway(frame):
    return stages_done(frame) == HALFWAY_DONE


def run_autosell(click, grab, wait):
    """Open GEAR, check every tab, sell what fails the rules, close. Returns False if stopped."""
    global _test_locked
    LOG_DIR.mkdir(exist_ok=True)
    for old in LOG_DIR.glob("*.png"):
        try:
            old.unlink()
        except OSError:
            pass

    frame = grab()
    if not gear_ready(frame):
        log("[autosell] GEAR button not usable, skipping")
        return True
    if DRY_RUN:
        log("[autosell] open gear [TEST MODE: "
              + ("items it would sell get LOCKED]" if not _test_locked else "log only]"))
    else:
        log("[autosell] open gear")
    click(_pt(frame, GEAR_BTN))
    for _ in range(int(OPEN_TIMEOUT / 0.1)):
        if wait(0.1):
            return False
        if menu_open(grab()):
            break
    else:
        log("[autosell] gear menu didn't open")
        return True

    lock_now = DRY_RUN and not _test_locked
    _test_locked = True
    sold = 0
    try:
        for tab, tab_pt, min_magic in TABS:
            click(_pt(frame, tab_pt))
            # Wait for the tab to turn tan and its grid to stop changing.
            last, end = None, time.time() + TAB_TIMEOUT
            while time.time() < end:
                if wait(POLL):
                    return False
                frame = grab()
                p = tab_print(frame)
                if tab_selected(frame, tab_pt) and same_print(p, last):
                    break
                last = p
            if same_print(tab_print(frame), _tab_prints.get(tab)):
                log(f"[autosell] {tab}: no changes since last check, skipped")
                continue
            idx, checked, steps = 0, 0, 0
            # Set when an item was kept only because something couldn't be checked; then this
            # tab isn't remembered, so it gets checked again next time.
            uncertain = False
            while steps < 40:
                steps += 1
                frame = grab()
                if not menu_open(frame):
                    log("[autosell] gear menu closed unexpectedly")
                    return True
                total = count_items(frame)
                if idx >= total:
                    break
                checked += 1
                if equipped(frame, idx):
                    log(f"[autosell] {tab} #{checked}: keep (equipped)")
                    idx += 1
                    continue
                if locked(frame, idx):
                    log(f"[autosell] {tab} #{checked}: keep (locked)")
                    idx += 1
                    continue
                entry = None  # top % tables
                if tab in TAB_KIND:
                    try:
                        entry = item_db.identify(frame, idx, TAB_KIND[tab], _slot_box)
                    except Exception as e:
                        log(f"[autosell] item recognition error {e}")
                    if entry is not None and not entry.get("top"):
                        entry = None
                icon = None if entry is not None else protected_icon(frame, idx)
                before = _sig(frame, PANEL_SIG_BOX)
                click(_pt(frame, slot_center(idx)))
                frame = wait_panel(grab, wait, before)
                if frame is None:
                    if stopping_now(wait):
                        return False
                    uncertain = True
                    _save_log(grab(), tab, checked, True, "panel didn't update in time")
                    idx += 1
                    continue
                keep, reason = judge(frame, min_magic, icon, tab, entry)
                _save_log(frame, tab, checked, keep, reason)
                _drop_log(tab, entry["name"] if entry else (icon or "?"), keep, reason)  # drop log
                if keep and (reason.startswith(("rarity color unknown", "read error", "unsure"))
                             or reason.endswith("no stats read")):
                    uncertain = True
                if keep:
                    idx += 1
                    continue
                sell_pt = find_sell_button(frame)
                if not sell_pt:
                    log("[autosell] SELL button not found, keeping item")
                    idx += 1
                    continue
                if DRY_RUN:
                    if lock_now and _lock(frame, click, sell_pt):
                        log("[autosell] test mode: LOCKED instead of selling")
                        if wait(SELECT_DELAY):
                            return False
                    idx += 1
                    continue
                click(_pt(frame, sell_pt))
                confirm_pt, end = None, time.time() + POPUP_TIMEOUT
                while not confirm_pt and time.time() < end:
                    if wait(POLL):
                        return False
                    # Popup found twice in a row, so it isn't still sliding in.
                    first = find_popup_sell(grab())
                    if first and wait(POLL):
                        return False
                    confirm_pt = first and find_popup_sell(grab())
                if not confirm_pt:
                    log("[autosell] sell popup didn't show, keeping item")
                    uncertain = True
                    idx += 1
                    continue
                click(_pt(frame, confirm_pt))
                dropped, end = False, time.time() + SOLD_TIMEOUT
                while not dropped and time.time() < end:
                    if wait(POLL):
                        return False
                    dropped = count_items(grab()) < total
                if dropped:
                    sold += 1  # next item slid into this slot, so check the same slot again
                    if wait(0.15):  # let the popup finish closing
                        return False
                else:
                    log("[autosell] item count didn't drop, moving on")
                    uncertain = True
                    idx += 1
            if uncertain:
                _tab_prints.pop(tab, None)
                log(f"[autosell] {tab}: some items couldn't be checked, will recheck next time")
            else:
                _tab_prints[tab] = tab_print(grab())
        log(f"[autosell] done, sold {sold}")
        stats.bump("gear checks")  # stats
        stats.bump("items sold", sold)  # stats
        return True
    finally:
        for _ in range(3):
            frame = grab()
            if not menu_open(frame):
                break
            click(_pt(frame, CLOSE_BTN))
            if wait(0.5):
                break
