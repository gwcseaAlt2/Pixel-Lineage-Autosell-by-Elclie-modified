# How to install

## 1. Install Python

1. Download Python 3 from https://www.python.org/downloads/
2. Run the installer. On the first screen, tick **Add python.exe to PATH**, then click **Install Now**.

## 2. Download the macro

1. On this GitHub page, click the green **Code** button, then **Download ZIP**.
2. Unzip it somewhere you'll find it, like your Documents folder.

## 3. First start

1. Open the unzipped folder and double-click **skills.bat**.
2. The first time, it says `Setting up .venv...` and installs what it needs. This can take a few minutes. Wait until it's done.
3. Leave that black window open. That's the bot's console.

## 4. Set up the game

- Windows only. Run Roblox **fullscreen on your main monitor**.
- Screen positions were measured at **1920x1080**. Other sizes or a different in game UI size may make it click in the wrong spots.

## 5. Use it

Switch to the game and press **Ctrl+2** to start.

| Key | What it does |
|---|---|
| Ctrl+2 | Start / resume |
| Ctrl+3 | Pause |
| Ctrl+1 | Use the scroll first in each battle, on / off (starts on) |
| Ctrl+4 | Auto-sell, on / off (starts on) |

Moving the mouse into a corner of the screen is an emergency stop. Close the console window to quit.

## 6. Commands

Click the console window, type one of these and press Enter:

| Command | What it does |
|---|---|
| `T=52` | Torment tier to pick when it reconnects after a disconnect |
| `help` | Show the item commands |
| `items` | List every gear piece and the Magic it needs to be kept |
| `items hat` | Only pieces with "hat" in the name |
| `top tempest hat 3` | Keep only the top 3% of Tempest Hats |
| `top all 5` | Every piece back to top 5% (the default) |

Your choices are saved, so you only set them once.

## 7. Before your first long run

1. **Lock** (in game) any gear you never want sold. Locked and equipped gear is never sold.
2. **Test auto-sell safely:** open `autosell.py` in Notepad, change `DRY_RUN = False` to `DRY_RUN = True` and save. The bot then clicks LOCK instead of SELL, so you can see what it would sell. Unlock those items, set it back to `False`, and save.
3. **Reconnect:** for it to start a new run after a disconnect, have **Torment** and **Today's Gauntlet** picked in the Solo Run screen once yourself.

More about the auto-sell rules: see `AUTOSELL_SETUP.txt`.

## Files it makes

| File | What's in it |
|---|---|
| `autosell_log\log.txt` | Every item it checked, and why it kept or sold it |
| `drops.csv` | One line per item, open it in Excel |
| `bot_stats.txt` | Runs, battles, boss fights, items sold |
| `stuck_screens\` | Screenshots when the bot seemed stuck |

## Problems

- **"Setup failed. Make sure Python is installed and on PATH."** Reinstall Python and tick **Add python.exe to PATH**.
- **It clicks the wrong spots.** Check the game is fullscreen at 1920x1080 on your main monitor.
- **It does wrong moves in battle.** Make sure only one console window (one skills.bat) is running.
