# pixel-lineage-macro

A screen-reading macro that plays a 2D Roblox roguelike RPG on its own. It watches the screen, decides what's showing, and clicks buttons, picks stages, sells gear, and taps Space to fight.

Windows only. It assumes the game runs fullscreen on the primary monitor.

## Quick start

Run **`skills.bat`**, switch to the game, and press **Ctrl+2**. That's the main mode: it casts skills, then ATTACKs, plays the minigames, skips the post-battle screens, and handles every popup and stage pick. The first run creates `.venv` and installs the requirements.

| File | What it does |
|---|---|
| `skills.bat` | **Main mode.** Skill mode for harder stages: casts skills, then ATTACKs, and plays the minigames. |
| `run.bat` | Older scroll mode: spams Space to use the SCROLL every turn, with GUARD as a fallback. All the other `.bat` files go through it to set up `.venv`. |
| `sell_test.bat` | Runs the gear sell routine once, then exits. |
| `minigame.bat` | Standalone mode that only plays the minigames. |

Hotkeys work from any window: **Ctrl+2** starts, **Ctrl+3** stops and exits. Moving the mouse into a screen corner is an emergency stop.

`skills.bat --dry-run` (or `run.bat --dry-run`) logs what the bot would do without clicking or pressing keys.

## How it works

### Screen capture and coordinates

- Each loop takes a screenshot of the primary monitor with `mss`. One capture object is reused, and a full scan takes about 40–50 ms.
- The process is set DPI-aware, so screenshot pixels and mouse coordinates line up even with Windows display scaling.
- Every position and search area is stored as a fraction of the screen size. They were measured on 1024×576 screenshots and work at any resolution, including 1920×1080.
- Nothing uses image templates. Each detector checks colors in HSV inside a fixed area, then looks for blobs with the right size, aspect ratio, and fill.

### Input

- Clicks and key presses go through `pydirectinput`, which uses `SendInput` with scan codes, so the game registers them reliably.
- Before every click, the cursor moves 1 px. Roblox sometimes ignores a click when the cursor hasn't just moved.
- A background thread presses Space every 0.1 s while the bot runs. It pauses while selling and while the battle pointer is being reset. In skill mode it only runs after a battle ends.
- Hotkeys come from a `pynput` low-level keyboard hook and are matched by virtual-key code. Holding Ctrl changes the character Python sees for 2 and 3, so the code checks the key itself.

### Main loop (`bot.py`)

Each scan checks the screen in this order. The first match acts, and the loop starts over.

1. **Gear menu left open:** if its red X is visible, click X.
2. **Battle end:** the bottom HUD (see below) is tracked on every scan. When it has been up at least 1 s and then disappears, the battle is over. The bot marks a new battle and spams Space to skip the victory screens. This also happens in skill mode. The spam keeps going through every post-battle screen (including the boss chest cutscene) until the **CONTINUE** popup appears, a stage select with a pickable card is on screen (not every stage select has the popup), or **PLAY AGAIN** shows up because the run ended. Until then, the rest of the loop is skipped, so nothing in a cutscene gets clicked or misread as a card. It also stops if the HUD comes back, or after 30 s. While spamming, the bot scans every 20 ms, so few Spaces land on the next screen before the spam stops. The log says what ended the spam.
   - **Idle click:** outside battle, if the bot hasn't clicked or pressed a key for 20 s, it clicks the bottom-right corner. That spot is empty ground on every non-battle screen.
3. **Battle menu**
   - When the scroll hits, Space spam handles it and the menu goes away.
   - If the menu stays on screen for 2 s or more, the bot assumes the scroll missed and clicks **GUARD**.
   - After a battle where it guarded, the pointer is left on GUARD. In the next battle, Space stays paused. Once the menu has been up 0.5 s, it presses **W** (or **S**) until the **SCROLL** row is highlighted, then resumes Space.
