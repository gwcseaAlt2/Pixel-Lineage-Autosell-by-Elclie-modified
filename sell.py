import argparse
import sys

import cv2

from buttons import TAN_HIGH, TAN_LOW
from stage_select import grab_screen

# Everything below is (x, y) or (x0, y0, x1, y1) as fractions of screen size, measured on 1024x576.
def _pt(x, y):
    return x / 1024, y / 576


def _box(x0, y0, x1, y1):
    return x0 / 1024, y0 / 576, x1 / 1024, y1 / 576


GEAR_BTN = _pt(111, 529)
SELL_MANY_TAB = _pt(502, 140)
RARITY_BTNS = {
    "common": _pt(496, 392),
    "uncommon": _pt(553, 392),
    "rare": _pt(609, 392),
    "epic": _pt(665, 392),
}
SELL_BTN = _pt(611, 424)
CLOSE_BTN = _pt(751, 140)

# Inner parts of each button, used to check what's on screen.
GEAR_BOX = _box(82, 521, 140, 538)  # bright tan only when no popup dims the sidebar
CLOSE_BOX = _box(743, 133, 759, 147)  # red X of the gear menu
SELLING_TAB_BOX = _box(482, 134, 522, 146)  # SELL MANY tab, red ("SELLING") in sell mode

RED_RANGES = (((0, 100, 100), (8, 255, 255)), ((170, 100, 100), (180, 255, 255)))
TAN_RANGES = ((TAN_LOW, TAN_HIGH),)
MIN_COVER = 0.6

STEP_DELAY = 0.25
SELL_PANEL_DELAY = 0.5
SELL_CONFIRM_DELAY = 0.5
OPEN_TIMEOUT = 3.0


def color_cover(frame, box, ranges):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, *ranges[0])
    for lo, hi in ranges[1:]:
        mask |= cv2.inRange(hsv, lo, hi)
    return cv2.countNonZero(mask) / mask.size


def gear_ready(frame):
    return color_cover(frame, GEAR_BOX, TAN_RANGES) >= MIN_COVER


def menu_open(frame):
    return color_cover(frame, CLOSE_BOX, RED_RANGES) >= MIN_COVER


def sell_panel_open(frame):
    return color_cover(frame, SELLING_TAB_BOX, RED_RANGES) >= MIN_COVER


def to_px(frame, pt):
    h, w = frame.shape[:2]
    return int(pt[0] * w), int(pt[1] * h)


def run_sell(click, grab, wait):
    """Open GEAR > SELL MANY, pick every rarity but CLEAR, sell, close. Returns True on success.

    click(pos) clicks, grab() returns a frame, wait(s) sleeps and returns True if stopping.
    """

    def wait_for(check):
        for _ in range(int(OPEN_TIMEOUT / 0.1)):
            if wait(0.1):
                return False
            if check(grab()):
                return True
        return False

    frame = grab()
    print("[sell] open gear")
    click(to_px(frame, GEAR_BTN))
    if not wait_for(menu_open):
        print("[sell] gear menu didn't open")
        return False

    try:
        print("[sell] sell many")
        click(to_px(frame, SELL_MANY_TAB))
        if wait(SELL_PANEL_DELAY):
            return False
        if not menu_open(grab()):
            print("[sell] gear menu closed unexpectedly")
            return False

        for name, pt in RARITY_BTNS.items():
            print(f"[sell] pick {name}")
            click(to_px(frame, pt))
            if wait(STEP_DELAY):
                return False

        for n in (1, 2):
            print(f"[sell] sell ({n}/2)")
            click(to_px(frame, SELL_BTN))
            if wait(SELL_CONFIRM_DELAY):
                return False
        return True
    finally:
        for _ in range(3):
            if not menu_open(grab()):
                break
            print("[sell] close menu")
            click(to_px(frame, CLOSE_BTN))
            if wait(0.5):
                break


def main():
    parser = argparse.ArgumentParser(description="Check the sell routine's screen detection")
    parser.add_argument("image", nargs="?", help="screenshot to analyze (default: live screen)")
    args = parser.parse_args()

    frame = cv2.imread(args.image) if args.image else grab_screen()
    if frame is None:
        sys.exit(f"Can't read {args.image}")
    print(f"gear ready: {gear_ready(frame)}")
    print(f"menu open:  {menu_open(frame)}")
    print(f"sell panel: {sell_panel_open(frame)}")


if __name__ == "__main__":
    main()
