import argparse
import ctypes
import sys

import cv2
import mss
import numpy as np

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    ctypes.windll.user32.SetProcessDPIAware()

# Layout measured on a 1024x576 fullscreen capture, stored as fractions of screen size.
STAR_AREA = (0.818, 0.33, 0.905, 0.90)  # remeasured on this PC  # x0, y0, x1, y1 covering every card's reward stars
CARD_CLICK_X = 0.57
BASE_WIDTH = 1024

GOLD_LOW = (15, 90, 150)
GOLD_HIGH = (35, 255, 255)

PRIORITY = (5, 3)


def read_rewards(frame):
    """Return [(reward_stars, row_y), ...] top to bottom, in frame pixels."""
    h, w = frame.shape[:2]
    x0, y0 = int(STAR_AREA[0] * w), int(STAR_AREA[1] * h)
    x1, y1 = int(STAR_AREA[2] * w), int(STAR_AREA[3] * h)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, GOLD_LOW, GOLD_HIGH)

    scale = w / BASE_WIDTH
    # Stars are ~6x5 at 1024 wide; the cap keeps gold buttons (e.g. BUY) from counting.
    min_area = 10 * scale * scale
    max_area = 60 * scale * scale
    row_gap = 8 * scale

    n, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
    ys = sorted(
        centroids[i][1] + y0
        for i in range(1, n)
        if min_area <= stats[i][cv2.CC_STAT_AREA] <= max_area
    )

    rows = []
    for y in ys:
        if rows and y - rows[-1][-1] <= row_gap:
            rows[-1].append(y)
        else:
            rows.append([y])
    return [(len(r), int(np.mean(r))) for r in rows]


def pick_stage(frame):
    """Return (card_index, reward, (x, y)) for the best card, or None."""
    rewards = read_rewards(frame)
    for want in PRIORITY:
        for i, (stars, y) in enumerate(rewards):
            if stars == want:
                return i, stars, (int(CARD_CLICK_X * frame.shape[1]), y)
    return None


_sct = None


def grab_screen():
    # mss handles are per-thread on Windows; only call this from one thread.
    global _sct
    if _sct is None:
        _sct = mss.mss()
    return np.array(_sct.grab(_sct.monitors[1]))[:, :, :3]


def main():
    parser = argparse.ArgumentParser(description="Pick the stage card with the best reward")
    parser.add_argument("image", nargs="?", help="screenshot to analyze (default: live screen)")
    args = parser.parse_args()

    frame = cv2.imread(args.image) if args.image else grab_screen()
    if frame is None:
        sys.exit(f"Can't read {args.image}")

    for i, (stars, y) in enumerate(read_rewards(frame)):
        print(f"card {i + 1}: reward {stars} (y={y})")

    choice = pick_stage(frame)
    if choice is None:
        print("no reward 5 or 3 card found")
    else:
        i, stars, (x, y) = choice
        print(f"pick card {i + 1} (reward {stars}) -> click ({x}, {y})")


if __name__ == "__main__":
    main()