4. **Popup buttons**, checked in this order:
   - **PLAY AGAIN** on the run complete popup. The popup has either 2 buttons (PLAY AGAIN on the right) or 3 (PLAY AGAIN in the middle, NEXT on the right), and its height changes with the loot list. The bot finds the button row by its height. It counts as this popup when the row has two tan buttons, or one tan button right of center (CONTINUE is a single centered button). It then clicks at x = 540/1024, which is on PLAY AGAIN in both layouts.
   - **CONTINUE**, the popup button in the middle of the screen.
   - **TO BATTLE**, the large yellow button in the shop column. Its height can change.
5. **Settle check:** cards are only picked after 1 s with no button click, and 3 s after the last card click.
6. **Sell gear** (only if `AUTO_SELL` is on) after every `SELL_EVERY` PLAY AGAIN clicks, once the GEAR button is bright, meaning no popup covers it.
7. **Stage pick:** pick a card on the stage select screen.

After any click, there's a 0.5 s cooldown before the next one.

### Stage selection (`stage_select.py`)

- In the reward star strip on the right of the cards, it masks gold pixels. Red danger stars and grey empty stars are ignored.
- Gold blobs of star size are grouped into one row per card. Size limits keep gold buttons such as BUY from counting.
- Each row's star count is that card's reward.
- It picks the first card with **reward 5**, otherwise the first with **reward 3**. Cards with reward 4 or 2 are never picked.
- Before clicking, it waits 0.3 s and checks again. If a button appeared or the stars changed, it skips the click.

### Popup buttons (`buttons.py`)

- All three buttons are solid tan rectangles: HSV hue 10–35, high value.
- In each button's search area, the bot looks for a tan blob with the right width, an aspect ratio of 3.5–8, and at least 85% fill.
- The search areas leave out the tan CHARACTER and GEAR buttons in the sidebar. The width limits leave out the BUY buttons, which are in the same column as TO BATTLE.

### Gear selling (`sell.py`)

1. Click **GEAR**, then wait up to 3 s for the gear menu's red X to appear.
2. Click **SELL MANY**, wait 0.5 s, and check that the red X is still there.
3. Click **COMMON**, **UNCOMMON**, **RARE**, and **EPIC**, 0.25 s apart. **CLEAR** is never clicked.
4. Click the red **SELL** button twice, 0.5 s apart.
5. Click **X** to close, up to 3 times until the red X is gone. This also runs if an earlier step fails.

Space is paused for the whole routine. If it fails, the bot tries again 5 s later.

### Battle menu (`battle.py`)

- The menu counts as visible when three things are all true:
  - Its light-blue left border is present.
  - Its navy background is present.
  - Exactly one row is highlighted.
- The highlighted row is the one whose empty background area is clearly brighter than the rest, by at least 10 grey levels. That gives the pointer's position: ATTACK, SKILLS, SCROLL, GUARD, MEDITATE, or SATCHEL.
- The **HUD** counts as visible when both of these are true:
  - The top-right part of the big middle panel is at least 70% navy.
  - The light-blue left border of the PARTY/FOES panel is present.
  The navy check on its own also matches the third stage card. The border check keeps it working when the HUD switches to the wide BATTLE LOG during enemy turns and minigames.

### Skill mode (`skills.py`, `bot.py --skills`)

Skill mode replaces the constant Space spam (only the post-battle spam stays) and the scroll/GUARD logic. The popup buttons, stage picks, and selling work the same as in normal mode.

- **The minigame solver** runs in its own thread the whole time (see below). The bot doesn't press anything while a minigame was on screen in the last 0.5 s.
- **Turn start:** the battle menu has to be up for 0.2 s. If a skill list was left open, the bot clicks BACK first.
- **Pointer:** the bot reads which main menu row is highlighted and presses W or S until it's on the row it wants. For the first `len(SKILL_PICKS)` turns of a battle that's SKILLS, then ATTACK. In practice, that's W once to get to ATTACK after the skills, and S once to get back to SKILLS in the next battle.
- **Skill cast:**
  1. SPACE opens the list. The bot waits up to 0.5 s for the list to appear: it checks for the list's left border and the BACK button.
  2. W × `SKILL_PICKS[n]` picks the skill (3 for the first, 2 for the second).
  3. SPACE × 2, 30 ms apart, confirms the skill and its target. With a single enemy, the second press is ignored.
