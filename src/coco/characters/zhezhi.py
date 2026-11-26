"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Zhezhi import Zhezhi as NativeZhezhi
from src.coco.characters.base import CocoCharacter


class Zhezhi(CocoCharacter, NativeZhezhi):
    def do_perform(self):
        if self.char_carlotta is not None:
            return self.do_perform_interlock()
        if self.has_intro:
            self.continues_normal_attack(1.5)
        self.click_liberation()
        if (self._resonance_blue or self.resonance_blue()) and self.resonance_available():
            self._resonance_blue = False
            self.resonance_until_not_blue()
            return self.switch_next_char()
        elif self.resonance_available() and not self.is_forte_full():
            # 3 段普攻约 +45 灵韵, 攒满再放 E 出鹤影
            self.attack_while(1.2, stop=self.is_forte_full)
            if self.is_forte_full() and self.resonance_available():
                self.click_resonance(send_click=False, time_out=1)
                self.continues_normal_attack(0.8)
                self._resonance_blue = True
                return self.switch_next_char()
        elif self.resonance_available() and self.is_forte_full():
            self.click_resonance(time_out=1)
            self.continues_normal_attack(0.8)
            self._resonance_blue = True
            return self.switch_next_char()
        if not self.click_echo():
            self.continues_normal_attack(0.1)
        self.switch_next_char()

    def do_perform_interlock(self):
        if self.has_intro:
            self.continues_normal_attack(1.3)
        if self.flying():
            self.task.wait_until(lambda: not self.flying(), post_action=self.click_with_interval, time_out=1.2)
            self.continues_right_click(0.05)
        if not self.resonance_blue() and self.judge_forte() < 3 and not (
                self.is_con_full() and self.char_carlotta.get_ready()):
            self.continues_normal_attack(1.4)
            if not self.char_carlotta.get_ready():
                return self.switch_next_char()
        if not self.resonance_blue() and self.resonance_available() and self.judge_forte() > 1 and not (
                self.is_con_full() and self.char_carlotta.get_ready()):
            if self.con_lock() and self.click_liberation():
                self.sleep(0.2)
            self.click_resonance(time_out=1)
            self.continues_normal_attack(0.8)
        if self.con_lock():
            if self.resonance_blue() and self.resonance_available():
                self.resonance_until_not_blue()
                if self.con_lock() and self.click_liberation(wait_if_cd_ready=0.5):
                    self.sleep(0.2)
                elif self.echo_available():
                    self.continues_right_click(0.05)
        self.click_echo(time_out=2)
        return self.switch_next_char()
