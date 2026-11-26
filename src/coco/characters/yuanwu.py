"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Yuanwu import Yuanwu as NativeYuanwu
from src.coco.characters.base import CocoCharacter


class Yuanwu(CocoCharacter, NativeYuanwu):
    def do_perform(self):
        if self.click_liberation(con_less_than=1):
            self.click_resonance(time_out=1)
            return self.switch_next_char()
        if self.has_intro:
            self.continues_normal_attack(1.2)
            return self.switch_next_char()
        self.click_resonance(time_out=1)
        self.click_echo()
        self.switch_next_char()
