"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Danjin import Danjin as NativeDanjin
from src.coco.characters.base import CocoCharacter


class Danjin(CocoCharacter, NativeDanjin):
    FIELD_TIME_OUT = 6.0

    ATTACK_GAP = 0.3

    E_GAP = 0.35

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.5)
        else:
            self.wait_down()
        self.click_echo(time_out=0)
        self.heavy_if_full()
        if self.resonance_available():
            self.e_chain()
        self.heavy_if_full()
        if self.click_liberation():
            self.continues_normal_attack(0.3)
        if not self.is_con_full():
            self.attack_while(max(0.4, self.FIELD_TIME_OUT - self.field_time()), stop=self.is_con_full)
        self.switch_next_char()

    def e_chain(self):
        # E 起手 + 两段普攻, 后面就能接三段 E(第二段起挂花)
        self.send_resonance_key()
        self.record_resonance_use()
        self.sleep(self.E_GAP)
        for _ in range(2):
            self.click()
            self.sleep(self.ATTACK_GAP)
        for _ in range(3):
            self.send_resonance_key()
            self.sleep(self.E_GAP)

    def forte_full(self):
        return self.is_forte_full() or self.is_mouse_forte_full()

    def heavy_if_full(self):
        if not self.forte_full():
            return False
        self.heavy_attack(0.8)
        self.sleep(0.15)
        self.click()
        self.sleep(0.4)
        return True
