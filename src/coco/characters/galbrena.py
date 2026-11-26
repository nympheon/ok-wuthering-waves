"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Galbrena import Galbrena as NativeGalbrena
from src.coco.characters.base import CocoCharacter


class Galbrena(CocoCharacter, NativeGalbrena):
    ENHANCED_DODGE_INTERVAL = 2.6

    def do_perform(self):
        if self.has_intro:
            self.logger.debug('has_intro wait and heavy attack for 86F and dodge')
            self.task.mouse_down()
            self.sleep(1)
            if self.need_fast_perform():
                self.task.mouse_up()
                return self.switch_next_char()
            self.sleep(0.44)
            self.task.mouse_up()
            self.continues_right_click(0.6)
        elif self.flying():
            self.wait_down()
        self.click_echo(time_out=0)
        if self.is_forte_full() and not self.need_fast_perform():
            self.click_resonance()
            if self.click_liberation():
                self.continues_normal_attack(1)
        if self.check_res() and not self.need_fast_perform():
            self.click_liberation()
            start = time.time()
            last_dodge = start
            while self.check_res() and time.time() - start < 10:
                if self.flying():
                    self.shorekeeper_auto_dodge()
                # 强化态: 强普2345 -> 闪避续内燃烧 -> 强普345; 闪避不重置连段
                if time.time() - last_dodge > self.ENHANCED_DODGE_INTERVAL:
                    self.continues_right_click(0.05)
                    last_dodge = time.time()
                self.click(after_sleep=0.1)
                self.check_combat()
            return self.switch_next_char()
        self.continues_normal_attack(1)
        self.click_resonance()
        return self.switch_next_char()
