import argparse
import ctypes
import time
from collections import deque
from ctypes import wintypes

import cv2
import mss
import numpy as np
import pydirectinput

import stage_select  # noqa: F401  (sets DPI awareness before any capture)
from hotkeys import running, start_listener, stopping, wait

# All positions/sizes are in reference pixels on a 1920x1080 screen, scaled at runtime.
REF_W = 1920
# Capture box around the minigame panel, with margin for the panel's shake.
REGION = (540, 90, 1380, 450)

# ARCANE SIGILS: a white square frame shrinks onto a purple rune.
RUNE_LOW, RUNE_HIGH = (125, 60, 120), (160, 255, 255)
RUNE_SIZE = (25, 60)
RUNE_MIN_AREA = 400
FRAME_SCAN = (22, 160)  # how far from the rune center to look for the frame edge
FRAME_AGREE = 4  # edges within this many px of the median count as the same frame
# Purple "ARCANE SIGILS" title (or the panel's purple top edge). Only trust a sigil while it's
# showing, so purple/white sprites (e.g. bosses) aren't mistaken for the minigame. The panel sits
# lower in boss fights, so the box is tall and any one row that's mostly purple counts.
# Measured on this PC.
SIGIL_TITLE_BOX = (830, 100, 960, 210)
SIGIL_TITLE_MIN = 0.3
# The real panel is dark behind the title; a purple sky behind a boss is not.
SIGIL_TITLE_DARK_MIN = 0.3
# Frame-to-rune distance at which all presses in the reference recording registered (PERFECT).
SIGIL_TARGET = 22.5

# INCOMING!: a red marker slides across a bar; press when it's on the white (DODGE) zone center.
# Remeasured on this PC (was 600, 250, 1320, 330). The bar sits lower in boss fights, so both
# heights are checked: boss fights first, then normal fights.
BAR_AREAS = ((560, 322, 1360, 372), (560, 265, 1360, 315))
BAR_MIN_ROWS = 15  # a column counts as zone/marker if it has at least this many matching pixels
BAR_MIN_ZONE = 30
BAR_MIN_SPEED = 200  # px/s; slower means the marker is still blinking at the start

# Time from sending Space to the game registering it, plus how old a capture is when it arrives.
SIGIL_LEAD = 0.05  # was 0.0; presses landed ~50 ms after plan on this PC
BAR_LEAD = 0.05
# Schedule a press if it's due within this window; otherwise wait for a fresher capture.
LOOKAHEAD = 0.05
SPEED_WINDOW = 0.25
PRESS_COOLDOWN = 0.4


def _scaled_box(box, scale, origin=(0, 0)):
    return tuple(int(v * scale) - int(o * scale) for v, o in zip(box, origin * 2))


