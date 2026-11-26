"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Luhesi import Luhesi as NativeLuhesi
from src.coco.characters.base import CocoCharacter


class Luhesi(CocoCharacter, NativeLuhesi):
    def perform_everything(self):
        self.continues_normal_attack(1.1)
        if not self.burst_intro():
            self.send_resonance_key(post_sleep=0.1)
            return
        else:
            self.last_intro = time.time()
        if not self.flying():
            self.task.wait_until(self.flying, post_action=self.task.jump, time_out=0.2)
        self.logger.debug(f"detect {self.available('echo', check_color=True)}")
        detect_ready = self.echo_available()
        start = time.time()
        res_count = 0
        try_jump = False
        while self.time_elapsed_accounting_for_freeze(start) < 12:
            if self.detect_elbow_strike(detect_ready):
                self.logger.debug("Detected an elbow strike, attempting to reset.")
                self.task.wait_until(lambda: not self.detect_elbow_strike(detect_ready),
                                     post_action=lambda: self.continues_right_click(0.05), time_out=1.5)
            elif self.handle_heavy(res_count) and res_count > 2:
                self.lib()
                return
            elif try_jump and not self.check_res():
                self.task.wait_until(lambda: self.task.find_one('luhesi_kick', threshold=0.7) or\
                                             self.detect_elbow_strike(detect_ready),
                                             post_action=self.send_resonance_key, time_out=1)
                if self.detect_elbow_strike(detect_ready):
                    continue
                try_jump = False
                if self.task.find_one('luhesi_kick', threshold=0.7):
                    res_count+=1
                else:
                    if res_count == 2:
                        self.wait_down()
                    self.lib()
                    return
            elif self.check_res():
                self.task.jump()
                try_jump = True
            else:
                self.click()
            self.sleep(0.01)
