"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Verina import Verina as NativeVerina
from src.coco.characters.base import CocoCharacter


class Verina(CocoCharacter, NativeVerina):
    def cast_resonance(self):
        """共鸣(E)可用则放。"""
        if self.resonance_available():
            self.click_resonance(send_click=True, time_out=1)
