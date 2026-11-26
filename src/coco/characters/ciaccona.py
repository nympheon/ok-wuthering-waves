"""Selected coco-ww rotation changes based on the current native character."""


import time
from src.char.Ciaccona import Ciaccona as NativeCiaccona
from src.coco.characters.base import CocoCharacter


class Ciaccona(CocoCharacter, NativeCiaccona):
    def continues_click_a(self, duration=0.6):
        # 演唱会的按钮要在光环走到圆环时按下才算(攻略: 大招一放就一直点那个按钮), 按住只算按下那一下;
        # 原来连发没有间隔, 加 0.05 秒间隔
        start = time.time()
        while time.time() - start < duration:
            self.task.send_key('a')
            time.sleep(0.05)
