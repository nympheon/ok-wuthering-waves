"""Enter a 4C challenge by rechecking the visible button after each attempt."""

import re
import time

from src.task.BaseWWTask import TEAM_SCREEN_FEATURES

MAP_ENTRY_FEATURES = ('fast_travel_custom', 'gray_teleport', 'remove_custom')
SOLO_CHALLENGE = re.compile(r'^\s*(?:单人挑战|單人挑戰|Solo\s*Challenge|Solo)\s*$', re.I)
START_CHALLENGE = re.compile(r'^\s*(?:开启挑战|開啟挑戰|开始挑战|開始挑戰|Start\s*Challenge|Start)\s*$', re.I)


def _challenge_button(task):
    texts = task.ocr(0.6, 0.86, 0.98, 0.97, name='challenge_buttons') or []
    for text in texts:
        if SOLO_CHALLENGE.fullmatch(text.name):
            return 'level', text
        if START_CHALLENGE.fullmatch(text.name):
            return 'team', text
    if button := task.find_one('team_start_challenge'):
        return 'challenge', button
    return None


def wait_after_book_click(task):
    def find_destination():
        if task.find_one(MAP_ENTRY_FEATURES):
            return 'map'
        if task.find_one(TEAM_SCREEN_FEATURES) or _challenge_button(task):
            return 'challenge'
        return None

    destination = task.wait_until(find_destination, time_out=10, settle_time=0.5, raise_if_not_found=False)
    if not destination:
        raise RuntimeError(task.tr('The boss was selected but no map or challenge screen opened.'))
    return destination == 'challenge'


def enter_challenge(task, level_selected=False, time_out=120, retry_interval=4):
    deadline = time.monotonic() + time_out
    last_page = None
    last_click = float('-inf')
    while time.monotonic() < deadline:
        task.next_frame()
        if task.in_team_and_world():
            return
        if task.click_skip_dialog_confirm():
            continue
        if found := _challenge_button(task):
            page, button = found
            if not level_selected and page in ('level', 'challenge'):
                level_selected = True
                if page == 'level':
                    task.click_configured_boss_level()
                else:
                    task.click_configured_boss_level(raise_if_not_found=False)
                continue
            now = time.monotonic()
            if now - last_click >= (retry_interval if page == last_page else 1):
                if page == last_page:
                    task.log_info(task.tr('challenge: {button} did not respond, click again').format(button=button.name))
                task.click_box(button, after_sleep=0.5)
                last_page, last_click = page, now
                continue
        task.sleep(0.5)
    raise RuntimeError(task.tr('challenge: not in world after {seconds}s').format(seconds=time_out))
