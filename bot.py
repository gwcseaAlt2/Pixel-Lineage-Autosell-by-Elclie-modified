import argparse
import threading
import time

import pydirectinput

from battle import ROWS, highlighted_row, hud_visible, menu_visible, row_px
from buttons import find_battle, find_choice, find_continue, find_play_again
from hotkeys import running, start_listener, stopping, wait
from hotkeys import autosell_on  # autosell
from autosell import halfway, run_autosell  # autosell
import reconnect  # reconnect
import stats  # stats
from macro import click
from minigame import MinigameSolver, solve_loop
from sell import CLOSE_BTN, gear_ready, menu_open, run_sell, to_px
from skills import SkillBattle
from stage_select import grab_screen, pick_stage

SCAN_INTERVAL = 0.1
# Minimum gap between any two clicks, so one button isn't clicked twice.
CLICK_COOLDOWN = 0.5
# Cards are only picked after this long with no button click.
SETTLE_DELAY = 1.0
# Second look before clicking a card, in case a popup was still fading in.
CONFIRM_DELAY = 0.3
# The stage select can linger while the next screen loads; don't pick a card again in that window.
CARD_REPICK_DELAY = 3.0
SPACE_INTERVAL = 0.1
AUTO_SELL = False
# Sell gear after this many PLAY AGAIN clicks, once the GEAR button is usable.
SELL_EVERY = 1
SELL_RETRY_DELAY = 5.0
# Battle menu still up this long means the scroll missed/was used: click GUARD.
GUARD_AFTER = 2.0
# Next battle after a GUARD: menu must be up this long before moving the pointer.
MENU_LOAD_DELAY = 0.5
KEY_SETTLE = 0.3
# HUD must have been up this long for its disappearance to count as a battle ending.
HUD_MIN = 1.0
# Post-battle Space spam gives up after this long if neither CONTINUE nor a stage select shows up.
POST_BATTLE_SPAM = 30.0
# Faster scans while spamming, so few Spaces land on the stage select before the spam stops.
POST_BATTLE_SCAN = 0.02
# Outside battle, no click/key for this long means something is stuck: click an empty corner.
IDLE_CLICK_AFTER = 20.0
# Bottom-right edge: empty ground on stage select, shop, popups and run complete.
IDLE_CLICK_POS = (1014 / 1024, 570 / 576)
# stats: no real click/key (idle clicks don't count) for this long = probably stuck, save a screenshot.
STUCK_AFTER = 300.0
STUCK_REPEAT = 600.0  # while still stuck, another screenshot this often

# PLAY AGAIN first: its popup also passes the CONTINUE size/position check.
BUTTONS = (
    ("play again", find_play_again),
    ("continue", find_continue),
    ("battle", find_battle),
    ("choice", find_choice),
)
# Every stage select opens with CONTINUE or straight on the cards; PLAY AGAIN if the run ended.
POST_BATTLE_ENDS = (
    ("CONTINUE", find_continue),
    ("PLAY AGAIN", find_play_again),
    ("stage", pick_stage),
)

# Space could press things inside the gear menu, so spamming pauses while this is set.
selling = threading.Event()
# Set after a battle where GUARD was clicked: the pointer is left on GUARD, so Space stays
# paused until the next battle's pointer is moved back to SCROLL.
fixing_pointer = threading.Event()
# Set from the HUD vanishing until a popup button / stage select appears: Space skips the
# victory screens faster than waiting for CONTINUE. Overrides fixing_pointer (no menu there).
post_battle = threading.Event()


def find_any_button(frame):
    for name, finder in BUTTONS:
        pos = finder(frame)
        if pos:
            return name, pos
    return None


def spam_space(always):
    while not stopping.is_set():
        active = post_battle.is_set() or (always and not fixing_pointer.is_set())
        if not running.is_set() or selling.is_set() or not active:
            wait(0.1)
            continue
        try:
            pydirectinput.press("space", _pause=False)
        except pydirectinput.FailSafeException:
            print("[failsafe] mouse in screen corner, stopping")
            stopping.set()
            return
        wait(SPACE_INTERVAL)


def sell_test(do_click):
    print("[sell test] Ctrl+2 = sell once, Ctrl+3 = cancel.")
    while not running.is_set():
        if wait(0.1):
            return
    while not gear_ready(grab_screen()):
        print("[sell test] GEAR button not visible (popup open?), retrying...")
        if wait(1.0):
            return
    ok = run_sell(do_click, grab_screen, wait)
    print("[sell test] success" if ok else "[sell test] failed")


