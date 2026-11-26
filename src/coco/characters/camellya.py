"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Camellya import Camellya as NativeCamellya
from src.coco.characters.base import CocoCharacter


class Camellya(CocoCharacter, NativeCamellya):
    def wait_resonance_not_gray(self, timeout=5):
        start = time.time()
        while self.current_resonance() == 0:
            self.click()
            self.sleep(0.1)
            if time.time() - start > timeout:
                self.logger.error('wait wait_resonance_not_gray timed out')
                return False
        return True

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(1.2)
            self.sleep(0.1)
            self.heavy_attack(4.6, until_con_full=True)
        if self.liberation_available():
            self.click_liberation(con_less_than=0.82)
        start_con = self.get_current_con()
        if start_con < 0.82:
            loop_time = 1.1
            if self.resonance_available():
                self.click_resonance(time_out=1)
        else:
            loop_time = 4.6
        budding_start_time = time.time()
        budding = False
        heavy_att = False
        freeze_forte_check = False
        freeze_forte_time = 0
        self.last_forte = 0
        loop_start = time.time()
        while (time.time() - budding_start_time < loop_time or self.task.find_one('camellya_budding', threshold=0.7))                 and time.time() - loop_start < 14:
            if not budding:
                if self.ephemeral_ready() and self.is_con_full():
                    self.ephemeral_cast()
                    budding = True
                else:
                    self.click(interval=0.1)
                    current_con = self.get_current_con()
                    if current_con < 0.82:
                        if not self.is_con_full():
                            self.click_echo()
                            return self.switch_next_char()
                        elif loop_time < 3.1:
                            loop_time += 1
                if budding:
                    self.logger.info(f'start budding')
                    self.check_target()
                    budding_start_time = time.time()
                    loop_time = 5.1
            if budding:
                if not heavy_att:
                    heavy_att = True
                    self.task.mouse_down()
                if time.time() - budding_start_time < 1.5 and self.liberation_available():
                    if self.click_liberation() and heavy_att:
                        self.logger.info(f'liberation retry heavy att')
                        self.task.mouse_up()
                        self.sleep(0.2, False)
                        self.task.mouse_down()
            self.check_target(heavy_att)
            self.task.next_frame()
            if freeze_forte_check and time.time() - freeze_forte_time >= 0.2:
                freeze_forte_check = False
            if not freeze_forte_check and heavy_att:
                if self.should_retry_heavy_attack(budding) < 0:
                    freeze_forte_check = True
                    freeze_forte_time = time.time()
        self.waiting_for_forte_drop = False
        if heavy_att:
            self.task.mouse_up()
            self.sleep(0.1)
        if budding:
            self.click_resonance(time_out=1)
            self.sleep(0.1)
        self.click_echo()
        self.switch_next_char()

    def ephemeral_cast(self):
        self.check_combat()
        start = time.time()
        while self.ephemeral_ready() and time.time() - start < 2:
            self.send_resonance_key()
            self.sleep(0.1)
        self.sleep(1.1)
