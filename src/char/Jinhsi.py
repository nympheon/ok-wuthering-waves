import time

from src.char.BaseChar import BaseChar, SwitchPriority


class Jinhsi(BaseChar):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_free_intro = 0  # free intro every 25 sec
        self.has_free_intro = False
        self.incarnation = False
        self.incarnation_cd = False
        self.last_fly_e_time = 0

    def do_perform(self):
        if self.incarnation:
            self.handle_incarnation()
            return self.switch_next_char()
        elif self.has_intro or self.incarnation_cd:
            self.handle_intro()
            return self.switch_next_char()
        self.click_echo()
        return self.switch_next_char()

    def reset_state(self):
        super().reset_state()
        self.incarnation = False
        self.has_free_intro = False
        self.incarnation_cd = False

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        if has_intro or self.incarnation or self.incarnation_cd:
            self.logger.info(
                f'将切换优先级设为最高，触发变奏技能 {has_intro}，乘岁凌霄状态 {self.incarnation}，'
                f'乘岁凌霄技能处于冷却 {self.incarnation_cd}')
            return SwitchPriority.MUST
        return SwitchPriority.NO

    def switch_next_char(self, **args):
        super().switch_next_char(free_intro=self.has_free_intro, target_low_con=True)
        self.has_free_intro = False

    def handle_incarnation(self):
        self.incarnation = False
        self.logger.info('乘岁凌霄状态下开始施放共鸣技能')
        start = time.time()
        animation_start = 0
        last_op = 'resonance'
        self.task.in_liberation = True
        while True:
            if time.time() - start > 6:
                self.logger.info('处理乘岁凌霄状态超时')
                break
            if self.task.in_team()[0]:
                if last_op == 'resonance':
                    self.task.click(interval=0.1)
                    last_op = 'click'
                else:
                    self.send_resonance_key()
                    last_op = 'resonance'
                if animation_start != 0:
                    self.logger.info('今汐处理乘岁凌霄状态完成')
                    break
            else:
                if animation_start == 0:
                    self.logger.info('今汐在乘岁凌霄状态下进入技能动画')
                    animation_start = time.time()
                self.task.in_liberation = True
            self.check_combat()
            self.task.next_frame()
        self.task.in_liberation = False

        if not self.click_echo():
            self.task.click()

        self.add_freeze_duration(animation_start)
        # if self.task.debug:
        #     self.task.screenshot(f'handle_incarnation click_resonance end {time.time() - start}')
        self.logger.info(f'乘岁凌霄状态下的共鸣技能操作结束，耗时 {time.time() - start} 秒')

    def handle_intro(self):
        self.logger.info('开始处理变奏技能')
        start = time.time()
        while True:
            elapsed = time.time() - start
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
        self.logger.info(f'变奏技能处理结束，耗时 {time.time() - start} 秒')
        self.incarnation = True
        self.incarnation_cd = False

    def wait_resonance(self):
        while not self.resonance_available():
            self.send_resonance_key(interval=0.1)
