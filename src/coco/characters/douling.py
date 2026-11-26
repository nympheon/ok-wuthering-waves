"""Selected coco-ww rotation changes based on the current native character."""


from src.char.Douling import Douling as NativeDouling
from src.coco.characters.base import CocoCharacter


GEN = 'G'  # 艮


ZHEN = 'Z'  # 震


class Douling(CocoCharacter, NativeDouling):
    def _do_segment2(self):
        self.check_combat()
        self.task.jump(after_sleep=0.01)
        self.sleep(0.05)
        self.check_combat()
        if self.flying():
            self.click()
            self.sleep(0.05)
        else:
            self.wait_down()
        self.check_combat()
        self._arrange_gua()
        self._heavy_attack_hold(2.5)
        self.click_echo(time_out=0)
        self.click_liberation()
        self._segment = 1
        self.switch_next_char()

    @staticmethod
    def _gua_good(gua):
        # 两下重击先吃右边两个再吃左边两个: 一组同色(少阴) + 一组异色(少阳) 大招才强化
        return len(gua) == 4 and (gua[0] == gua[1]) != (gua[2] == gua[3])

    def _plan_gua(self, gua):
        """最多补两个卦把卦象排成一同一异, 返回要补的序列; 已经对了或补不成返回 ''。"""
        if len(gua) < 2 or self._gua_good(gua):
            return ''
        for seq in (ZHEN, GEN, ZHEN + ZHEN, ZHEN + GEN, GEN + ZHEN, GEN + GEN):
            if self._gua_good((gua + seq)[-4:]):
                return seq
        return ''

    def _add_gua(self, kind):
        if kind == ZHEN:
            # 下落攻击落地命中给震(不用 E: E 之后点普攻会派生 A4 再多给一个震)
            self.task.jump(after_sleep=0.05)
            self.click()
            self.wait_down()
            self.sleep(0.15)
        else:
            # A1 -> A2 命中给艮
            self.continues_normal_attack(0.5)
            self.sleep(0.25)

    def _arrange_gua(self):
        """被打断后卦象常排成两组异色/两组同色, 重击前补卦挤成对的。读不到卦象就不管。"""
        for _ in range(2):
            gua = self.gua()
            seq = self._plan_gua(gua)
            if not seq:
                return
            self.logger.debug(f'douling arrange gua {gua} + {seq}')
            self.check_combat()
            self._add_gua(seq[0])
