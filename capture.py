import argparse
import json
import sys
from pathlib import Path

import cv2
import mss

from screen import find_window, grab, window_region

ROOT = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(description="Crop a template image from the Roblox window")
    parser.add_argument("name", help="saved as images/<name>.png")
    args = parser.parse_args()

    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    title = config.get("window_title", "Roblox")
    win = find_window(title)
    if win is None:
        sys.exit(f"Window '{title}' not found. Open the game (not minimized) and retry.")

    with mss.mss() as sct:
        frame = grab(sct, window_region(win))

    print("Drag a box around the target, then press ENTER/SPACE. Press C to cancel.")
    x, y, w, h = cv2.selectROI("capture - select target", frame, showCrosshair=True)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        sys.exit("Cancelled.")

    out = ROOT / "images" / f"{args.name}.png"
    out.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(out), frame[y:y + h, x:x + w])
    print(f"Saved {out.relative_to(ROOT)} ({w}x{h}). Add it to config.json targets if it's new.")


if __name__ == "__main__":
    main()