def find_sigil(crop, scale):
    """Return ((cx, cy), distance, is_white) for the rune and its frame, distances in ref px."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    tx0, ty0, tx1, ty1 = _scaled_box(SIGIL_TITLE_BOX, scale, REGION[:2])
    title = cv2.inRange(hsv[ty0:ty1, tx0:tx1], RUNE_LOW, RUNE_HIGH)
    if title.size == 0 or (title > 0).mean(axis=1).max() < SIGIL_TITLE_MIN:
        return None
    if (hsv[ty0:ty1, tx0:tx1, 2] < 40).mean() < SIGIL_TITLE_DARK_MIN:
        return None
    mask = cv2.inRange(hsv, RUNE_LOW, RUNE_HIGH)
    k = max(3, int(5 * scale))
    mask = cv2.dilate(mask, np.ones((k, k), np.uint8))
    n, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
    lo, hi = RUNE_SIZE[0] * scale, RUNE_SIZE[1] * scale
    best = None
    for i in range(1, n):
        _, _, w, h, area = stats[i]
        if lo <= w <= hi and lo <= h <= hi and area >= RUNE_MIN_AREA * scale * scale:
            if best is None or area > stats[best][4]:
                best = i
    if best is None:
        return None
    cx, cy = (int(v) for v in centroids[best])

    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    white = (sat < 50) & (val > 170)
    yellow = (hue >= 10) & (hue <= 35) & (sat > 60) & (val > 120)
    start, end = int(FRAME_SCAN[0] * scale), int(FRAME_SCAN[1] * scale)
    hits = []
    for dx, dy in ((-1, 0), (1, 0), (0, 1), (0, -1)):
        for step in range(start, end):
            x, y = cx + dx * step, cy + dy * step
            if not (0 <= x < crop.shape[1] and 0 <= y < crop.shape[0]):
                break
            if white[y, x] or yellow[y, x]:
                hits.append((step / scale, bool(white[y, x])))
                break
    if len(hits) < 3:
        return None
    med = float(np.median([d for d, _ in hits]))
    agree = [(d, w) for d, w in hits if abs(d - med) <= FRAME_AGREE]
    if len(agree) < 3:
        return None
    is_white = sum(w for _, w in agree) * 2 > len(agree)
    return (cx, cy), med, is_white


def find_bar(crop, scale):
    """Return (zone_center, zone_half_width, marker_x or None) in ref px, or None."""
    for area in BAR_AREAS:
        found = _find_bar_in(crop, scale, area)
        if found:
            return found
    return None


def _find_bar_in(crop, scale, area):
    x0, y0, x1, y1 = _scaled_box(area, scale, REGION[:2])
    hsv = cv2.cvtColor(crop[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    min_rows = BAR_MIN_ROWS * scale
    white_cols = np.flatnonzero(((sat < 30) & (val > 200)).sum(0) >= min_rows)
    blue_cols = np.flatnonzero(((hue >= 95) & (hue <= 115) & (sat > 60) & (val > 180)).sum(0) >= min_rows)
    red_cols = np.flatnonzero((((hue < 8) | (hue > 170)) & (sat > 120) & (val > 120)).sum(0) >= min_rows)
    # Blue disappears when the bar flashes white after a hit, which also ends the minigame.
    if len(white_cols) < BAR_MIN_ZONE * scale or len(blue_cols) < BAR_MIN_ZONE * scale:
        return None
    to_ref = lambda px: (px + x0) / scale + REGION[0]
    center = to_ref(float(white_cols.mean()))
    half = (white_cols[-1] - white_cols[0]) / scale / 2
    marker = to_ref(float(red_cols.mean())) if len(red_cols) else None
    return center, half, marker


class MinigameSolver:
    """Feed it panel captures with timestamps; it says when to press Space."""

    def __init__(self, sigil_lead=SIGIL_LEAD, bar_lead=BAR_LEAD):
        self.sigil_lead = sigil_lead
        self.bar_lead = bar_lead
        self.history = deque()
        self.target = None
        self.cooldown_until = 0.0
        # perf_counter time a minigame was last on screen; read by the bot to confirm casts.
        self.last_seen = 0.0

    def _track(self, target, t, value):
        if target != self.target:
            self.target = target
            self.history.clear()
        self.history.append((t, value))
        while self.history and t - self.history[0][0] > SPEED_WINDOW:
            self.history.popleft()

    def _speed(self):
        if len(self.history) < 2:
            return None
        (t0, v0), (t1, v1) = self.history[0], self.history[-1]
        if t1 - t0 < 0.02:
            return None
        return (v1 - v0) / (t1 - t0)

    def _press(self, t, press_at, label):
        press_at = max(t, press_at)
        self.cooldown_until = press_at + PRESS_COOLDOWN
        self.target = None
        self.history.clear()
        return press_at, label

    def update(self, crop, scale, t):
        """Return (press_at, label) when Space should be pressed at time press_at, else None."""
        sigil = find_sigil(crop, scale)
        bar = None if sigil else find_bar(crop, scale)
        if sigil or bar:
            self.last_seen = t
        if t < self.cooldown_until:
            return None

        if sigil and sigil[2]:
            (cx, cy), dist, _ = sigil
            same = self.target and self.target[0] == "sigil" and abs(self.target[1] - cx) + abs(self.target[2] - cy) < 20 * scale
            self._track(self.target if same else ("sigil", cx, cy), t, dist)
            speed = self._speed()
            if speed is not None and speed < -5:
                press_at = t + (dist - SIGIL_TARGET) / -speed - self.sigil_lead
            elif dist <= SIGIL_TARGET:
                press_at = t
            else:
                return None
            if press_at <= t + LOOKAHEAD:
                return self._press(t, press_at, f"sigil d={dist:.0f} speed={-(speed or 0):.0f}px/s")
            return None

        if bar and bar[2] is not None:
            center, half, marker = bar
            self._track(("bar",), t, marker)
            speed = self._speed()
            if speed is None or abs(speed) < BAR_MIN_SPEED:
                return None
            if (center - marker) * speed > 0:
                press_at = t + (center - marker) / speed - self.bar_lead
            elif abs(marker - center) <= half:
                press_at = t
            else:
                return None
            if press_at <= t + LOOKAHEAD:
                return self._press(t, press_at, f"bar x={marker:.0f} center={center:.0f} speed={speed:.0f}px/s")
            return None

        if self.target and self.history and t - self.history[-1][0] > SPEED_WINDOW:
            self.target = None
            self.history.clear()
        return None


def replay(path, verbose=False):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    solver = MinigameSolver()
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        scale = frame.shape[1] / REF_W
        x0, y0, x1, y1 = _scaled_box(REGION, scale)
        crop = frame[y0:y1, x0:x1]
        t = i / fps
        if verbose:
            s, b = find_sigil(crop, scale), find_bar(crop, scale)
            if s or b:
                print(f"  frame {i}: sigil={s} bar={b}")
        hit = solver.update(crop, scale, t)
        if hit:
            press_at, label = hit
            print(f"frame {i}: PRESS at frame {press_at * fps:.1f} ({label})")
        i += 1


def pin_console(region):
    """Keep this console above the game, and warn if it would cover the captured panel."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    # Handles are 64-bit; without argtypes, HWND_TOPMOST (-1) would be passed as a 32-bit int.
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
    hwnd = kernel32.GetConsoleWindow()
    if not hwnd:
        return
    HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE = -1, 0x0002, 0x0001
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    r = region
    if rect.left < r["left"] + r["width"] and rect.right > r["left"] and rect.top < r["top"] + r["height"] and rect.bottom > r["top"]:
        print(f"[warning] this window overlaps the minigame area "
              f"({r['left']},{r['top']} to {r['left'] + r['width']},{r['top'] + r['height']}); move it aside")


