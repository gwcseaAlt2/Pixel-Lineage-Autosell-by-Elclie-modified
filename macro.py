import argparse
import json
import sys
import threading
import time
from pathlib import Path

import cv2
import mss
import pydirectinput
from pynput import keyboard

from screen import find_window, grab, window_region

ROOT = Path(__file__).parent
pydirectinput.PAUSE = 0.02

running = threading.Event()
quitting = threading.Event()


def load_targets(config):
    targets = []
    for t in config["targets"]:
        if not t.get("enabled", True):
            continue
        path = ROOT / t["image"]
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            print(f"[skip] {t['name']}: can't read {path}")
            continue
        targets.append({**t, "template": img, "last_click": 0.0})
    return targets


def find(haystack, template, threshold):
    th, tw = template.shape[:2]
    if th > haystack.shape[0] or tw > haystack.shape[1]:
        return None
    result = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(result)
    if score < threshold:
        return None
    return x + tw // 2, y + th // 2, score


def click(x, y, button):
    pydirectinput.moveTo(x, y)
    # Roblox sometimes ignores a click unless the cursor moved right before it.
    pydirectinput.moveRel(1, 0)
    pydirectinput.click(button=button)


def on_press(key):
    if key == keyboard.Key.f6:
        if running.is_set():
            running.clear()
            print("[paused]")
        else:
            running.set()
            print("[running]")
    elif key == keyboard.Key.f8:
        quitting.set()
        return False


def main():
    parser = argparse.ArgumentParser(description="Image search click macro for Roblox")
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--dry-run", action="store_true", help="log matches without clicking")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    targets = load_targets(config)
    if not targets:
        sys.exit("No usable targets. Capture some with capture.py and enable them in config.json.")

    title = config.get("window_title", "Roblox")
    interval = config.get("scan_interval", 0.2)
    cooldown = config.get("click_cooldown", 0.5)

    keyboard.Listener(on_press=on_press, daemon=True).start()
    print(f"Loaded {len(targets)} target(s). F6 = start/pause, F8 = quit."
          + (" [dry run]" if args.dry_run else ""))

    with mss.mss() as sct:
        while not quitting.is_set():
            if not running.is_set():
                time.sleep(0.1)
                continue

            win = find_window(title)
            if win is None:
                print(f"[wait] window '{title}' not found")
                time.sleep(1)
                continue

            region = window_region(win)
            frame = grab(sct, region)
            now = time.time()

            for t in targets:
                if now - t["last_click"] < cooldown:
                    continue
                hit = find(frame, t["template"], t.get("threshold", 0.85))
                if hit is None:
                    continue
                x, y, score = hit
                dx, dy = t.get("offset", [0, 0])
                sx, sy = region["left"] + x + dx, region["top"] + y + dy
                print(f"[hit] {t['name']} {score:.2f} at ({sx}, {sy})")
                if not args.dry_run:
                    try:
                        click(sx, sy, t.get("button", "left"))
                    except pydirectinput.FailSafeException:
                        print("[failsafe] mouse in screen corner, quitting")
                        return
                t["last_click"] = now
                # Screen changed after a click, so rescan before trying other targets.
                break

            time.sleep(interval)

    print("bye")


if __name__ == "__main__":
    main()
