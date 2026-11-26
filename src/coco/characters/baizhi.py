"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Baizhi import Baizhi as NativeBaizhi
from src.coco.characters.base import CocoCharacter


class Baizhi(CocoCharacter, NativeBaizhi):
    FIELD_TIME_OUT = 5.0

    STACK_TIME = 1.4

    def do_perform(self):
        self.wait_down()
        if not self.is_con_full():
            self.attack_while(self.STACK_TIME)
        if self.resonance_available():
            self.click_resonance(send_click=False, time_out=1)
        self.click_liberation()
        self.click_echo(time_out=0)
        if not self.is_con_full() and self.field_time() < self.FIELD_TIME_OUT - self.STACK_TIME:
            self.attack_while(self.STACK_TIME, stop=self.is_con_full)
            if not self.is_con_full():
                self.heavy_attack(0.6)
        self.switch_next_char()
