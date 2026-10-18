# Changes made to pixel-lineage-macro for this setup

Base: https://github.com/elClie/pixel-lineage-macro (Windows, game fullscreen at 1920x1080).
The game UI on this PC is drawn bigger than on the author's screen, so most screen positions
were remeasured from real screenshots. All positions below are in 1920x1080 pixels.

## Setup
- The four .bat files were converted to Windows (CRLF) line endings.
- Run skills.bat. Ctrl+2 starts, Ctrl+3 stops, mouse in a screen corner is an emergency stop.
- Python 3.15 worked. The first run builds .venv and installs requirements.txt.

## battle.py (battle menu, HUD, skill list, boss detection)
- Menu rows: ROW_Y0 = 443.5/576, ROW_STEP = 20.9/576, HIGHLIGHT_X = 140-170 (of 1024).
- HUD_AREA = (1182, 760, 1375, 880), HUD_EDGE_BOX = (1396, 760, 1416, 950).
- Skill list: BACK_BTN = (277, 782), SKILL_LIST_BORDER_BOX = (360, 430, 380, 710),
  BACK_EDGE_BOX = (225, 792, 330, 808).
- New MENU_EDGE_BOX = (340, 800, 380, 950): menu_visible() also needs the menu panel's right
  edge, so the wide BATTLE LOG is never mistaken for the menu.
- BORDER_BOX and BODY_BOX now cover y 780-950. Every battle check stops at y 950 because boss
  fights put black bars over the bottom of the screen (otherwise the bot thinks the battle ended
  and spams Space).
- New boss_bar_visible(): gold frame of the boss health bar, box (600, 44, 1400, 58), at least 2
  rows that are 90% gold.
- New letterbox_visible(): black bar at the bottom, box (100, 970, 1800, 1070), 90% of pixels
  with brightness under 12. Every boss fight starts with these bars.

## buttons.py
- CONTINUE_AREA = (0.3, 0.25, 0.7, 0.93), CONTINUE_WIDTH = (0.10, 0.18) (boss chest CONTINUE is wider).
- BATTLE_AREA = (0.64, 0.1, 0.90, 0.95), BATTLE_WIDTH = (0.10, 0.16).
- New find_choice(): on "Make your choice" events (camp, altar) TO BATTLE is grayed out. When the
  grayed TO BATTLE (1380, 715, 1615, 752) and a bright option edge (630, 600, 637, 670) are both
  showing, click the bottom option at (1130, 635). So: WALK AWAY at altars, SHARPEN UP at camps.

## bot.py
- Imports find_choice and adds ("choice", find_choice) to the end of the BUTTONS list.

## stage_select.py
- STAR_AREA = (0.818, 0.33, 0.905, 0.90), so the gold "REWARD" label is not counted as stars.

## skills.py (skill order)
- Every turn the bot tries a chain of skills, one try each, then ATTACKs if none went through
  (cooldown or not enough EN). Later skills are reached with keys from the previous skill,
  which stays highlighted in the open list when it fails.
- The skill list opens on its top skill; W wraps to the bottom:
  W x1 = ECLIPSE, W x2 = CHAINS OF OBLIVION, W x3 = END OF DAYS.
- Normal fights: END OF DAYS (www), CHAINS OF OBLIVION (s), ECLIPSE (s), then ATTACK.
- Boss fights: ECLIPSE (w), END OF DAYS (ww), CHAINS OF OBLIVION (s), then ATTACK.
- A battle counts as a boss fight once boss_bar_visible() or letterbox_visible() is seen while
  the battle menu is up. It stays a boss fight until the next battle.
- Never use Mage's Sense or Hex Bind (they deal no damage).

## minigame.py (sigils and dodges)
- SIGIL_TARGET = 22.5 (px from rune center to the frame when it presses; lower = later).
  Tuned by feel in small steps.
- SIGIL_LEAD = 0.05 s (presses landed about 50 ms after plan), BAR_LEAD = 0.05 s.
- Sigil gate: only trust a sigil when the purple "ARCANE SIGILS" title shows. Box (830, 100,
  960, 210): some row must be at least 30% rune-purple AND at least 30% of the box must be dark
  (brightness under 40). This stops purple bosses and purple skies from faking a sigil, which
  had made the bot spam Space and freeze. The panel sits lower in boss fights, which is why the
  box is tall.
- Dodge bar (INCOMING!): BAR_AREAS = ((560, 322, 1360, 372), (560, 265, 1360, 315)), checked in
  that order: boss fight height first, then normal fight height.

## Planned, not built
- Auto-sell toggle (hotkey such as Ctrl+4) that reads gear stats between battles and keeps items
  with at least 2 of: 150+ magic, shadow damage, 15%+ crit chance, magic %, or a legendary trait
  that deals damage or elemental damage. Needs OCR, plus screenshots of the inventory and of an
  item stat panel first.
