"""Reads the item panel of the gear menu: rarity color and the green stat lines.

All positions are measured on 1920x1080 screenshots and scaled to the real frame size.
The stat font is monospace, 8 px per character and 9 px tall at 1920 wide.
"""
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
GLYPH_FILE = ROOT / "gear_glyphs.npz"

BASE_W = 1920
PITCH = 8
GLYPH_H = 9
# Panel text area (x0, y0, x1, y1). Left column of stats starts near x 861, right near 1079.
PANEL_BOX = (852, 620, 1298, 905)
COLUMN_SPLIT = 1065
# Left edge bar of the item panel; its color shows the rarity.
RARITY_BAR = (841, 700, 846, 740)

GREEN_LOW = (45, 80, 110)
GREEN_HIGH = (70, 200, 255)

# BGR colors of the rarity bar, sampled from screenshots.
RARITY_COLORS = {
    "legendary": (90, 190, 255),
    "secret": (200, 110, 255),
    "epic": (255, 130, 200),
    "common": (199, 207, 205),
}
RARITY_TOLERANCE = 40
# A character cell has to match its best glyph at least this well (0..1), else it reads as '?'.
MIN_GLYPH_SCORE = 0.80
MIN_CELL_INK = 3


def _scale(frame):
    return frame.shape[1] / BASE_W


def _box(frame, box):
    s = _scale(frame)
    return tuple(int(round(v * s)) for v in box)


def rarity(frame):
    """Return 'legendary', 'secret', 'epic', 'common' or None if the bar color is unknown."""
    x0, y0, x1, y1 = _box(frame, RARITY_BAR)
    patch = frame[y0:y1, x0:x1].reshape(-1, 3).astype(int)
    color = np.median(patch, axis=0)
    best, best_d = None, None
    for name, ref in RARITY_COLORS.items():
        d = np.abs(color - np.array(ref)).max()
        if best_d is None or d < best_d:
            best, best_d = name, d
    return best if best_d <= RARITY_TOLERANCE else None


def _green_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, GREEN_LOW, GREEN_HIGH)


def _row_groups(mask):
    rows = np.where(mask.sum(1) > 0)[0]
    groups, start, prev = [], None, None
    for r in rows:
        if start is None:
            start = prev = r
        elif r == prev + 1:
            prev = r
        else:
            groups.append((start, prev))
            start = prev = r
    if start is not None:
        groups.append((start, prev))
    return groups


def _cells(gray, mask, x_start, x_end):
    """Split one column of one line into character cells.

    Returns a list of (cell_image or None for a space).
    """
    cols = np.where(mask[:, x_start:x_end].sum(0) > 0)[0]
    if len(cols) == 0:
        return []
    first = x_start + cols[0]
    last = x_start + cols[-1]
    n = int(round((last - first + 1 + 1) / PITCH))
    cells = []
    for i in range(n):
        cx = first + i * PITCH
        m = mask[:, cx:cx + PITCH]
        # A few stray pixels are ink bleeding over from the next letter, not a character.
        if np.count_nonzero(m) <= MIN_CELL_INK:
            cells.append(None)
        else:
            # One extra pixel each side, so matching can try small shifts.
            cells.append(gray[:, max(0, cx - 1):cx + PITCH + 1])
    return cells


def _norm(cell):
    c = cell.astype(np.float32)
    c -= c.mean()
    n = np.linalg.norm(c)
    return c / n if n else c


def panel_lines(frame):
    """Yield (column, cells) for every green line in the item panel, top to bottom.

    column is 'L' or 'R'. cells are raw grayscale cells (None = space).
    """
    s = _scale(frame)
    x0, y0, x1, y1 = _box(frame, PANEL_BOX)
    crop = frame[y0:y1, x0:x1]
    if abs(s - 1) > 0.01:
        crop = cv2.resize(crop, None, fx=1 / s, fy=1 / s, interpolation=cv2.INTER_AREA)
    mask = _green_mask(crop)
    gray = crop[:, :, 1]  # green channel: text bright, background dark
    split = COLUMN_SPLIT - PANEL_BOX[0]
    out = []
    for top, bottom in _row_groups(mask):
        if bottom - top + 1 < GLYPH_H - 2:
            continue
        top = max(0, bottom - GLYPH_H + 1) if bottom - top + 1 > GLYPH_H else top
        rows = slice(top, top + GLYPH_H)
        for col, xs, xe in (("L", 0, split), ("R", split, mask.shape[1])):
            cells = _cells(gray[rows], mask[rows], xs, xe)
            if cells:
                out.append((col, cells))
    return out


_glyphs = None


def _load_glyphs():
    global _glyphs
    if _glyphs is None:
        data = np.load(GLYPH_FILE)
        _glyphs = (list(str(data["chars"])), data["templates"])
    return _glyphs


def read_cells(cells):
    chars, templates = _load_glyphs()
    text = ""
    for cell in cells:
        if cell is None:
            text += " "
            continue
        flat = templates.reshape(len(chars), -1)
        scores = np.full(len(chars), -1.0)
        for dx in range(cell.shape[1] - PITCH + 1):
            part = cell[:, dx:dx + PITCH]
            if part.shape != (GLYPH_H, PITCH):
                continue
            scores = np.maximum(scores, flat @ _norm(part).reshape(-1))
        i = int(np.argmax(scores))
        text += chars[i] if scores[i] >= MIN_GLYPH_SCORE else "?"
    return " ".join(text.split())


def read_stats(frame):
    """Return the stat lines as text, e.g. ['+162 MAGIC', '+135 MAX EN', ...] (left, then right)."""
    lines = panel_lines(frame)
    return [read_cells(cells) for col, cells in lines if col == "L"] + \
           [read_cells(cells) for col, cells in lines if col == "R"]
