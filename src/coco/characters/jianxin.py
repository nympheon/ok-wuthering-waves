"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Jianxin import Jianxin as NativeJianxin
from src.coco.characters.base import CocoCharacter


class Jianxin(CocoCharacter, NativeJianxin):
    FIELD_TIME_OUT = 8.0

    CHANNEL_TIME = 4.5

    def do_perform(self):
        self.wait_down()
        self.click_liberation()
        if self.resonance_available():
            self.click_resonance(send_click=False, time_out=1)
            self.sleep(0.3)
        self.click_echo(time_out=0)
        if self.is_con_full():
            return self.switch_next_char()
        if not self.forte_full():
            self.attack_while(1.5, stop=self.forte_full)
        if self.forte_full():
            # 运气: 按住到协奏满, 最多运到大周天·外
            self.hold_mouse(self.CHANNEL_TIME, until=self.is_con_full, min_time=0.8)
            self.sleep(0.2)
        elif not self.is_con_full():
            self.attack_while(max(0.3, self.FIELD_TIME_OUT - self.field_time() - self.CHANNEL_TIME),
                              stop=self.is_con_full)
        self.switch_next_char()

    def forte_full(self):
        return self.is_forte_full() or self.is_mouse_forte_full()
