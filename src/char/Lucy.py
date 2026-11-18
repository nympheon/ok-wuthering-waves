import time
from src.char.BaseChar import BaseChar, SwitchPriority

class Lucy(BaseChar):
    FORTE_TIMEOUT = 8.5
    LIB_CD_WAIT = 1.5
    NORMAL_ATTACK_DURATION = 0.1
    HEAVY_ATTACK_DURATION = 0.4
    CLICK_INTERVAL = 0.1
    ENHANCED_HEAVY_INTERVAL = 0.2
    LIB_CLICK_COUNT = 11 #包含冗余点击

    def do_perform(self):
        # 切入时立即执行处决（协同角色已关闭自动处决）
        try:
            if hasattr(self.task, 'check_f_break') and self.task.check_f_break():
                self.task.f_break()
            elif getattr(self.task, 'can_break', False):
                self.task.f_break()
        except Exception:
            pass
        if not self.is_forte_full():
            self.perform_standard()
        self.perform_liberation()
        return self.switch_next_char()

    def perform_standard(self):
        """标准攒能量流程"""
        if self.is_forte_full():
            self.logger.info("露西的共鸣回路能量已满，跳过常规积攒流程")
            return False

        start_time = time.time()
        while not self.is_forte_full():
            # 防卡死超时机制
            if time.time() - start_time > self.FORTE_TIMEOUT:
                self.logger.warning("露西未在时限内攒满共鸣回路能量")
                break

            if self.resonance_available():
                self.click_resonance()

            self.heavy_attack(self.HEAVY_ATTACK_DURATION)

            if self.resonance_available():
                self.click_resonance()

        self.continues_normal_attack(self.NORMAL_ATTACK_DURATION)
        return True

    def perform_liberation(self):
        """大招释放及后续连击流程"""
        if self.resonance_available():
            self.click_resonance()
        self.f_break()
        self.perform_enhanced_heavy()

        # 若重击后仍未亮，边普攻边等最多 6s
        if not self.is_mouse_forte_full():
            fill_start = time.time()
            while not self.is_mouse_forte_full() and time.time() - fill_start < 6.0:
                self.task.click()
                self.sleep(0.1)
                if hasattr(self.task, 'next_frame'):
                    try:
                        self.task.next_frame()
                    except Exception:
                        pass

        if self.is_mouse_forte_full():
            self.task.mouse_down()
            press_start = time.time()
            while time.time() - press_start < 2.5:
                time.sleep(0.05)
                if hasattr(self.task, 'next_frame'):
                    try:
                        self.task.next_frame()
                    except Exception:
                        pass
            self.task.mouse_up()
            self.sleep(0.1)
            # 等黄条变红（最多2s）
            wait_liber_start = time.time()
            liber_after = self.liberation_available()
            while time.time() - wait_liber_start < 2.0 and not liber_after:
                time.sleep(0.1)
                liber_after = self.liberation_available()
                if hasattr(self.task, 'next_frame'):
                    try:
                        self.task.next_frame()
                    except Exception:
                        pass
            if self.echo_available():
                self.click_echo(time_out=0)
        else:
            # 仍未亮，Q后再 R
            if self.echo_available():
                self.click_echo(time_out=0)

        if self.liberation_available():
            self.click_liberation(send_click=True, wait_if_cd_ready=self.LIB_CD_WAIT)
            self.record_liberation_use()
            self.logger.info('露西开始施放共鸣解放')
            for _ in range(self.LIB_CLICK_COUNT):
                self.click()
                self.sleep(self.CLICK_INTERVAL, check_combat=False)
            self.logger.info('露西的共鸣解放操作结束')
        else:
            self.logger.debug("共鸣解放不可用，跳过施放")

        return True

    def perform_enhanced_heavy(self):
        """强化重击执行逻辑"""
        if self.is_mouse_forte_full():
            self.heavy_attack(self.HEAVY_ATTACK_DURATION)
            self.logger.info('露西执行第一段强化重击')
            self.sleep(self.ENHANCED_HEAVY_INTERVAL, check_combat=False)

            self.heavy_attack(self.HEAVY_ATTACK_DURATION)
            self.logger.info('露西执行第二段强化重击')

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        if has_intro and current_char and current_char.char_name in {'char_rebecca'}:
            return SwitchPriority.MUST
        return super().get_switch_priority(current_char, has_intro, target_low_con)
