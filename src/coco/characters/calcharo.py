"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Calcharo import Calcharo as NativeCalcharo
from src.coco.characters.base import CocoCharacter


class Calcharo(CocoCharacter, NativeCalcharo):
    LIB_DURATION = 11.0

    LIB_FIELD_TIME_OUT = 12.0

    FIELD_TIME_OUT = 5.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.liberation_time = -1

    def reset_state(self):
        super().reset_state()
        self.liberation_time = -1

    def still_in_liberation(self):
        return self.time_elapsed_accounting_for_freeze(self.liberation_time) < self.LIB_DURATION

    def do_perform(self):
        if self.has_intro:
            self.logger.debug('Calcharo wait intro animation')
            self.sleep(1)
            self.task.wait_in_team_and_world(time_out=3, raise_if_not_found=False)
            self.check_combat()
        else:
            self.wait_down()
        self.click_echo(time_out=0)
        if not self.still_in_liberation() and self.click_liberation(send_click=True):
            self.liberation_time = time.time()
        if self.still_in_liberation():
            self.liberation_combo()
        else:
            self.normal_combo()
        self.switch_next_char()

    def liberation_combo(self):
        while self.still_in_liberation() and self.field_time() < self.LIB_FIELD_TIME_OUT:
            if self.is_mouse_forte_full():
                self.heavy_click_forte(self.is_mouse_forte_full)
                self.sleep(0.3)
                continue
            self.attack_while(1.0, stop=self.is_mouse_forte_full)

    def normal_combo(self):
        for _ in range(3):
            if not self.resonance_available():
                break
            self.click_resonance(send_click=False, time_out=1)
            self.attack_while(0.3)
        if self.is_mouse_forte_full():
            self.heavy_click_forte(self.is_mouse_forte_full)
        if not self.is_con_full():
            self.attack_while(max(0.3, self.FIELD_TIME_OUT - self.field_time()), stop=self.is_con_full)
