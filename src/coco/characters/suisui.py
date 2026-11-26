"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.BaseChar import SwitchPriority
from src.char.Suisui import Suisui as NativeSuisui
from src.coco.characters.base import CocoCharacter


class Suisui(CocoCharacter, NativeSuisui):
    FORTE_TIMEOUT = 14.0

    CONCERTO_TIMEOUT = 10.0

    def perform_forte3_rotation(self):
        start = time.time()
        if self.should_heavy:
            if self.has_intro:
                self.heavy_attack(1.5)
            self.click_resonance(time_out=1)
            self.should_heavy = False
        while self.time_elapsed_accounting_for_freeze(start) < self.FORTE_TIMEOUT:
            if self.forte3_available():
                self.logger.debug('forte3 available')
                break
            elif self.forte2_available() or self.forte3_available():
                self.logger.debug('forte2 available')
                for i in range(7):
                    if self.forte3_available():
                        break
                    self.click(after_sleep=0.1)
                break
            self.cycle_start()
            if not self.has_intro:
                if self.try_e():
                    return self.switch_next_char()
            self.click()
            self.cycle_sleep(self.ATTACK_INTERVAL)
        else:
            self.logger.warning('Suisui forte3 detection timed out')
            return

        liberation_clicked = False
        start = time.time()
        while self.time_elapsed_accounting_for_freeze(start) < self.CONCERTO_TIMEOUT:
            if not liberation_clicked:
                liberation_clicked = self.click_liberation(wait_if_cd_ready=0)
                if liberation_clicked:
                    self.task.next_frame()
                    continue
            if self.is_con_full() and self.forte3_available():
                return
            self.click(after_sleep=0.1)
        self.logger.warning('Suisui concerto fill timed out')

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        since_last = self.time_elapsed_accounting_for_freeze(self.last_forte3_switch)
        # 还没满协奏切出过(-1)时 since_last=10000, 不能当成「太久没上场」, 否则开局一直抢 MUST
        if self.last_forte3_switch > 0 and since_last > 40:
            return SwitchPriority.MUST
        elif since_last < self.FORTE3_SWITCH_LOCKOUT:
            return SwitchPriority.NO
        has_main_dps = any(
            char and char != self and char.is_main_dps
            for char in getattr(self.task, 'chars', [])
        )
        if has_main_dps:
            if current_char and current_char.is_main_dps and has_intro:
                return SwitchPriority.MUST
        return super().get_switch_priority(current_char, has_intro, target_low_con)
