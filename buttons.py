import argparse
import sys

import cv2

from stage_select import grab_screen

TAN_LOW = (10, 60, 150)
TAN_HIGH = (35, 255, 255)

MIN_ASPECT, MAX_ASPECT = 3.5, 8.0
MIN_FILL = 0.85

# Areas are (x0, y0, x1, y1) and widths are fractions of screen size, measured on 1024x576.
# CONTINUE: 106x19 popup button in the middle. Area excludes the tan sidebar buttons.
CONTINUE_AREA = (0.3, 0.25, 0.7, 0.93)  # remeasured on this PC
CONTINUE_WIDTH = (0.10, 0.18)
# Big "TO BATTLE" button: 112x21 at x 685-797, any height. The BUY buttons share
# this column but are ~45px wide, so the width range filters them out.
BATTLE_AREA = (0.64, 0.1, 0.90, 0.95)  # remeasured on this PC
BATTLE_WIDTH = (0.10, 0.16)
# Run complete popup, two layouts; its height depends on the loot list:
#   RETURN TO CASTLE | PLAY AGAIN (x 515-620)
#   RETURN TO CASTLE | PLAY AGAIN (x 464-560) | NEXT (x 564-660, tan too)
# CONTINUE is a single tan button centered at x 512, so the run complete row is the one with
# two tan buttons or one right of center. x 540 is on PLAY AGAIN in both layouts.
PLAY_AGAIN_AREA = (0.44, 0.45, 0.66, 0.85)
PLAY_AGAIN_WIDTH = (0.08, 0.12)
PLAY_AGAIN_X = 540 / 1024
OFF_CENTER_X = 530 / 1024
SAME_ROW = 6 / 576


def find_buttons(frame, area, width_range):
    """Return (x, y) centers of all solid tan buttons in area."""
    h, w = frame.shape[:2]
    x0, y0 = int(area[0] * w), int(area[1] * h)
    x1, y1 = int(area[2] * w), int(area[3] * h)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, TAN_LOW, TAN_HIGH)

    found = []
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    for i in range(1, n):
        x, y, bw, bh, px = stats[i]
        if not (width_range[0] * w <= bw <= width_range[1] * w):
            continue
        if not (MIN_ASPECT <= bw / bh <= MAX_ASPECT):
            continue
        if px / (bw * bh) < MIN_FILL:
            continue
        found.append((int(x0 + x + bw // 2), int(y0 + y + bh // 2)))
    return found


def find_button(frame, area, width_range):
    """Return (x, y) center of the first solid tan button in area, or None."""
    found = find_buttons(frame, area, width_range)
    return found[0] if found else None


def find_continue(frame):
    return find_button(frame, CONTINUE_AREA, CONTINUE_WIDTH)


def find_battle(frame):
    return find_button(frame, BATTLE_AREA, BATTLE_WIDTH)


def find_play_again(frame):
    h, w = frame.shape[:2]
    found = find_buttons(frame, PLAY_AGAIN_AREA, PLAY_AGAIN_WIDTH)
    for cx, cy in found:
        row = [x for x, y in found if abs(y - cy) <= SAME_ROW * h]
        if len(row) >= 2 or cx > OFF_CENTER_X * w:
            return int(PLAY_AGAIN_X * w), cy
    return None


# "Make your choice" events (camp, altar...): TO BATTLE is grayed out until an option is picked.
# Pick the bottom option (e.g. WALK AWAY, SHARPEN UP). Measured on this PC (1920x1080).
CHOICE_DISABLED_BOX = (1380 / 1920, 715 / 1080, 1615 / 1920, 752 / 1080)  # grayed-out TO BATTLE
CHOICE_DISABLED_RANGE = ((10, 80, 90), (35, 200, 170))
CHOICE_ACCENT_BOX = (630 / 1920, 600 / 1080, 637 / 1920, 670 / 1080)  # bright left edge of option 2
CHOICE_ACCENT_RANGE = ((0, 150, 200), (180, 255, 255))
CHOICE_CLICK = (1130 / 1920, 635 / 1080)  # middle of the bottom option
CHOICE_MIN_COVER = 0.7


def _cover(frame, box, rng):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    return cv2.countNonZero(cv2.inRange(hsv, *rng)) / max(1, (y1 - y0) * (x1 - x0))


def find_choice(frame):
    if _cover(frame, CHOICE_DISABLED_BOX, CHOICE_DISABLED_RANGE) < CHOICE_MIN_COVER:
        return None
    if _cover(frame, CHOICE_ACCENT_BOX, CHOICE_ACCENT_RANGE) < CHOICE_MIN_COVER:
        return None
    h, w = frame.shape[:2]
    return int(CHOICE_CLICK[0] * w), int(CHOICE_CLICK[1] * h)


def main():
    parser = argparse.ArgumentParser(description="Find the PLAY AGAIN / CONTINUE / TO BATTLE buttons")
    parser.add_argument("image", nargs="?", help="screenshot to analyze (default: live screen)")
    args = parser.parse_args()

    frame = cv2.imread(args.image) if args.image else grab_screen()
    if frame is None:
        sys.exit(f"Can't read {args.image}")

    print(f"play again: {find_play_again(frame)}")
    print(f"continue:   {find_continue(frame)}")
    print(f"battle:     {find_battle(frame)}")
    print(f"choice:     {find_choice(frame)}")


if __name__ == "__main__":
    main()