def main():
    parser = argparse.ArgumentParser(description="Clicks popup buttons and picks the best stage")
    parser.add_argument("--dry-run", action="store_true", help="log actions without clicking")
    parser.add_argument("--sell-test", action="store_true", help="run the gear sell routine once, then exit")
    parser.add_argument("--skills", action="store_true",
                        help="skill mode: cast skills then ATTACK each battle, auto-play minigames, "
                             "Space spam only after battles")
    args = parser.parse_args()

    last_activity = time.time()
    progress = {"t": time.time(), "saved": 0.0}  # stats: last real click/key, last stuck screenshot

    def do_click(pos, idle=False):
        nonlocal last_activity
        last_activity = time.time()
        if not idle:
            progress["t"] = time.time()  # stats
        if not args.dry_run and not stopping.is_set() and running.is_set():  # paused: no clicks
            click(*pos, "left")

    def do_key(key):
        nonlocal last_activity
        last_activity = time.time()
        progress["t"] = time.time()  # stats
        if not args.dry_run and not stopping.is_set() and running.is_set():  # paused: no keys
            pydirectinput.press(key)

    start_listener()
    reconnect.start_console()  # reconnect: type T=52 in this window to change the torment tier
    if args.sell_test:
        sell_test(do_click)
        return
    skill_battle = None
    if args.skills:
        solver = MinigameSolver()
        threading.Thread(target=solve_loop, args=(solver, args.dry_run), daemon=True).start()
        skill_battle = SkillBattle(do_key, do_click, grab_screen, wait, lambda: solver.last_seen)
    if not args.dry_run:
        threading.Thread(target=spam_space, args=(not args.skills,), daemon=True).start()
    print(("[skill mode] " if args.skills else "") + "Ctrl+2 = start / resume, Ctrl+3 = pause."
          + (" [dry run]" if args.dry_run else ""))
    # help: every hotkey and console command
    print("  Ctrl+1 = scroll first on/off   Ctrl+4 = auto-sell on/off (both start on)")
    print("  Type in this window: T=52 (reconnect tier), help, items, top tempest hat 3, top all 5")

    last_button = 0.0
    last_card = 0.0
    play_agains = 0
    last_sell_try = 0.0
    menu_since = None
    guarded = False
    hud_since = None
    post_battle_until = 0.0
    autosold = False  # autosell: already ran on this Choose your path screen
    boss_loot = False  # autosell: a boss fight ended since the last gear check

    def left_battle():
        nonlocal guarded, boss_loot
        if skill_battle:
            if skill_battle.boss:  # autosell: remember the boss before new_battle() resets it
                boss_loot = True
                stats.bump("boss fights")  # stats
            skill_battle.new_battle()
        if guarded:
            guarded = False
            fixing_pointer.set()
            print("[battle] left a GUARD battle, space paused until pointer is back on SCROLL")

    while not stopping.is_set():
        if not running.is_set():
            last_activity = time.time()
            progress["t"] = time.time()  # stats: being paused isn't being stuck
            wait(0.1)
            continue

        frame = grab_screen()
        # stats: nothing real done for STUCK_AFTER seconds, save what the screen looks like.
        now = time.time()
        if now - progress["t"] >= STUCK_AFTER and now - progress["saved"] >= STUCK_REPEAT:
            progress["saved"] = now
            path = stats.save_stuck(frame)
            print(f"[stuck] no progress for {(now - progress['t']) / 60:.0f} min, saved {path}")
        # reconnect: disconnect popup, title screen, castle etc. get handled before anything else.
        if reconnect.step(frame, do_click):
            post_battle.clear()
            last_activity = time.time()
            last_button = time.time()
            wait(0.3)
            continue
        # A gear menu left open would hide everything else, and its stars/items could be misread.
        if menu_open(frame):
            print("[gear] menu open, closing")
            do_click(to_px(frame, CLOSE_BTN))
            last_button = time.time()
            wait(CLICK_COOLDOWN)
            continue

        now = time.time()
        hud = hud_visible(frame)
        if hud:
            last_activity = now
        elif now - last_activity >= IDLE_CLICK_AFTER:
            pos = to_px(frame, IDLE_CLICK_POS)
            print(f"[idle] nothing happened for {IDLE_CLICK_AFTER:.0f}s, click corner {pos}")
            do_click(pos, idle=True)
            continue

        if hud:
            hud_since = hud_since or now
            if post_battle.is_set():
                post_battle.clear()
                print("[battle] HUD back, post-battle Space off")
        else:
            if hud_since and now - hud_since >= HUD_MIN:
                print("[battle] HUD gone, battle over: spamming Space")
                stats.bump("battles")  # stats
                left_battle()
                post_battle_until = now + POST_BATTLE_SPAM
                post_battle.set()
            hud_since = None
            if post_battle.is_set():
                # Anything before these (boss chest cutscene etc.) is only skipped, never clicked.
                found = None
                for name, finder in POST_BATTLE_ENDS:
                    hit = finder(frame)
                    if hit:
                        found = f"{name} {hit}"
                        break
                if found:
                    post_battle.clear()
                    print(f"[battle] post-battle Space off, found {found}")
                elif now > post_battle_until:
                    post_battle.clear()
                    print(f"[battle] no CONTINUE/stage after {POST_BATTLE_SPAM:.0f}s, Space off")
                else:
                    wait(POST_BATTLE_SCAN)
                    continue

        if skill_battle:
            if skill_battle.step(frame):
                wait(0.05)
                continue
        elif menu_visible(frame):
            now = time.time()
            menu_since = menu_since or now
            shown = now - menu_since
            if fixing_pointer.is_set():
                if shown < MENU_LOAD_DELAY:
                    wait(SCAN_INTERVAL)
                    continue
                row = highlighted_row(frame)
                if row == "scroll":
                    print("[battle] pointer on SCROLL, space resumed")
                    fixing_pointer.clear()
                    continue
                key = "w" if ROWS.index(row) > ROWS.index("scroll") else "s"
                print(f"[battle] pointer on {row.upper()}, press {key.upper()}")
                do_key(key)
                wait(KEY_SETTLE)
                continue
            if shown >= GUARD_AFTER:
                pos = row_px(frame, "guard")
                print(f"[battle] menu up {shown:.1f}s, click GUARD {pos}")
                do_click(pos)
                guarded = True
                menu_since = None
                wait(CLICK_COOLDOWN)
                continue
            wait(SCAN_INTERVAL)
            continue
        menu_since = None

        btn = find_any_button(frame)
        if btn:
            name, pos = btn
            print(f"[{name}] click {pos}")
            do_click(pos)
            left_battle()
            last_button = time.time()
            if name == "play again":
                play_agains += 1
                stats.bump("runs finished")  # stats
            wait(CLICK_COOLDOWN)
            continue

        now = time.time()
        if now - last_button < SETTLE_DELAY or now - last_card < CARD_REPICK_DELAY:
            wait(SCAN_INTERVAL)
            continue

        if (
            AUTO_SELL
            and play_agains >= SELL_EVERY
            and gear_ready(frame)
            and now - last_sell_try >= SELL_RETRY_DELAY
        ):
            if args.dry_run:
                print("[sell] would sell gear now")
                ok = True
            else:
                selling.set()
                try:
                    ok = run_sell(do_click, grab_screen, wait)
                finally:
                    selling.clear()
            if ok:
                print("[sell] done")
                play_agains = 0
            else:
                last_sell_try = time.time()
            last_button = time.time()
            continue

        choice = pick_stage(frame)
        # autosell: on Choose your path after a boss fight or halfway through a land, Ctrl+4 on.
        if (choice and autosell_on.is_set() and not autosold and not args.dry_run
                and (boss_loot or halfway(frame))):
            autosold = True
            print("[autosell] checking gear: " + ("after boss fight" if boss_loot else "halfway"))
            boss_loot = False
            selling.set()
            try:
                run_autosell(do_click, grab_screen, wait)
            finally:
                selling.clear()
            last_button = time.time()
            continue
        if choice:
            if wait(CONFIRM_DELAY):
                break
            frame = grab_screen()
            if find_any_button(frame) or pick_stage(frame) != choice:
                print("[stage] screen changed, rechecking")
                continue
            i, stars, pos = choice
            print(f"[stage] card {i + 1} (reward {stars}) click {pos}")
            do_click(pos)
            left_battle()
            last_card = time.time()
            autosold = False  # autosell: next Choose your path screen gets checked again
            wait(CLICK_COOLDOWN)
            continue

        wait(SCAN_INTERVAL)

    print("bye")


if __name__ == "__main__":
    main()
