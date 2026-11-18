import time

from src.char.BaseChar import BaseChar, SwitchPriority


class Encore(BaseChar):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_heavy = 0
        self.liberation_time = 0
        self.last_resonance = 0

    def still_in_liberation(self):
        return self.time_elapsed_accounting_for_freeze(self.liberation_time) < 9.5

    def switch_out(self, con_full=False):
        super().switch_out(con_full=con_full)
        self.last_resonance = 0

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        self.logger.debug(
            f'安可上次重击时间 {self.last_heavy}，距今 {self.time_elapsed_accounting_for_freeze(self.last_heavy, True)} 秒')
        if self.time_elapsed_accounting_for_freeze(self.last_heavy, True) < 4.6:
            return SwitchPriority.NO
        if self.still_in_liberation() or self.can_resonance_step2():
            self.logger.info('共鸣解放仍在持续，将切换优先级设为最高')
            return SwitchPriority.MUST
        return super().get_switch_priority(current_char, has_intro, target_low_con)

    def do_perform(self):
        if self.has_intro:
            elapsed = self.time_elapsed_accounting_for_freeze(self.liberation_time)
            self.logger.debug(f'安可等待变奏技能，已耗时 {elapsed} 秒')
            if 6 < elapsed < 10 and self.is_mouse_forte_full():
                self.logger.debug('安可在变奏技能后执行重击')
                self.heavy_attack(1.2)
                self.sleep(0.1)
                self.last_heavy = time.time()
                return self.switch_next_char()
            else:
                self.wait_down()
        if self.still_in_liberation():
            self.n4()
            return self.switch_next_char()
        if self.click_resonance()[0]:
            if not self.can_resonance_step2(delay=4):
                self.last_resonance = time.time()
                return self.switch_next_char()
        if not self.need_fast_perform() and not self.is_open_world_auto_combat() and self.click_liberation(
                wait_if_cd_ready=0.4):
            self.liberation_time = time.time()
            self.n4()
            return self.switch_next_char()
        else:
            self.logger.info('安可当前无可用技能')
        if self.echo_available():
            self.logger.debug('施放声骸技能')
            self.click_echo()
            return self.switch_next_char()
        self.switch_next_char()

    def can_resonance_step2(self, delay=2):
        return self.time_elapsed_accounting_for_freeze(self.last_resonance, True) < delay

    def n4(self, duration=2.0):
        duration = 2.7 if self.click_resonance()[0] else 2.4
        if self.time_elapsed_accounting_for_freeze(self.liberation_time) < 6:
            self.logger.debug('安可在共鸣解放期间执行四段普攻')
            self.continues_normal_attack(duration=duration)
        elif self.is_mouse_forte_full():
            self.heavy_attack()
            self.logger.debug('安可在共鸣解放期间执行重击')
            self.last_heavy = time.time()
        else:
            self.logger.debug('安可在共鸣解放期间无可执行操作')
            self.click_resonance()
