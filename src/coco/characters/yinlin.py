"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Yinlin import Yinlin as NativeYinlin
from src.coco.characters.base import CocoCharacter


class Yinlin(CocoCharacter, NativeYinlin):
    FIELD_TIME_OUT = 8.0

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.3)
        else:
            self.wait_down()
        self.click_echo(time_out=0)
        e1 = self.resonance_available() and self.click_resonance(send_click=False, time_out=1)[0]
        self.click_liberation()
        for _ in range(2):
            if self.is_mouse_forte_full():
                break
            self.heavy_attack(0.5)
            self.sleep(0.2)
        if e1:
            # E1 后的 E2(不放也会自己进冷却)
            self.click_resonance(send_click=False, time_out=0.8)
        self.judgement()
        if not self.is_con_full():
            self.attack_while(max(0.4, self.FIELD_TIME_OUT - self.field_time()), stop=self.is_con_full)
        self.switch_next_char()

    def judgement(self):
        """审判值满了放千面魅影; 差一点就再补两下重击。"""
        for _ in range(4):
            if self.is_mouse_forte_full():
                self.heavy_click_forte(self.is_mouse_forte_full)
                self.sleep(0.3)
                return True
            if self.field_time() > self.FIELD_TIME_OUT:
                return False
            self.heavy_attack(0.5)
            self.sleep(0.2)
        return False
