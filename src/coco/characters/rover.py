"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Rover import Rover as NativeRover
from src.coco.characters.base import CocoCharacter


class Rover(CocoCharacter, NativeRover):
    def perform_spectro_routine(self):
        if self.has_intro:
            self.continues_normal_attack(1)
        self.wait_down()
        self.spectro_routine_aftertune_combo()
        self.click_echo(time_out=0)
        if self.is_forte_full():
            self.check_combat()
            if self.resonance_available() and self.click_resonance(time_out=1)[0]:
                self.continues_normal_attack(1.4)
                self.sleep(0.1)
        self.check_combat()
        if not self.click_liberation(send_click=True):
            self.click_resonance(time_out=1)

    HAVOC_UMBRA_DURATION = 10.0

    HAVOC_COMBO_TIME = 1.6

    def perform_havoc_routine(self):
        """暗主: 暗流满长按普攻进暗涌(翅膀出来闪避取消), 暗涌里 5A→E→闪避 / 5A→闪避 / 5A→大招→声骸。
        大招倍率高、吃暗涌的湮灭增伤, 平时留着; 太久没进暗涌(读不到暗流)就不留了。"""
        self.wait_down()
        if self.is_mouse_forte_full():
            self.heavy_attack(0.6)
            self.task.click(key='right')
            self.sleep(0.1)
            self.havoc_umbra_time = time.time()
        if self.time_elapsed_accounting_for_freeze(getattr(self, 'havoc_umbra_time', -1)) < self.HAVOC_UMBRA_DURATION:
            self.havoc_umbra_combo()
            return
        # 攒暗流: E 出第一刀就涨, 闪避取消第二刀; 再打一套普攻
        if self.resonance_available() and self.click_resonance(send_click=False, time_out=1)[0]:
            self.task.click(key='right')
            self.sleep(0.1)
        self.attack_while(self.HAVOC_COMBO_TIME)
        if self.is_mouse_forte_full():
            self.heavy_attack(0.6)
            self.task.click(key='right')
            self.sleep(0.1)
            self.havoc_umbra_time = time.time()
            self.havoc_umbra_combo()
            return
        hold_from = getattr(self, 'havoc_umbra_time', -1)
        if hold_from < 0:
            hold_from = getattr(self, 'havoc_hold_from', -1)
            if hold_from < 0:
                hold_from = self.havoc_hold_from = time.time()
        if self.time_elapsed_accounting_for_freeze(hold_from) > 25:
            self.click_liberation(send_click=True)
        self.click_echo(time_out=0)

    def havoc_umbra_combo(self):
        for i in range(3):
            if self.time_elapsed_accounting_for_freeze(self.havoc_umbra_time) > self.HAVOC_UMBRA_DURATION:
                break
            self.attack_while(self.HAVOC_COMBO_TIME)
            if i == 0 and self.resonance_available():
                self.click_resonance(send_click=False, time_out=0.8)
            elif i == 2 and self.click_liberation(send_click=True):
                break
            self.task.click(key='right')
            self.sleep(0.1)
        self.click_echo(time_out=0)

    def perform_wind_routine(self):
        if not (self.has_intro and self.wind_routine_click_while_flying(2)):
            self.wind_routine_wait_down(check_forte_full=False)
            if self.resonance_available() and not self.is_forte_full():
                self.click_echo(time_out=0)
                start = time.time()
                flying = False
                while time.time() - start < 1:
                    self.send_resonance_key(interval=0.1)
                    self.task.next_frame()
                    self.click(interval=0.1)
                    if flying := self.wind_routine_flying():
                        break
                use_skyfall_severance = self.use_skyfall_severance
                if flying:
                    self.wind_routine_click_while_flying(1.6 if use_skyfall_severance else 1.74)
                if use_skyfall_severance and self.click_resonance(send_click=False, time_out=1)[0]:
                    self.wind_routine_click_while_flying(1)
        self.click_liberation(send_click=True)
        self.wind_routine_wait_down()

    def perform_basic_routine(self):
        if self.has_intro:
            self.continues_normal_attack(self.intro_motion_freeze_duration + 0.2)
        self.wait_down()
        self.click_echo()
        liber = self.click_liberation(send_click=True)
        res = self.click_resonance(send_click=True, time_out=1)[0]
        if not (liber or res):
            self.continues_normal_attack(1)
