import time

from src.Labels import Labels
from src.char.BaseChar import BaseChar


class Hsin(BaseChar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lib2_cast_this_turn: bool = False
        self.finisher_start: float | None = None
        self.finisher_e_sent: bool = False
        self.h2_completed: bool = False
        self.h2_guard_until: float = 0.0

    def skip_combat_check(self):
        if self.h2_guard_until and time.time() >= self.h2_guard_until:
            self.logger.info('心的二段重击保护已超时，恢复战斗状态检测')
            self.h2_guard_until = 0.0
        return self.h2_guard_until > 0

    def do_perform(self):
        self.lib2_cast_this_turn = False
        self.finisher_start = None
        self.finisher_e_sent = False
        self.h2_completed = False
        self.h2_guard_until = 0.0
        self.logger.debug(f'心开始行动，触发变奏技能 {self.has_intro}')
        try:
            self.perform_everything()
        finally:
            self.h2_guard_until = 0.0
        self.logger.debug(f'心开始切换角色，本轮已施放第二段共鸣解放 {self.lib2_cast_this_turn}')
        self.switch_next_char()
        self.logger.debug('心切换角色结束')

    def perform_everything(self):
        start = time.time()
        duration = 12 if self.has_intro else 6
        last_e_ready = None
        self.logger.debug(f'心开始本轮输出，时长 {duration} 秒')
        while True:
            phase_start = self.finisher_start if self.finisher_start is not None else start
            phase_duration = 18 if self.finisher_start is not None else duration
            if self.time_elapsed_accounting_for_freeze(phase_start) >= phase_duration:
                self.logger.debug(f'心的输出循环超时，进入终结阶段 {self.finisher_start is not None}，'
                                  f'已施放强化共鸣技能 {self.finisher_e_sent}，已完成二段重击 {self.h2_completed}')
                if not self.h2_completed:
                    self.logger.debug('心结束重击，已达预定时长')
                self.logger.debug('心结束本轮输出，已达预定时长')
                self.logger.info(f'心的本轮输出因超时结束，进入终结阶段 {self.finisher_start is not None}，'
                                 f'已施放强化共鸣技能 {self.finisher_e_sent}，已完成二段重击 {self.h2_completed}')
                return
            self.cycle_start()
            self.logger.debug(
                f'心执行一轮动作，计入战斗时间 {self.time_elapsed_accounting_for_freeze(phase_start):.2f} 秒，'
                f'实际耗时 {time.time() - start:.2f} 秒，处于终结阶段 {self.finisher_start is not None}，'
                f'阶段时限 {phase_duration} 秒')
            # H2 completion survives a temporarily unavailable R2; do not resume E/Q.
            if self.h2_completed:
                if self.lib(after_heavy=True):
                    self.logger.debug('心已施放第二段共鸣解放，本轮输出结束')
                    return
                self.logger.debug('心开始等待下一轮动作')
                self.cycle_sleep()
                self.logger.debug('心等待结束')
                continue
            if self.task.find_one(Labels.hsin_lib2, threshold=0.7):
                self.lib()
                if self.lib2_cast_this_turn:
                    self.logger.debug('心已施放第二段共鸣解放，本轮输出结束')
                    return
            heavy_type = self.heavy_available()
            if heavy_type == 2:
                remaining = phase_duration - self.time_elapsed_accounting_for_freeze(phase_start)
                confirmed = self.handle_heavy(heavy_type)
                self.logger.debug(f'心结束重击，长按前的剩余时间为 {remaining:.2f} 秒')
                if confirmed and self.wait_for_lib2(after_heavy=True):
                    self.logger.debug('心已施放第二段共鸣解放，本轮输出结束')
                    return
                self.logger.debug('心开始等待下一轮动作')
                self.cycle_sleep()
                self.logger.debug('心等待结束')
                continue
            # The live prompt controls E; a transient disappearance must not lock out retries.
            if self.finisher_start is not None:
                ready = self.enhanced_e_ready()
                if ready != last_e_ready:
                    self.logger.info(f'心的强化共鸣技能提示就绪 {ready}，'
                                     f'先前确认施放 {self.finisher_e_sent}')
                    last_e_ready = ready
                if ready:
                    if self.finisher_e_sent:
                        self.logger.info('心的强化共鸣技能提示重新出现，重试共鸣技能')
                    self.finisher_e_sent = False
                    self.cast_enhanced_e()
                else:
                    self.logger.debug(f'心本轮跳过强化共鸣技能，已消耗 {self.finisher_e_sent}')
                    self.logger.debug('心开始普攻')
                    self.click()
                    self.logger.debug('心普攻结束')
                self.logger.debug('心开始等待下一轮动作')
                self.cycle_sleep()
                self.logger.debug('心等待结束')
                continue
            self.logger.debug('心开始施放共鸣技能')
            resonance_start = time.time()
            if self.resonance_available():
                resonance = self.click_resonance(has_animation=False, send_click=True, time_out=0)
            else:
                resonance = (False, 0, False)
                self.logger.debug('心的共鸣技能不可用，跳过施放')
            self.logger.debug(f'心检测并尝试施放共鸣技能，耗时 {time.time() - resonance_start:.3f} 秒')
            self.logger.debug(f'心的共鸣技能操作结束，结果 {resonance}')
            if resonance[0]:
                pass
            elif self.lib():
                if self.lib2_cast_this_turn:
                    self.logger.debug('心已施放第二段共鸣解放，本轮输出结束')
                    return
            elif heavy_type:
                remaining = phase_duration - self.time_elapsed_accounting_for_freeze(phase_start)
                self.handle_heavy(heavy_type)
                self.logger.debug(f'心结束重击，长按前的剩余时间为 {remaining:.2f} 秒')
            elif self.finisher_start is not None:
                self.logger.debug('心开始普攻')
                self.click()
                self.logger.debug('心普攻结束')
            else:
                self.logger.debug('心开始施放声骸技能')
                echoed = self.click_echo(time_out=0)
                self.logger.debug(f'心的声骸技能操作结束，已施放 {echoed}')
                if not echoed:
                    self.logger.debug('心开始普攻')
                    self.click()
                    self.logger.debug('心普攻结束')
            self.logger.debug('心开始等待下一轮动作')
            self.cycle_sleep()
            self.logger.debug('心等待结束')

    def enhanced_e_ready(self) -> bool:
        return bool(self.is_e_forte_full())

    def cast_enhanced_e(self) -> bool:
        self.logger.debug('心开始施放强化共鸣技能')
        self.logger.info('心检测到通用提示就绪，开始施放强化共鸣技能')
        start = time.time()
        last_send = -1.0
        sends = 0
        gone_since = None
        while time.time() - start < 1.5:
            self.check_combat()
            now = time.time()
            if self.enhanced_e_ready():
                gone_since = None
                if now - last_send >= 0.25:
                    self.send_resonance_key()
                    last_send = now
                    sends += 1
                    self.logger.info(f'心尝试施放强化共鸣技能，按键 {sends} 次，耗时 {now - start:.3f} 秒')
            elif last_send >= 0:
                if gone_since is None:
                    gone_since = now
                elif now - gone_since >= 0.25:
                    self.finisher_e_sent = True
                    self.record_resonance_use()
                    self.logger.debug('心已消耗强化共鸣技能，继续普攻')
                    self.logger.info(f'心的强化共鸣技能施放已确认，按键 {sends} 次，'
                                     f'耗时 {time.time() - start:.3f} 秒')
                    return True
            self.task.next_frame()
        self.logger.debug('心的强化共鸣技能施放未确认，就绪后重试')
        self.logger.info(f'心的强化共鸣技能施放未确认，按键 {sends} 次，'
                         f'耗时 {time.time() - start:.3f} 秒')
        return False

    def lib(self, after_heavy: bool = False) -> bool:
        self.logger.debug('心开始施放共鸣解放')
        # A confirmed H2 allows the generic R icon; the helper still must confirm animation.
        is_lib2 = after_heavy or bool(self.task.find_one(Labels.hsin_lib2, threshold=0.7))
        has_feature = is_lib2 or bool(self.task.find_one(Labels.hsin_lib1, threshold=0.7))
        available = self.liberation_available() if has_feature else None
        self.logger.debug(f'心的共鸣解放指示，检测到特征 {has_feature}，第二段 {is_lib2}，可施放 {available}')
        if not has_feature or not available:
            self.logger.debug('心结束共鸣解放尝试，未检测到特征或技能不可用')
            return False
        liberated = bool(self.click_liberation(wait_if_cd_ready=0))
        self.logger.debug(f'心尝试共鸣解放，第二段 {is_lib2}，施放成功 {liberated}')
        if liberated:
            if is_lib2:
                self.lib2_cast_this_turn = True
                self.h2_guard_until = 0.0
            elif self.finisher_start is None:
                # Start the finishing budget after R1 animation, accounting for subsequent freezes.
                self.finisher_start = time.time()
                self.logger.debug('心进入终结阶段，持续 18 秒')
                self.logger.info('心确认施放第一段共鸣解放，进入 18 秒终结阶段')
        self.logger.debug(f'心的共鸣解放操作结束，施放成功 {liberated}，第二段 {is_lib2}')
        return liberated

    def heavy_available(self) -> int:
        if self.task.find_one(Labels.hsin_h2, threshold=0.7):
            return 2
        if self.task.find_one(Labels.hsin_h1, threshold=0.7):
            return 1
        return 0

    def heavy_wait_highlight_down(self, time_out: float, protect_animation: bool = False) -> bool:
        self.logger.debug(f'心开始长按重击，超时设为 {time_out:.2f} 秒')
        self.check_combat()
        self.task.mouse_down()
        if protect_animation:
            # H2 hides the HUD; let R2 take over before retargeting interrupts the animation.
            self.h2_guard_until = time.time() + 4
            self.logger.info('心启动二段重击保护，覆盖第二段共鸣解放过渡，最长 4 秒')
        try:
            confirmed = bool(self.task.wait_until(
                lambda: not self.heavy_available(), time_out=time_out,
                settle_time=0.25, pre_action=self.check_combat))
        except BaseException:
            self.h2_guard_until = 0.0
            raise
        finally:
            self.task.mouse_up()
            self.logger.debug('心已松开重击按键')
        if not confirmed:
            self.h2_guard_until = 0.0
        self.sleep(0.01)
        self.logger.debug(f'心结束长按重击，指示图标已消失 {confirmed}')
        return confirmed

    def handle_heavy(self, heavy_type: int = 0) -> bool:
        self.logger.debug('心开始检测重击')
        heavy_type = heavy_type or self.heavy_available()
        if not heavy_type:
            self.logger.debug('心结束重击尝试，重击不可用')
            return False
        # An already-started hold gets its full window, even near the rotation deadline.
        confirmed = self.heavy_wait_highlight_down(1.2, protect_animation=heavy_type == 2)
        self.logger.debug(f'心尝试重击，类型 {heavy_type}，已确认 {confirmed}')
        if confirmed and heavy_type == 2:
            self.h2_completed = True
        return confirmed

    def wait_for_lib2(self, after_heavy: bool = False) -> bool:
        self.logger.debug(f'心开始等待第二段共鸣解放，已完成重击 {after_heavy}')
        confirmed = bool(self.task.wait_until(
            lambda: (after_heavy or bool(self.task.find_one(Labels.hsin_lib2, threshold=0.7)))
                    and self.lib(after_heavy=after_heavy) and self.lib2_cast_this_turn,
            time_out=1.5, pre_action=self.check_combat))
        self.logger.debug(f'心结束等待第二段共鸣解放，施放成功 {confirmed}，仍待施放 {self.h2_completed and not confirmed}')
        return confirmed
