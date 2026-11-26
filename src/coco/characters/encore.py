"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.BaseChar import SwitchPriority
from src.char.Encore import Encore as NativeEncore
from src.coco.characters.base import CocoCharacter


class Encore(CocoCharacter, NativeEncore):
    LIB_DURATION = 10.0

    COMBO_TIME = 2.2

    FIELD_TIME_OUT = 5.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_heavy = 0
        self.liberation_time = -1
        self.last_resonance = 0

    def reset_state(self):
        super().reset_state()
        self.liberation_time = -1

    def still_in_liberation(self):
        return self.time_elapsed_accounting_for_freeze(self.liberation_time) < self.LIB_DURATION

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        # 大招中途被切走(硬超时/被打断)要尽快回来打完
        if self.still_in_liberation():
            return SwitchPriority.MUST
        return super().get_switch_priority(current_char, has_intro, target_low_con)

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.5)
        else:
            self.wait_down()
        if self.still_in_liberation():
            self.liberation_combo()
            return self.switch_next_char()
        self.click_echo(time_out=0)
        if not self.is_open_world_auto_combat() and self.click_liberation(wait_if_cd_ready=0.3):
            self.liberation_time = time.time()
            self.liberation_combo()
            return self.switch_next_char()
        self.normal_combo()
        self.switch_next_char()

    def liberation_combo(self):
        while self.still_in_liberation():
            if self.resonance_available() and time.time() - self.last_resonance > 1.5:
                if self.click_resonance(send_click=False, time_out=1)[0]:
                    self.last_resonance = time.time()
                    continue
            # 一套 4 段普攻, 第 4 段出小羊后闪避直接接下一套
            self.attack_while(min(self.COMBO_TIME, self.LIB_DURATION - self.time_elapsed_accounting_for_freeze(
                self.liberation_time)))
            if self.still_in_liberation():
                self.task.click(key='right')
                self.sleep(0.1)
        self.heavy_forte()

    def normal_combo(self):
        if self.resonance_available():
            if self.click_resonance(send_click=False, time_out=1)[0]:
                self.last_resonance = time.time()
                # 光圈出来之前打几下普攻, 再按 E 接第二段
                self.attack_while(1.0)
                self.send_resonance_key()
                self.sleep(0.4)
        if self.heavy_forte():
            return
        if not self.is_con_full():
            self.attack_while(max(0.5, self.FIELD_TIME_OUT - self.field_time()), stop=self.is_con_full)

    def heavy_forte(self):
        if not self.is_mouse_forte_full():
            return False
        self.heavy_attack(1.2)
        self.last_heavy = time.time()
        self.sleep(0.1)
        return True
