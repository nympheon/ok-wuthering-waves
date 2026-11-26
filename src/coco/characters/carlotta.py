"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Carlotta import Carlotta as NativeCarlotta
from src.coco.characters.base import CocoCharacter


class Carlotta(CocoCharacter, NativeCarlotta):
    def do_perform(self):
        if self.press_w == -1:
            self.decide_teammate()
        if self.char_zhezhi is not None:
            return self.do_perform_interlock()
        self.bullet = 0
        if self.has_intro:
            self.logger.debug('has_intro wait click 1.3 sec')
            self.bullet = 1
            self.continues_normal_attack(1.3)
        if self.heavy_click_forte(check_fun=self.is_mouse_forte_full):
            return self.switch_next_char()
        if self.liberation_available() and not self.need_fast_perform():
            auto_dodge = -1
            lib_loop_start = time.time()
            # 图标亮着却放不出(空中/被控)最多点 8 秒
            while self.liberation_available() and time.time() - lib_loop_start < 8:
                if auto_dodge != -1 and time.time() - auto_dodge > 0.5 and self.flying():
                    self.shorekeeper_auto_dodge()
                if self.click_liberation_1():
                    auto_dodge = time.time()
                self.check_combat()
            self.click_echo()
            self.switch_lock = time.time()
            return self.switch_next_char()
        if self.resonance_available():
            if self.bullet == 0:
                self.heavy_attack()
            if self.click_resonance(time_out=1)[0]:
                return self.switch_next_char()
        if self.click_echo():
            return self.switch_next_char()
        self.continues_normal_attack(0.31)
        self.switch_next_char()

    def do_perform_interlock(self):
        self.bullet = 0
        if self.has_intro:
            self.bullet = 1
            self.continues_normal_attack(1.3)
            if self.check_outro() in {'char_zhezhi'}:
                self.do_perform_outro()
                return self.switch_next_char()
        if self.get_forte() < 4 and self.resonance_available() and not self.liberation_ready:
            if self.bullet == 0:
                self.heavy_attack()
            if self.click_resonance(time_out=1)[0]:
                self.forte += 2
                self.switch_lock = time.time()
                return self.switch_next_char()
        if self.get_ready():
            self.continue_liberation = False
        if self.heavy_click_forte(check_fun=self.is_mouse_forte_full):
            self.liberation_ready = True
            return self.switch_next_char()
        if self.liberation_available() and self.continue_liberation:
            auto_dodge = -1
            lib_loop_start = time.time()
            # 图标亮着却放不出(空中/被控)最多点 8 秒
            while self.liberation_available() and time.time() - lib_loop_start < 8:
                if auto_dodge != -1 and time.time() - auto_dodge > 0.5 and self.flying():
                    self.shorekeeper_auto_dodge()
                if self.click_liberation():
                    auto_dodge = time.time()
                    self.continue_liberation = False
                    self.liberation_ready = False
                self.check_combat()
        if self.echo_available():
            self.click_echo()
        self.continues_normal_attack(0.31)
        self.switch_next_char()

    def do_perform_outro(self):
        res = True
        self.char_zhezhi.forte = 0
        self.get_forte()
        if not self.liberation_ready:
            while not self.is_mouse_forte_full():
                if self.resonance_available():
                    self.click_resonance(time_out=1)
                else:
                    self.click_with_interval()
                if self.time_elapsed_accounting_for_freeze(self.last_perform) > 6:
                    break
                self.check_combat()
        if self.heavy_click_forte(check_fun=self.is_mouse_forte_full):
            self.liberation_ready = True
            self.forte = 0
        self.check_combat()
        self._liberation_available = False
        self._resonance_available = False
        click = False
        liber = False
        if self.liberation_ready:
            while self.time_elapsed_accounting_for_freeze(self.last_perform) < 14:
                if self.liberation_available() and not liber:
                    auto_dodge = -1
                    lib_loop_start = time.time()
                    # 图标亮着却放不出(空中/被控)最多点 8 秒
                    while self.liberation_available() and time.time() - lib_loop_start < 8:
                        if auto_dodge != -1 and time.time() - auto_dodge > 0.5 and self.flying():
                            self.shorekeeper_auto_dodge()
                        if self.click_liberation():
                            self.liberation_ready = False
                            liber = True
                            self.forte = 0
                            auto_dodge = time.time()
                        self.check_combat()
                    if liber:
                        self.sleep(0.2)
                if self.click_resonance(time_out=1)[0]:
                    self.continues_normal_attack(0.8)
                    self.forte += 1
                    click = True
                self.click_with_interval(0.1)
                if not self.liberation_available() and not self.resonance_available() and click:
                    break
                self.check_combat()
        if self.click_echo(time_out=2):
            self.switch_lock = time.time()
        self.continue_liberation = not liber
