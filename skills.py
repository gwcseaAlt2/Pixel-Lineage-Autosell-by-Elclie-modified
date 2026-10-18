import time

from hotkeys import scroll_first  # scroll first

from battle import BACK_BTN, ROWS, boss_bar_visible, highlighted_row, letterbox_visible, menu_visible, row_px, skill_list_open, to_px

# Every turn: try these skills in order, then ATTACK if none went through (cooldown / no EN).
# Each entry is (skill, keys to reach it). The list opens on its top skill and W wraps around
# to the bottom (ECLIPSE), so W x1 = ECLIPSE, W x2 = CHAINS OF OBLIVION, W x3 = END OF DAYS.
# Later keys move from the previous skill, which stays highlighted when it doesn't go through.
SKILL_CHAIN = (("END OF DAYS", "www"), ("CHAINS OF OBLIVION", "s"), ("ECLIPSE", "s"))
# Boss fights (gold health bar at the top, or black bars at the start): ECLIPSE first, then
# END OF DAYS, then CHAINS.
BOSS_SKILL_CHAIN = (("ECLIPSE", "w"), ("END OF DAYS", "ww"), ("CHAINS OF OBLIVION", "s"))

KEY_GAP = 0.05
# The two Spaces after picking: one confirms the skill/attack, one confirms the target.
# With a single enemy the second one is simply ignored.
DOUBLE_TAP_GAP = 0.03
NAV_SETTLE = 0.15
# Battle menu must be up this long before acting, so the turn has really started.
MENU_SETTLE = 0.2
LIST_TIMEOUT = 0.5
# No minigame and the menu still up after this long means the action didn't go through.
CAST_TIMEOUT = 2.0
MAX_CAST_TRIES = 3
# The solver saw a minigame this recently: it's handling input, so don't press anything.
MINIGAME_QUIET = 0.5


class SkillBattle:
    """Battle turns for skill mode: each turn try SKILL_CHAIN in order, then ATTACK if none worked."""

    def __init__(self, press, click, grab, wait, minigame_seen):
        self.press = press
        self.click = click
        self.grab = grab
        self.wait = wait
        self.minigame_seen = minigame_seen
        self.new_battle()

    def new_battle(self):
        self.menu_since = None
        # Set after acting; cleared once the menu goes away, so each turn is played once.
        self.acted = False
        # Set when no skill in SKILL_CHAIN went through this turn, so this turn is an ATTACK.
        self.no_skill = False
        # Set once the boss health bar is seen; stays on until the next battle.
        self.boss = False
        # scroll first: set once the SCROLL was tried this battle (one try per battle).
        self.scroll_done = False

    def step(self, frame):
        """Play the turn if the battle menu is up. Returns True if this was a battle frame."""
        if not menu_visible(frame):
            self.menu_since = None
            self.acted = False
            self.no_skill = False
            return False
        if not self.boss and (boss_bar_visible(frame) or letterbox_visible(frame)):
            print("[skills] boss fight: ECLIPSE > END OF DAYS > CHAINS")
            self.boss = True
        now = time.perf_counter()
        if self.acted or now - self.minigame_seen() < MINIGAME_QUIET:
            return True
        self.menu_since = self.menu_since or now
        if now - self.menu_since < MENU_SETTLE:
            return True

        if skill_list_open(frame):
            print("[skills] skill list left open, BACK")
            self.click(to_px(frame, BACK_BTN))
            self.wait(NAV_SETTLE)
            return True

        # scroll first: the first move of each battle is the SCROLL, while Ctrl+1 has it on.
        if scroll_first.is_set() and not self.scroll_done:
            want = "scroll"
        else:
            want = "attack" if self.no_skill else "skills"
        row = highlighted_row(frame)
        if row != want:
            key = "w" if ROWS.index(row) > ROWS.index(want) else "s"
            print(f"[skills] pointer on {row.upper()}, want {want.upper()}: {key.upper()}")
            self.press(key)
            self.wait(NAV_SETTLE)
            return True

        if want == "scroll":  # scroll first
            self.scroll_done = True
            print("[skills] SCROLL, SPACE x2")
            self.double_space()
            done = self.went_through()
            if done:
                print("[skills] SCROLL used")
                self.acted = True
            elif done is False:
                print("[skills] SCROLL didn't go through, using skills")
            return True
        if want == "skills":
            done = self.cast_chain()
            if done:
                self.acted = True
            elif done is False:
                print("[skills] no skill went through, ATTACK this turn")
                self.no_skill = True
                self.click(to_px(self.grab(), BACK_BTN))
                self.wait(NAV_SETTLE)
        elif self.attack():
            self.acted = True
        return True

    def double_space(self):
        self.press("space")
        self.wait(DOUBLE_TAP_GAP)
        self.press("space")

    # These return None when Ctrl+3 stops the bot mid-action, so a stop isn't mistaken for a failure.

    def wait_for(self, check, timeout):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if check(self.grab()):
                return True
            if self.wait(0.03):
                return None
        return False

    def went_through(self):
        """After an action: True once a minigame shows or the battle menu goes away."""
        start = time.perf_counter()
        gone = 0
        while time.perf_counter() - start < CAST_TIMEOUT:
            if self.wait(0.05):
                return None
            if self.minigame_seen() > start:
                return True
            gone = 0 if menu_visible(self.grab()) else gone + 1
            if gone >= 2:
                return True
        return False

    def cast_chain(self):
        """Try each skill in the chain once. True if one went through, False if none did."""
        chain = BOSS_SKILL_CHAIN if self.boss else SKILL_CHAIN
        name, keys = chain[0]
        print(f"[skills] SPACE, {keys.upper()}, SPACE x2 ({name})")
        self.press("space")
        opened = self.wait_for(skill_list_open, LIST_TIMEOUT)
        if not opened:
            return opened
        for i, (name, keys) in enumerate(chain):
            if i > 0:
                # A skill that didn't go through leaves the list open with the pointer on it.
                if not skill_list_open(self.grab()):
                    return False
                print(f"[skills] didn't go through, {keys.upper()}, SPACE x2 ({name})")
            for key in keys:
                self.press(key)
                self.wait(KEY_GAP)
            self.double_space()
            done = self.went_through()
            if done is not False:
                if done:
                    print(f"[skills] {name} cast")
                return done
        return False

    def attack(self):
        print("[attack] SPACE x2")
        self.double_space()
        done = self.went_through()
        if done is False:
            print("[attack] didn't go through, retrying next scan")
        return done
