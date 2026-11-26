"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.Labels import Labels
from src.char.Qingxiao import Qingxiao as NativeQingxiao
from src.coco.characters.base import CocoCharacter


class Qingxiao(CocoCharacter, NativeQingxiao):
    BURST_FALLBACK = 30.0

    def __init__(self, *args, **kwargs):
        self.last_burst_time = -1
        super().__init__(*args, **kwargs)
        self.must_cast_lib_this_turn = False

    def burst_turn(self):
        """标准队(清达莫)等两个队友延奏都挂着的变奏入场才打整套; 太久没打过就直接打。"""
        if self.has_all_buff():
            return True
        since = max(self.last_burst_time, getattr(self.task, 'combat_start', 0) or 0)
        if since <= 0:
            return False
        return self.time_elapsed_accounting_for_freeze(since) > self.BURST_FALLBACK

    def do_perform(self):
        self.must_cast_lib_this_turn = self.burst_turn()
        if self.must_cast_lib_this_turn:
            if not self.has_all_buff():
                self.logger.info(f'qingxiao: no full burst for {self.BURST_FALLBACK:.0f}s, burst without both outro buffs')
            self.last_burst_time = time.time()

        if not self.must_cast_lib_this_turn:
            self.cast_enhanced_resonance()
            return self.switch_next_char()

        start = time.time()
        broke_on_h2 = False
        if self.must_cast_lib_this_turn:
            while self.time_elapsed_accounting_for_freeze(start) < 18:
                self.cycle_start()
                if heavy := self.handle_heavy():
                    self.f_break()
                    if heavy == Labels.qingxiao_h2:
                        # 第二次(强化)重击:图标已被 handle_heavy 确认灭(真释放)才回到这 → 开 R
                        if self.task is not None and not self.liberation_available():
                            # h2 多段命中的后半段会把 R 能量打满;等 R 图标亮(上限 1.5s)再开大
                            self.task.wait_until(lambda: self.liberation_available(), time_out=1.5)
                        self.click_liberation()
                        broke_on_h2 = True
                        break
                elif self.cast_enhanced_resonance():
                    pass
                else:
                    self.click()
                self.cycle_sleep()
            if not broke_on_h2:
                self.handle_heavy()

        if broke_on_h2 and self.task is not None:
            # R 未放出时(按钮没亮),强化重击落地动画还没结束就切会撞 not_in_team ERROR;等切人判定稳定再切
            self.task.wait_until(lambda: self.task.in_team()[0], time_out=1.0)
        self.switch_next_char()
