"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Lucilla import Lucilla as NativeLucilla
from src.coco.characters.base import CocoCharacter


class Lucilla(CocoCharacter, NativeLucilla):
    FOCUS_HOLD_TIME: float = 2.0

    R_AFTER_FOCUS: float = 1.4

    A1_TO_A2: float = 0.45

    A2_TO_A3: float = 0.3

    A3_HOLD_TIME: float = 2.1

    INTRO_SETTLE: float = 0.9

    CHARGE_TIME_OUT: float = 9.0

    LIB_ANIMATION_CAP: float = 6.0

    ZHUIYI_HOLD_CAP: float = 8.0

    DSL_BACK_CAP: float = 3.0

    def perform_combat(self):
        """攒相片 -> 大招可用就放大招打完追忆。放出了大招(已切人)返回 True。"""
        self.task.wait_until(lambda: self.task.in_team()[0], time_out=0.8)
        settle = (self.INTRO_SETTLE if self.has_intro else 0.3) - self.field_time()
        if settle > 0:
            self.sleep(settle, check_combat=False)
        self.task.next_frame()
        # 延奏和格洛犸图声骸联动, 入场先放声骸(大招 CD 中提前走也要放到)
        self.click_echo(time_out=0)

        if self.try_liberation():
            return True

        while self.field_time() < self.CHARGE_TIME_OUT:
            # 能量满但放不出(短CD / 切回来UI没渲染好) -> 别空攒, 切人
            if self.energy_full() and not self.liberation_available():
                self.logger.info('Lucilla energy full but liberation not castable, switch')
                break
            # 能量没满且大招长 CD -> 不攒满, E 好了打一发追光(印象和协奏都留着)再走
            if not self.liberation_available() and self.task.get_cd('liberation') > self.LIBERATION_CD_SKIP:
                self.logger.info('Lucilla liberation on long cd, switch to save time')
                if self.resonance_available():
                    self.focus_shot()
                    self.sleep(1.0)
                break
            if self.try_liberation():
                return True
            if self.resonance_available():
                self.focus_shot()
                # 追光的印象松手后约 0.9 秒才到账, 这段时间等 R 亮
                if self.task.wait_until(self.liberation_available, time_out=self.R_AFTER_FOCUS):
                    continue
            else:
                # E 没好: A1 A2 长按 A3 拿一张相片; 还在追忆里的话就是打到断舍离
                self.focus_a3()
            self.task.next_frame()
        return False

    def focus_shot(self):
        """长按 E 到聚焦环跑满, 自动出追光。不赌金色窗口: E 起手被缓存时定时松手会落进补光。"""
        self.hold_key(self.get_resonance_key(), self.FOCUS_HOLD_TIME)
        self.record_resonance_use()
        self.logger.info(f'Lucilla focus E held {self.FOCUS_HOLD_TIME:.2f}s')

    def focus_a3(self):
        """A1 -> A2 -> 长按 A3 到聚焦环跑满(可圈可点, +50 印象)。"""
        self.click()
        self.sleep(self.A1_TO_A2)
        self.click()
        self.sleep(self.A2_TO_A3)
        self.hold_mouse(self.A3_HOLD_TIME)

    def try_liberation(self):
        """大招就绪则放(顺带先放声骸)并打完追忆、切人, 返回是否放出。"""
        if not self.liberation_available():
            return False
        if self.echo_available():
            self.click_echo(time_out=0)
        self.perform_liberation()
        self.switch_next_char()
        return True

    def energy_full(self):
        """相片是否已满(大招图标高亮, 忽略 CD)。"""
        return self.available('liberation', check_color=True, check_cd=False)

    def perform_liberation(self):
        """放大招 -> 等演出 -> 按住普攻打追忆直到断舍离。

        不用 BaseChar.click_liberation(): 追忆形态下 HUD 判断不稳, 它的等待会误判。
        这里放出判据是「HUD 消失」或「大招图标灭」。
        """
        if not self.task.use_liberation:
            return
        start = time.time()
        hud_gone_at = None
        while time.time() - start < 1.5:
            if not self.task.in_team()[0]:
                hud_gone_at = time.time()
                break
            if not self.liberation_available():
                break
            self.send_liberation_key()
            self.sleep(0.1, check_combat=False)
        self.record_liberation_use()
        self.task.in_liberation = True
        try:
            # 演出: HUD 回来就结束; HUD 读不到就按 4.5 秒保底
            if hud_gone_at is None:
                hud_gone_at = time.time()
            self.task.wait_until(lambda: time.time() - hud_gone_at > 1.0 and self.task.in_team()[0],
                                 time_out=self.LIB_ANIMATION_CAP)
            if not self.task.in_team()[0]:
                left = 4.5 - (time.time() - hud_gone_at)
                if left > 0:
                    self.sleep(left, check_combat=False)
            self.add_freeze_duration(hud_gone_at, time.time() - hud_gone_at)
        finally:
            self.task.in_liberation = False
        self.logger.info('Lucilla liberation animation end, hold attack until 断舍离')
        self.hold_until_dsl()

    def hold_until_dsl(self):
        """追忆: 按住普攻到断舍离(HUD 连续 2 帧消失), 再等 HUD 回来。"""
        gone = 0
        gone_at = None
        start = time.time()
        self.task.mouse_down()
        try:
            while time.time() - start < self.ZHUIYI_HOLD_CAP:
                self.task.next_frame()
                if time.time() - start < 1.0:
                    continue
                if not self.task.in_team()[0]:
                    gone += 1
                    if gone_at is None:
                        gone_at = time.time()
                    if gone >= 2:
                        break
                else:
                    gone = 0
                    gone_at = None
        finally:
            self.task.mouse_up()
        if gone_at is None:
            self.logger.info(f'Lucilla 断舍离 not seen in {self.ZHUIYI_HOLD_CAP}s, released')
            gone_at = time.time()
        # 断舍离期间不能切人, 等 HUD 回来
        self.task.wait_until(lambda: time.time() - gone_at > 0.8 and self.task.in_team()[0],
                             time_out=self.DSL_BACK_CAP)
        self.add_freeze_duration(gone_at, time.time() - gone_at)

    def hold_resonance(self, duration=None):
        """兼容旧接口: 长按 E 对焦(时长固定用追光窗口)。"""
        self.focus_shot()
