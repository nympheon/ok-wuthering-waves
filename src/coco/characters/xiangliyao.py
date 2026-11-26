"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Xiangliyao import Xiangliyao as NativeXiangliyao
from src.coco.characters.base import CocoCharacter


class Xiangliyao(CocoCharacter, NativeXiangliyao):
    LIB_DURATION = 24.0

    LIB_FIELD_TIME_OUT = 15.0

    FIELD_TIME_OUT = 4.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.liberation_time = -1
        self.e4_count = 0

    def reset_state(self):
        super().reset_state()
        self.liberation_time = -1
        self.e4_count = 0

    def do_perform(self):
        self.wait_down()
        if self.click_liberation():
            self.liberation_time = time.time()
            self.e4_count = 0
        if self.still_in_liberation() and self.e4_count < 3:
            self.liberation_combo()
        else:
            self.click_echo(time_out=0)
            if self.resonance_available():
                self.click_resonance(send_click=False, time_out=1)
            if not self.is_con_full():
                self.attack_while(max(0.3, self.FIELD_TIME_OUT - self.field_time()), stop=self.is_con_full)
        self.switch_next_char()

    def still_in_liberation(self):
        return self.time_elapsed_accounting_for_freeze(self.liberation_time) < self.LIB_DURATION

    def liberation_combo(self):
        casts = 0
        while (self.still_in_liberation() and self.e4_count < 3 and casts < 8
               and self.field_time() < self.LIB_FIELD_TIME_OUT):
            if self.resonance_available():
                e4 = self.is_forte_full()
                if self.click_resonance(send_click=False, time_out=1)[0]:
                    casts += 1
                    if e4:
                        self.e4_count += 1
                        # 等魔方炸完
                        self.sleep(0.9)
                    else:
                        # E3 飞起来, 接空中攻击
                        self.attack_while(0.5)
                    continue
            self.attack_while(1.0)
        if self.e4_count >= 3 or casts >= 8:
            self.liberation_time = -1
