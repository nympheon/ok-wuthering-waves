"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.ShoreKeeper import ShoreKeeper as NativeShoreKeeper
from src.coco.characters.base import CocoCharacter


class ShoreKeeper(CocoCharacter, NativeShoreKeeper):
    FIELD_TIME_OUT = 6.0

    def do_perform(self):
        if self.has_intro:
            self.task.skip_combat_check = True
            try:
                self.logger.debug('ShoreKeeper wait intro animation')
                time.sleep(0.1)
                if not self.task.in_team_and_world():
                    self.task.wait_in_team_and_world(time_out=4, raise_if_not_found=False)
                else:
                    self.continues_normal_attack(1.2)
            finally:
                self.task.skip_combat_check = False
        self.click_echo(time_out=0)
        self.click_liberation()
        if self.resonance_available():
            self.click_resonance(time_out=1)
        # 一套 4 段普攻正好攒满 5 格, 满了重击把坍缩核变成蝴蝶; 协奏没满就再来一轮
        for _ in range(2):
            if self.is_con_full() or self.field_time() > self.FIELD_TIME_OUT:
                break
            if not self.is_mouse_forte_full():
                self.attack_while(1.6, stop=lambda: self.is_mouse_forte_full() or self.is_con_full())
            if self.is_mouse_forte_full():
                self.heavy_click_forte(self.is_mouse_forte_full)
        self.switch_next_char()
