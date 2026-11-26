"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Qiuyuan import Qiuyuan as NativeQiuyuan
from src.coco.characters.base import CocoCharacter


class Qiuyuan(CocoCharacter, NativeQiuyuan):
    HEAVY_MIN = 2.5

    HEAVY_MAX = 5.0

    E_HOLD_MIN = 0.35

    E_HOLD_MAX = 1.6

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(1.17)
        if self.flying():
            self.wait_down()
        start = time.time()
        time_out = 4 if self.has_sub_dps_intro else 1.2
        while time.time() - start < time_out:
            self.click_echo(time_out=0)
            if time.time() - start < 0.5 and self.click_liberation():
                start = time.time()
            if self.is_mouse_forte_full():
                # 醉墨里先开大再按住打强化重击
                if self.liberation_available():
                    self.click_liberation()
                self.hold_heavy_chain()
                break
            if self.flying():
                self.shorekeeper_auto_dodge()
            self.click()
            self.check_combat()
            self.task.next_frame()
        self.hold_e2()
        self.switch_next_char()

    def hold_heavy_chain(self):
        """按住普攻打完 3 段强化重击(松早了只出第一段)。"""
        self.hold_mouse(self.HEAVY_MAX, until=lambda: not self.is_mouse_forte_full(), min_time=self.HEAVY_MIN)

    def hold_e2(self):
        """长按 E 出不辞远, 进冷却就松(再按着会进奔袭跑路)。"""
        if not self.resonance_available():
            return False
        self.hold_key(self.get_resonance_key(), self.E_HOLD_MAX, until=lambda: self.has_cd('resonance'),
                      min_time=self.E_HOLD_MIN)
        self.record_resonance_use()
        return True
