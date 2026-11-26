"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Jiyan import Jiyan as NativeJiyan
from src.coco.characters.base import CocoCharacter


class Jiyan(CocoCharacter, NativeJiyan):
    LIB_DURATION = 10.0

    FIELD_TIME_OUT = 5.0

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.3)
        else:
            self.wait_down()
        self.click_echo(time_out=0)
        if self.click_liberation():
            self.liberation_combo(time.time())
            return self.switch_next_char()
        # 一套 5 段普攻把破阵值攒到 30 以上再放 E
        self.attack_while(2.0, stop=self.is_con_full)
        if self.resonance_available():
            self.click_resonance(send_click=False, time_out=1, post_sleep=0.6)
        if not self.is_con_full():
            self.attack_while(max(0.3, self.FIELD_TIME_OUT - self.field_time()), stop=self.is_con_full)
        self.switch_next_char()

    def liberation_combo(self, start):
        while self.time_elapsed_accounting_for_freeze(start) < self.LIB_DURATION:
            if self.resonance_available():
                if self.click_resonance(send_click=True, time_out=0.6)[0]:
                    continue
            self.attack_while(1.0)
            # 龙转一段后闪避取消后摇
            self.task.click(key='right')
            self.sleep(0.05)
