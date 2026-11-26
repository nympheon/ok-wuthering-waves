"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Youhu import Youhu as NativeYouhu
from src.coco.characters.base import CocoCharacter


class Youhu(CocoCharacter, NativeYouhu):
    FIELD_TIME_OUT = 9.0

    def do_perform(self):
        self.wait_down()
        self.throw()
        self.click_echo(time_out=0)
        if self.resonance_available() and self.click_resonance(send_click=False, time_out=1)[0]:
            self.throw()
        if self.click_liberation():
            self.throw()
        if not self.is_con_full() and self.field_time() < self.FIELD_TIME_OUT - 3:
            # 长按攒满霜色, 松手前滚问祯, 再扔
            self.hold_mouse(1.5, until=self.is_mouse_forte_full, min_time=0.5)
            self.sleep(0.5)
            self.throw()
        if not self.is_con_full() and self.field_time() < self.FIELD_TIME_OUT - 1.5:
            # 4 个吉兆时长按是诗中物结算; 不够 4 个就只是又摇一次
            self.heavy_attack(0.8)
            self.sleep(0.3)
        self.switch_next_char()

    def throw(self):
        self.click()
        self.sleep(0.45)
