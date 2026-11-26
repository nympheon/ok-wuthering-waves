"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Hiyuki import Hiyuki as NativeHiyuki
from src.coco.characters.base import CocoCharacter


class Hiyuki(CocoCharacter, NativeHiyuki):
    PERFORM_HARD_TIMEOUT = 40.0

    def perform_standard(self):
        timeout = self.FIELD_TIME_OUT
        if self.has_intro and self.check_outro() == 'char_linnai':
            timeout = self.LINNAI_FIELD_TIME_OUT

        while self.has_long_action() and self.time_elapsed_accounting_for_freeze(self.last_perform) < timeout:
            self.click_echo(time_out=0)
            self.click_resonance(send_click=False, time_out=0)

            if self.liberation_available():
                if self.click_liberation():
                    self.logger.debug('hiyuki perform lib1')
                    return

            if self.is_mouse_forte_full():
                self.task.click(key="right")
                self.heavy_click_forte(check_fun=self.is_mouse_forte_full)
                # 重击后大招一般马上亮; 等不到别耗满整段在场时间
                self.task.wait_until(self.liberation_available, post_action=self.click_with_interval, time_out=3.0)
                if self.click_liberation():
                    self.logger.debug('hiyuki perform lib1')
                    return
            else:
                self.click(interval=0.1)
            self.sleep(0.05)
