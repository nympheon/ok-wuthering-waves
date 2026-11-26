"""Shared helpers for the optional coco character classes."""

import time

from src.char.BaseChar import SwitchPriority
from src.coco.combat_timing import stop_rotation_timeout


class CocoCharacter:
    PERFORM_HARD_TIMEOUT = 30.0

    def field_time(self):
        return self.time_elapsed_accounting_for_freeze(self.last_perform)

    def burst_intro(self):
        return self.has_sub_dps_intro or (self.has_intro and not any(
            char and char is not self and char.is_sub_dps for char in self.task.chars))

    def _hold(self, down, up, seconds, until, min_time):
        self.check_combat()
        start = time.monotonic()
        down()
        try:
            while time.monotonic() - start < seconds:
                if until is not None and time.monotonic() - start >= min_time and until():
                    return True
                self.task.next_frame()
        finally:
            up()
        return False

    def hold_mouse(self, seconds, until=None, min_time=0.0):
        return self._hold(self.task.mouse_down, self.task.mouse_up, seconds, until, min_time)

    def hold_key(self, key, seconds, until=None, min_time=0.0):
        return self._hold(lambda: self.task.send_key_down(key), lambda: self.task.send_key_up(key),
                          seconds, until, min_time)

    def tap_until(self, send, done, time_out, interval=0.12):
        start = time.monotonic()
        last_send = start - interval
        while time.monotonic() - start < time_out:
            if done():
                return True
            now = time.monotonic()
            if now - last_send >= interval:
                send()
                last_send = now
            self.task.next_frame()
        return bool(done())

    def attack_while(self, seconds, stop=None, interval=0.1):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if stop is not None and stop():
                return True
            self.click(interval=interval)
            self.task.next_frame()
        return False

    def click_resonance(self, post_sleep=0, has_animation=False, send_click=True,
                        animation_min_duration=0, check_cd=False, time_out=0, click_f=True):
        flags = {} if click_f else {'click_f': False}
        return super().click_resonance(post_sleep=post_sleep, has_animation=has_animation,
                                       send_click=send_click, animation_min_duration=animation_min_duration,
                                       check_cd=check_cd, time_out=time_out or 3, **flags)

    def switch_next_char(self, *args, **kwargs):
        stop_rotation_timeout(self)
        return super().switch_next_char(*args, **kwargs)


def switch_priority(char, priority, current_char):
    if not isinstance(char, CocoCharacter):
        return priority
    last_turn = max(char.last_switch_time, char.task.combat_start)
    off_field = char.time_elapsed_accounting_for_freeze(last_turn)
    if off_field >= 70 or (off_field >= 25 and char.is_main_dps and not current_char.is_main_dps):
        return max(priority, SwitchPriority.MUST + 1)
    if off_field >= 40:
        return max(priority, SwitchPriority.NORMAL)
    return priority
