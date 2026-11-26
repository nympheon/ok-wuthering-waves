"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Xigelika import Xigelika as NativeXigelika
from src.coco.characters.base import CocoCharacter


class Xigelika(CocoCharacter, NativeXigelika):
    def perform_everything(self):
        start = time.time()
        time_out = 0.5
        if self.burst_intro():
            time_out = 15
        while self.time_elapsed_accounting_for_freeze(start) < time_out:
            self.click_echo(time_out=0)
            if self.flying():
                self.shorekeeper_auto_dodge()
            if self.handle_heavy():
                return
            elif not self.has_intro and self.lib():
                time_out = 15
                start = time.time()
            elif self.click_resonance(send_click=False, time_out=2)[0]:
                pass
            else:
                self.click(interval=0.1)
            self.sleep(0.05)
