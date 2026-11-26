"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Lucy import Lucy as NativeLucy
from src.coco.characters.base import CocoCharacter


class Lucy(CocoCharacter, NativeLucy):
    def perform_standard(self):
        """标准攒能量流程"""
        if self.is_forte_full():
            self.logger.info("Lucy forte is already full, skip standard build-up.")
            return False

        start_time = time.time()
        while not self.is_forte_full():
            # 防卡死超时机制
            if time.time() - start_time > self.FORTE_TIMEOUT:
                self.logger.warning("Lucy failed to fill forte, timeout reached.")
                break

            if self.resonance_available():
                self.click_resonance(time_out=1)

            self.heavy_attack(self.HEAVY_ATTACK_DURATION)

            if self.resonance_available():
                self.click_resonance(time_out=1)

        self.continues_normal_attack(self.NORMAL_ATTACK_DURATION)
        return True

    def perform_liberation(self):
        """大招释放及后续连击流程"""
        if self.resonance_available():
            self.click_resonance(time_out=1)
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
            self.hold_mouse(2.5)
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
            self.logger.info('Lucy perform lib: Started')
            for _ in range(self.LIB_CLICK_COUNT):
                self.click()
                self.sleep(self.CLICK_INTERVAL, check_combat=False)
            self.logger.info('Lucy perform lib: Ended')
        else:
            self.logger.debug("Liberation not available, skipping.")

        return True
