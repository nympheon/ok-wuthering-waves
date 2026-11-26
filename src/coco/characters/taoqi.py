"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Taoqi import Taoqi as NativeTaoqi
from src.coco.characters.base import CocoCharacter


class Taoqi(CocoCharacter, NativeTaoqi):
    FIELD_TIME_OUT = 4.0

    def do_perform(self):
        if self.has_intro:
            self.wait_down()
            # 变奏给满能量, 直接打三段强化普攻上盾
            self.attack_while(1.5)
        else:
            self.wait_down()
        if self.resonance_available():
            self.click_resonance(send_click=False, time_out=1)
        self.click_liberation()
        self.click_echo(time_out=0, sleep_time=0.1)
        if not self.is_con_full():
            self.attack_while(max(0.3, self.FIELD_TIME_OUT - self.field_time()), stop=self.is_con_full)
        self.switch_next_char()
