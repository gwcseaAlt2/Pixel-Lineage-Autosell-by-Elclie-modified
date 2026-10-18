import ctypes
import time
from ctypes import wintypes

# Report real pixels, not values shrunk by Windows display scaling.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    ctypes.windll.user32.SetProcessDPIAware()


def get_mouse_pos():
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def main():
    print("Move your mouse. Ctrl+C to quit.")
    try:
        while True:
            x, y = get_mouse_pos()
            print(f"\rX: {x:5d}  Y: {y:5d}", end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
