"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Roccia import Roccia as NativeRoccia
from src.coco.characters.base import CocoCharacter


class Roccia(CocoCharacter, NativeRoccia):
    def do_perform(self):
        if self.has_intro:
            self.heavy_attack(1.6)
            self.sleep(0.1)
            self.last_intro = time.time()
            self.plunge()
            if not self.liberation_available() and not self.resonance_available():
                return self.switch_next_char()
        liberated = self.click_liberation()
        if self.click_resonance(time_out=1)[0] or not liberated:
            self.plunge()
            return self.switch_next_char()
        self.click_echo()
        return self.switch_next_char()
