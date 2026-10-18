import argparse
import sys

import cv2
import numpy as np

from sell import TAN_RANGES, color_cover
from stage_select import grab_screen

# Battle action menu (bottom left), measured on 1024x576 and stored as fractions.
ROWS = ("attack", "skills", "scroll", "guard", "meditate", "satchel")
ROW_Y0, ROW_STEP = 443.5 / 576, 20.9 / 576  # center of ATTACK, gap between rows (remeasured on this PC)
ROW_HALF = 5 / 576
# Right part of each row: always empty background, so only the highlight changes it.
HIGHLIGHT_X = (140 / 1024, 170 / 1024)
TEXT_X = 60 / 1024

# Boxes stop at y 950 so they still work when boss fights add black bars over the bottom of the screen.
BORDER_BOX = (11 / 1024, 780 / 1080, 13 / 1024, 950 / 1080)  # light blue left edge of the panel
BODY_BOX = (130 / 1024, 780 / 1080, 165 / 1024, 950 / 1080)  # navy panel background
BORDER_RANGE = (((95, 50, 110), (115, 130, 170)),)
BODY_RANGE = (((100, 90, 30), (120, 200, 80)),)
# Right edge of the menu panel (light blue line). The wide BATTLE LOG has no line here, so this
# keeps log text from being read as a highlighted row. Measured on this PC.
MENU_EDGE_BOX = (340 / 1920, 800 / 1080, 380 / 1920, 950 / 1080)
MIN_COVER = 0.6

# Highlighted row background is ~20 brighter than the rest.
MIN_HIGHLIGHT_GAP = 10

# Bottom HUD, up for the whole battle in every layout (menu, skill list, minigame battle log).
# Top-right of the big middle panel is plain navy; stage select cards are navy there too, so the
# left border of the PARTY/FOES panel is required as well.
HUD_AREA = (1182 / 1920, 760 / 1080, 1375 / 1920, 880 / 1080)  # remeasured on this PC
HUD_EDGE_BOX = (1396 / 1920, 760 / 1080, 1416 / 1920, 950 / 1080)
HUD_MIN_COVER = 0.7

# Skill list popup (opened from SKILLS) and the BACK button that only exists while it's open.
BACK_BTN = (277 / 1920, 782 / 1080)  # remeasured on this PC
# Thin lines: each box must contain one column (border) / row (BACK edge) that's mostly line-colored.
SKILL_LIST_BORDER_BOX = (360 / 1920, 430 / 1080, 380 / 1920, 710 / 1080)  # left edge of the list
BACK_EDGE_BOX = (225 / 1920, 792 / 1080, 330 / 1920, 808 / 1080)  # bottom edge of BACK's tan outline
LINE_COVER = 0.8


def row_y(frame, i):
    return int((ROW_Y0 + i * ROW_STEP) * frame.shape[0])


def row_px(frame, name):
    return int(TEXT_X * frame.shape[1]), row_y(frame, ROWS.index(name))


def highlighted_row(frame):
    """Return the name of the highlighted menu row, or None if there's no clear highlight."""
    h, w = frame.shape[:2]
    x0, x1 = int(HIGHLIGHT_X[0] * w), int(HIGHLIGHT_X[1] * w)
    half = max(1, int(ROW_HALF * h))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    levels = [float(np.mean(gray[row_y(frame, i) - half:row_y(frame, i) + half, x0:x1])) for i in range(len(ROWS))]
    order = np.argsort(levels)
    if levels[order[-1]] - levels[order[-2]] < MIN_HIGHLIGHT_GAP:
        return None
    return ROWS[order[-1]]


def menu_visible(frame):
    return (
        color_cover(frame, BORDER_BOX, BORDER_RANGE) >= MIN_COVER
        and color_cover(frame, BODY_BOX, BODY_RANGE) >= MIN_COVER
        and line_cover(frame, MENU_EDGE_BOX, BORDER_RANGE, vertical=True) >= LINE_COVER
        and highlighted_row(frame) is not None
    )


def line_cover(frame, box, ranges, vertical):
    """Best fraction of line-colored pixels over the columns (vertical) or rows of box."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], bool)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, lo, hi) > 0
    return float(mask.mean(axis=0 if vertical else 1).max())


def hud_visible(frame):
    return (
        color_cover(frame, HUD_AREA, BODY_RANGE) >= HUD_MIN_COVER
        and line_cover(frame, HUD_EDGE_BOX, BORDER_RANGE, vertical=True) >= LINE_COVER
    )


def skill_list_open(frame):
    return (
        line_cover(frame, SKILL_LIST_BORDER_BOX, BORDER_RANGE, vertical=True) >= LINE_COVER
        and line_cover(frame, BACK_EDGE_BOX, TAN_RANGES, vertical=False) >= LINE_COVER
    )


# Boss fights have a gold-framed health bar across the top of the screen. Measured on this PC.
BOSS_BAR_BOX = (600 / 1920, 44 / 1080, 1400 / 1920, 58 / 1080)
BOSS_BAR_ROW = 0.9  # a row counts as frame if this much of it is gold
BOSS_BAR_MIN_ROWS = 2


def boss_bar_visible(frame):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = int(BOSS_BAR_BOX[0] * w), int(BOSS_BAR_BOX[1] * h), int(BOSS_BAR_BOX[2] * w), int(BOSS_BAR_BOX[3] * h)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    gold = (hsv[..., 0] >= 15) & (hsv[..., 0] <= 35) & (hsv[..., 1] > 80) & (hsv[..., 2] > 150)
    return int((gold.mean(axis=1) >= BOSS_BAR_ROW).sum()) >= BOSS_BAR_MIN_ROWS


# Boss fights start with black bars over the top and bottom of the screen, which hide the
# health bar. Only checked while the battle menu is up. Measured on this PC.
LETTERBOX_BOX = (100 / 1920, 970 / 1080, 1800 / 1920, 1070 / 1080)
LETTERBOX_MIN = 0.9


def letterbox_visible(frame):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = int(LETTERBOX_BOX[0] * w), int(LETTERBOX_BOX[1] * h), int(LETTERBOX_BOX[2] * w), int(LETTERBOX_BOX[3] * h)
    val = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)[..., 2]
    return float((val < 12).mean()) >= LETTERBOX_MIN


def to_px(frame, pt):
    h, w = frame.shape[:2]
    return int(pt[0] * w), int(pt[1] * h)


def main():
    parser = argparse.ArgumentParser(description="Check battle menu detection")
    parser.add_argument("image", nargs="?", help="screenshot to analyze (default: live screen)")
    args = parser.parse_args()

    frame = cv2.imread(args.image) if args.image else grab_screen()
    if frame is None:
        sys.exit(f"Can't read {args.image}")
    print(f"menu visible: {menu_visible(frame)}")
    print(f"highlighted:  {highlighted_row(frame)}")
    print(f"skill list:   {skill_list_open(frame)}")
    print(f"HUD:          {hud_visible(frame)}")
    print(f"boss bar:     {boss_bar_visible(frame)}")
    print(f"black bars:   {letterbox_visible(frame)}")


if __name__ == "__main__":
    main()
