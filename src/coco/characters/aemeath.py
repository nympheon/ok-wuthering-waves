"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Aemeath import Aemeath as NativeAemeath
from src.coco.characters.base import CocoCharacter


class Aemeath(CocoCharacter, NativeAemeath):
    def do_perform(self):
        self.enhance_e_cast_this_turn = False
        self.lib2_cast_this_turn = False
        self.must_cast_lib2_this_turn = self.has_all_buff() and self.has_intro
        if not self.must_cast_lib2_this_turn and self.waits_for_intro():
            start = time.time()
            # 高亮一直不灭(读错/被打断)最多重击 8 秒
            while self.has_long_action() and time.time() - start < 8:
                if self.handle_heavy():
                    self.sleep(0.3)
                else:
                    self.task.next_frame()
            return self.switch_next_char()
        elif self.has_intro:
            self.continues_normal_attack(2.1)

        self.perform_everything()

        self.switch_next_char()

    PERFORM_TOTAL_TIME_OUT = 20

    def perform_everything(self):
        start = time.time()
        # 每放出一招 start 会重置, 另给一个总上限, 免得高亮一直亮着就永远不走
        while (self.time_elapsed_accounting_for_freeze(start) < 12
               and self.field_time() < self.PERFORM_TOTAL_TIME_OUT):
            self.cycle_start()
            if self.handle_heavy():
                start = time.time()
                if not self.f_break():
                    self.sleep(0.1)
                self.check_combat()
                continue
            if self.lib():
                if self.lib2_cast_this_turn:
                    return
                action_performed = True
            elif self.enhance_e_available():
                if self.click_resonance(has_animation=True, send_click=True, animation_min_duration=0.5,
                                        time_out=1.5)[0]:
                    self.record_enhance_e()
                    self.click_echo(time_out=0)
                    self.task.next_frame()
                self.lib()
                if self.lib2_cast_this_turn:
                    return
                action_performed = True
            else:
                self.click()
                action_performed = False
            if action_performed:
                start = self.continue_after_action(start)
                if start is None:
                    return
            self.cycle_sleep()

    def heavy_wait_highlight_down(self):
        self.task.mouse_down()
        try:
            ret = self.task.wait_until(lambda: not self.has_long_action(), time_out=1.2)
        finally:
            self.task.mouse_up()
        self.sleep(0.01)
        return ret
