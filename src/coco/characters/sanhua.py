"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Sanhua import Sanhua as NativeSanhua
from src.coco.characters.base import CocoCharacter


class Sanhua(CocoCharacter, NativeSanhua):
    CHARGE_TIME = 0.85

    def do_perform(self):
        self.task.mouse_down()
        self.wait_down(click=False)
        start = time.time()
        charge = self.CHARGE_TIME
        e_used = False
        if self.resonance_available():
            self.task.mouse_up()
            e_used = self.click_resonance(send_click=False, time_out=1)[0]
            self.task.mouse_down()
            start = time.time()
        if self.click_liberation(send_click=False):
            # 大招取消 E 的后摇, 挥刀时继续蓄力
            start = time.time()
            charge += 0.1
        remain = charge - self.time_elapsed_accounting_for_freeze(start)
        if remain > 0:
            self.sleep(remain, False)
        self.task.mouse_up()
        self.sleep(0.15)
        if not e_used and self.resonance_available():
            # 爆裂冲刺途中补 E, 冰一起炸
            self.click_resonance(send_click=False, time_out=0.8)
        self.sleep(0.4)
        if self.is_con_full():
            self.click_echo(time_out=0)
        self.switch_next_char()
