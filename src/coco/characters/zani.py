"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Zani import State, Zani as NativeZani
from src.coco.characters.base import CocoCharacter


class Zani(CocoCharacter, NativeZani):
    def click_liber2(self):
        start = time.time()
        self.task.in_liberation = True
        send_key = True
        not_liber_box = self.task.box_of_screen_scaled(2560, 1440, 1909, 1274, 1957, 1322, name='zani_not_liber_box', hcenter=True)
        overall = time.time()
        while not self.task.find_one('target_enemy_long_inner', box=not_liber_box, threshold=0.75):
            if time.time() - start > 6 or time.time() - overall > 9:
                self.task.in_liberation = False
                if not self.check_liber():
                    self.update_blazes()
                return
            if self.current_resonance() == 0:
                start = time.time()
            elif time.time() - start > 1.5:
                send_key = False
            if send_key:
                self.send_liberation_key()
            self.task.next_frame()
        self.task.in_liberation = False
        current = time.time()
        duration = 2.25
        if current - start >= duration:
            self.last_liber2 = current
            self.add_freeze_duration(current - duration, duration, 0)
            self.logger.info('clicked liber2')
        self.in_liberation = False
        self.blazes = -1
        self.liberation_time = -1
        self.state = 0

    def basic_attack_breakthrough(self):
        wait_chair = 1.2
        if self.chair_time == -1:
            result = self.standard_defense_protocol_combo()
            if result == State.FAILED:
                sleep = 0.3 - (time.time() - self.dodge_time)
                if (result := self.wait_forte_full(sleep)) != State.DONE:
                    return result
                self.task.mouse_down()
                try:
                    result = self.wait_forte_full(0.6)
                finally:
                    self.task.mouse_up()
                if result != State.DONE:
                    return result
                wait_chair = 1.15
                if (result := self.wait_forte_full(0.85, send_click=True)) != State.DONE:
                    return result
            elif result == State.FORTE_FULL:
                return State.FORTE_FULL
        else:
            wait_chair -= (time.time() - self.chair_time)
            self.chair_time = -1
        if (result := self.wait_forte_full(wait_chair)) != State.DONE:
            return result
        self.continues_normal_attack(0.2)
        return result
