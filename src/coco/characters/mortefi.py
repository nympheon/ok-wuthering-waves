"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Mortefi import Mortefi as NativeMortefi
from src.coco.characters.base import CocoCharacter


class Mortefi(CocoCharacter, NativeMortefi):
    FIELD_TIME_OUT = 5.0

    def do_perform(self):
        if self.has_intro:
            self.wait_down()
        else:
            # 等切人自动打的第 4 段打完
            self.attack_while(0.5)
        self.click_echo(time_out=0)
        self.e_twice()
        self.click_liberation(wait_if_cd_ready=0.5)
        if not self.is_con_full():
            self.attack_while(1.4, stop=self.is_con_full)
            if self.resonance_available():
                self.click_resonance(send_click=False, time_out=0.8)
        if not self.is_con_full():
            self.attack_while(max(0.3, self.FIELD_TIME_OUT - self.field_time()), stop=self.is_con_full)
        self.switch_next_char()

    def e_twice(self):
        if not self.resonance_available():
            return
        self.click_resonance(send_click=False, time_out=1)
        self.sleep(0.1)
        # 怒气满了 E 图标马上又亮(强化 E)
        if self.resonance_available():
            self.click_resonance(send_click=False, time_out=0.8)
