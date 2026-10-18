import ctypes

import mss
import numpy as np
import pygetwindow as gw

# Without this, Windows display scaling makes window coords and screenshot pixels disagree.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    ctypes.windll.user32.SetProcessDPIAware()


def find_window(title):
    # Exact match so editors/browsers with "Roblox" in their title are ignored.
    for win in gw.getAllWindows():
        if win.title == title and not win.isMinimized and win.width > 0 and win.height > 0:
            return win
    return None


def window_region(win):
    return {"left": win.left, "top": win.top, "width": win.width, "height": win.height}


def grab(sct: mss.base.MSSBase, region):
    return np.array(sct.grab(region))[:, :, :3]
