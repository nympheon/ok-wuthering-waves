"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Cartethyia import Cartethyia as NativeCartethyia
from src.coco.characters.base import CocoCharacter


class Cartethyia(CocoCharacter, NativeCartethyia):
    def click_resonance_with_lib_big(self):
        if self.has_cd('resonance'):
            return False
        clicked = False
        self.logger.debug(f'click_resonance start')
        last_click = 0
        resonance_click_time = 0
        loop_start = time.time()
        while True:
            if time.time() - loop_start > 10 or (resonance_click_time != 0 and time.time() - resonance_click_time > 8):
                self.task.in_liberation = False
                self.logger.error(f'click_resonance too long, breaking {time.time() - resonance_click_time}')
                self.task.screenshot('click_resonance too long, breaking')
                break
            self.check_combat()
            now = time.time()
            current_resonance = self.current_resonance()
            if not self.resonance_available():
                self.logger.debug(f'click_resonance not available break')
                break
            self.logger.debug(f'click_resonance resonance_available click {current_resonance}')

            if now - last_click > 0.1:
                if current_resonance > 0 and self.resonance_available():
                    if current_resonance < 0.17 and time.time() - resonance_click_time < 2.5:
                        self.click()
                        continue
                    if resonance_click_time == 0:
                        clicked = True
                        resonance_click_time = now
                    self.send_resonance_key()
                last_click = now
            if self.try_lib_big():
                break
            self.task.next_frame()
        if clicked:
            self.record_resonance_use()
            self.res_time = time.time()
        return clicked