def solve_loop(solver, dry_run=False, on_region=None):
    """Capture the panel and press Space for minigames while running, until Ctrl+3."""
    with mss.mss() as sct:
        mon = sct.monitors[1]
        scale = mon["width"] / REF_W
        x0, y0, x1, y1 = _scaled_box(REGION, scale)
        region = {"left": mon["left"] + x0, "top": mon["top"] + y0, "width": x1 - x0, "height": y1 - y0}
        if on_region:
            on_region(region)
        while not stopping.is_set():
            if not running.is_set():
                wait(0.1)
                continue
            t0 = time.perf_counter()
            crop = np.array(sct.grab(region))[:, :, :3]
            t = (t0 + time.perf_counter()) / 2
            hit = solver.update(crop, scale, t)
            if not hit:
                time.sleep(0.002)
                continue
            press_at, label = hit
            delay = press_at - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            if not dry_run and not stopping.is_set():
                pydirectinput.press("space", _pause=False)
            late = (time.perf_counter() - press_at) * 1000
            print(f"[minigame] SPACE ({label}, {late:+.0f}ms vs plan)")


def run(dry_run=False):
    start_listener()
    print("Minigame mode. Ctrl+2 = start, Ctrl+3 = stop." + (" [dry run]" if dry_run else ""))
    solve_loop(MinigameSolver(), dry_run, on_region=pin_console)
    print("bye")


def main():
    parser = argparse.ArgumentParser(description="Auto-play the ARCANE SIGILS and INCOMING! minigames")
    parser.add_argument("--dry-run", action="store_true", help="log presses without pressing")
    parser.add_argument("--replay", metavar="VIDEO", help="run the solver over a recording instead")
    parser.add_argument("-v", "--verbose", action="store_true", help="with --replay, print every detection")
    args = parser.parse_args()
    if args.replay:
        replay(args.replay, args.verbose)
    else:
        run(args.dry_run)


if __name__ == "__main__":
    main()
