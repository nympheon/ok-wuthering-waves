"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Cantarella import Cantarella as NativeCantarella
from src.coco.characters.base import CocoCharacter


class Cantarella(CocoCharacter, NativeCantarella):
    def do_perform(self):
        perform_under_outro = False
        if self.has_intro:
            self.continues_normal_attack(1.2)
            if self.has_sub_dps_intro and self.check_outro() in {'char_roccia', 'char_sanhua'}:
                perform_under_outro = True
        self.click_liberation()
        if self.is_mouse_forte_full() or not self.is_forte_full():
            self.click_resonance()
            if perform_under_outro and self.flying():
                self.wait_down()
            if not self.flying() and self.is_mouse_forte_full():
                if self.heavy_click_forte(check_fun=self.is_mouse_forte_full):
                    self.last_heavy = time.time()
            elif self.click_echo():
                return self.switch_next_char()
            else:
                self.continues_normal_attack(0.1)
                return self.switch_next_char()
        forte_delay = time.time()
        count = -0.1
        while self.time_elapsed_accounting_for_freeze(self.last_heavy) < 8 and not self.is_mouse_forte_full():
            now = time.time()
            if self.resonance_available() and self.click_resonance(send_click=False, time_out=1)[0]:
                if not perform_under_outro:
                    self.task.mouse_up()
                    return self.switch_next_char()
            if not perform_under_outro and self.need_fast_perform() and self.time_elapsed_accounting_for_freeze(self.last_perform) > 1.1:
                break
            if now - forte_delay > count:
                self.task.mouse_up()
                self.sleep(0.2)
                self.task.mouse_down()
                count += 1
            if self.is_forte_full():
                forte_delay = now
            elif now - forte_delay > 0.5:
                break
            self.check_combat()
            self.task.next_frame()
        self.task.mouse_up()
        self.click_echo()
        self.switch_next_char()
