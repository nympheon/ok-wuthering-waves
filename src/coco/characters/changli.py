"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Changli import Changli as NativeChangli
from src.coco.characters.base import CocoCharacter


class Changli(CocoCharacter, NativeChangli):
    def liberation_and_heavy(self, con_less_than=-1, send_click=False, wait_if_cd_ready=0, timeout=5):
        if con_less_than > 0:
            if self.get_current_con() > con_less_than:
                return False
        self.logger.debug('click_liberation start')
        start = time.time()
        last_click = 0
        clicked = False
        while time.time() - start < wait_if_cd_ready and not self.liberation_available() and not self.has_cd(
                'liberation'):
            self.logger.debug(f'click_liberation wait ready {wait_if_cd_ready}')
            if send_click:
                self.click(interval=0.1)
            self.task.next_frame()
        while self.liberation_available() and self.task.in_team()[0]:  # clicked and still in team wait for animation
            self.logger.debug('click_liberation liberation_available click')
            now = time.time()
            if now - last_click > 0.1:
                self.send_liberation_key()
                if not clicked:
                    clicked = True
                    self.record_liberation_use()
                last_click = now
            if time.time() - start > timeout:
                # 图标亮着却放不出来(被控/空中): 放弃这次, 别判脱战
                self.logger.error('liberation still available after clicking, give up')
                self._liberation_available = False
                return False
            self.task.next_frame()
        if clicked:
            if self.task.wait_until(lambda: not self.task.in_team()[0], time_out=0.4):
                self.task.in_liberation = True
                self.logger.debug('not in_team successfully casted liberation')
            else:
                self.task.in_liberation = False
                self.logger.error('clicked liberation but no effect')
                return False
        start = time.time()
        hold = False
        while not self.task.in_team()[0]:
            self.task.in_liberation = True
            if not clicked:
                clicked = True
                self.record_liberation_use()
            if send_click:
                self.click(interval=0.1)
            if time.time() - start > 1.5 and not hold:
                self.task.mouse_down()
                hold = True
            if time.time() - start > 7:
                self.task.in_liberation = False
                self.task.raise_not_in_combat('too long a liberation, the boss was killed by the liberation')
            self.task.next_frame()
        duration = time.time() - start
        self.add_freeze_duration(start, duration)
        self.task.in_liberation = False
        if clicked:
            self.logger.info(f'click_liberation end {duration}')
            self.task.wait_until(lambda: self.task.in_team()[0] and self.is_mouse_forte_full(), time_out=0.6)
            self.task.wait_until(lambda: self.task.in_team()[0] and not self.is_mouse_forte_full(), time_out=0.6)
        self.task.mouse_up()
        self.check_combat()
        return clicked