- **Attack:** SPACE × 2.
- **Did it go through?** An action counts once a minigame appears or the battle menu goes away, within 2 s. If not, the bot clicks BACK, then clicks SKILLS (which opens the list without a Space), then repeats the W presses and SPACE × 2. After 3 failed tries, it gives up on skills and attacks for the rest of that battle.
- **New battle:** the HUD disappearing, or any popup button or card click, marks the start of a new battle, which resets the skill count.

### Minigames (`minigame.py`, also standalone)

Run `minigame.bat`, start a battle yourself, and press Ctrl+2. The solver only presses Space when a minigame is on screen.

- To keep scans fast, it only captures the panel area (840×360 at 1080p). That gives about 57 scans per second.
- **ARCANE SIGILS:** it finds the purple rune, then measures the distance from the rune's center to the shrinking white frame. From the last 0.25 s of samples it works out the shrink speed and predicts when the frame will reach `SIGIL_TARGET` = 25 px. All three PERFECT presses in the reference recording registered at that distance.
- **INCOMING!:** it finds the white DODGE zone and the red marker on the bar. From the marker's speed (about 1000 px/s) it predicts when the marker will reach the zone center. It ignores the marker while it's blinking at the start.
- In both games, the press is scheduled for the predicted moment minus a lead time (`SIGIL_LEAD` / `BAR_LEAD`, 30 ms) to cover input delay. It sleeps until then, presses, and logs how late the press was compared with the plan.
- `python minigame.py --replay video.mp4` runs the solver over a recording and prints the frame where each press would happen. Use it to tune the timing values.

## Tuning

Timings are constants at the top of `bot.py`:

| Constant | Default | Meaning |
|---|---|---|
| `SCAN_INTERVAL` | 0.1 s | Pause between screen scans |
| `CLICK_COOLDOWN` | 0.5 s | Minimum gap between clicks |
| `SETTLE_DELAY` | 1.0 s | Time with no button click needed before a card can be picked |
| `CONFIRM_DELAY` | 0.3 s | Wait before the second look at the cards |
| `CARD_REPICK_DELAY` | 3.0 s | No second card pick within this window |
| `SPACE_INTERVAL` | 0.1 s | Time between Space presses |
| `AUTO_SELL` | False | Turn the automatic gear sell on or off |
| `SELL_EVERY` | 1 | PLAY AGAIN clicks between gear sells |
| `GUARD_AFTER` | 2.0 s | How long the battle menu can stay up before GUARD is clicked |
| `MENU_LOAD_DELAY` | 0.5 s | Wait before moving the pointer in the next battle |
| `HUD_MIN` | 1.0 s | How long the HUD must be up for its disappearance to count as a battle end |
| `POST_BATTLE_SPAM` | 30.0 s | Longest post-battle Space spam if neither CONTINUE nor a stage select shows up |
| `IDLE_CLICK_AFTER` | 20.0 s | Time outside battle with no click or key press before the corner click |

Sell step delays are at the top of `sell.py`.

## Debug tools

Each detector can be run by itself, on the live screen or on a saved screenshot:

```powershell
.\.venv\Scripts\python stage_select.py samples\stage_select.png
.\.venv\Scripts\python buttons.py samples\shop.png
.\.venv\Scripts\python sell.py samples\sell_menu.png
.\.venv\Scripts\python battle.py samples\battle.png
.\.venv\Scripts\python mouse_pos.py   # live cursor X/Y
```

`samples/` contains the reference screenshots the detectors were measured on.

## Other files

`macro.py`, `capture.py`, `screen.py`, and `config.json` make up the original general-purpose macro: it matches images listed in `config.json` and clicks them. `bot.py` only borrows its click helper from `macro.py`.
