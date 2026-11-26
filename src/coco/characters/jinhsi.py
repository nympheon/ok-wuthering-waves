"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Jinhsi import Jinhsi as NativeJinhsi
from src.coco.characters.base import CocoCharacter


class Jinhsi(CocoCharacter, NativeJinhsi):
    def do_perform(self):
        if self.incarnation:
            self.handle_incarnation()
            return self.switch_next_char()
        elif self.has_intro or self.incarnation_cd:
            self.handle_intro()
            return self.switch_next_char()
        self.basic_combo()
        return self.switch_next_char()

    def basic_combo(self):
        """没变奏也不在凌霄态(防饿死被切上来/非标准队): 4A 后 E 变 E2 踏空进强化, 再 4A → E。"""
        self.wait_down()
        self.click_echo(time_out=0)
        for _ in range(2):
            self.attack_while(1.3, stop=self.is_con_full)
            if self.is_con_full():
                break
            if self.resonance_available():
                self.click_resonance(send_click=False, time_out=1)

    def handle_intro(self):
        self.logger.info(f'handle_intro start')
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > 4:
                # E 一直读不到 CD(被控/图标读错), 别卡在这
                self.logger.info('handle_intro resonance never on cd, give up')
                break
            if self.has_cd('resonance'):
                if 0.3 < elapsed < 1.5:
                    self.incarnation_cd = True
                    # self.task.screenshot('incarnation_cd')
                    if not self.click_echo():
                        self.click()
                    return
                elif elapsed > 1.5:
                    # self.task.screenshot('incarnation_finished')
                    break
            else:
                self.send_resonance_key(interval=0.1)
            self.task.next_frame()
            self.check_combat()

        self.last_fly_e_time = start
        if self.click_liberation(send_click=True):
            self.continues_normal_attack(0.3)
        else:
            self.continues_normal_attack(1.4)
        # self.task.screenshot(f'handle_intro end {time.time() - start}')
        self.logger.info(f'handle_intro end {time.time() - start}')
        self.incarnation = True
        self.incarnation_cd = False

    def wait_resonance(self, time_out=3):
        start = time.time()
        while not self.resonance_available() and time.time() - start < time_out:
            self.send_resonance_key(interval=0.1)
            self.task.next_frame()
