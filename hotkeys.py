import threading
import time

from pynput import keyboard

# Virtual key codes for the top-row 2 and 3. Matched by vk because holding Ctrl
# turns the key's char into a control code.
VK_START, VK_STOP = 0x32, 0x33
VK_AUTOSELL = 0x34  # autosell: Ctrl+4 toggles auto-sell
VK_SCROLL = 0x31  # scroll first: Ctrl+1 toggles using the SCROLL as each battle's first move
CTRL_KEYS = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}

running = threading.Event()
stopping = threading.Event()
autosell_on = threading.Event()  # autosell
autosell_on.set()  # autosell: on by default, Ctrl+4 turns it off
scroll_first = threading.Event()  # scroll first
scroll_first.set()  # scroll first: on by default, Ctrl+1 turns it off
ctrl_held = set()


def on_press(key):
    if key in CTRL_KEYS:
        ctrl_held.add(key)
        return
    if not ctrl_held:
        return
    vk = getattr(key, "vk", None)
    if vk == VK_START and not running.is_set():
        running.set()
        print("[started]")
    elif vk == VK_SCROLL:  # scroll first
        if scroll_first.is_set():
            scroll_first.clear()
            print("[scroll first] OFF (skills from the first turn)")
        else:
            scroll_first.set()
            print("[scroll first] ON (SCROLL first, then skills)")
    elif vk == VK_AUTOSELL:  # autosell
        if autosell_on.is_set():
            autosell_on.clear()
            print("[autosell] OFF")
        else:
            autosell_on.set()
            print("[autosell] ON (checks gear after boss fights and halfway through a land)")
    elif vk == VK_STOP:
        # Ctrl+3 pauses; Ctrl+2 resumes. Close the window to quit.
        if running.is_set():
            running.clear()
            print("[paused] Ctrl+2 = resume, close this window to quit")


def on_release(key):
    ctrl_held.discard(key)


def start_listener():
    keyboard.Listener(on_press=on_press, on_release=on_release, daemon=True).start()


def wait(seconds):
    """Sleep, but return early (True) if the bot is quitting or gets paused (Ctrl+3).

    A wait that starts while already paused just sleeps, so the idle loop doesn't spin.
    """
    was_running = running.is_set()
    end = time.time() + seconds
    while True:
        left = end - time.time()
        if left <= 0:
            return stopping.is_set()
        if stopping.wait(min(left, 0.05)):
            return True
        if was_running and not running.is_set():
            return True
