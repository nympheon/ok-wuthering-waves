"""持宏角色共用的宏原语。

楽山的队伍代码里, 持宏角色 (定义 macro_wait、替全队跑轴的那个) 原来每队各抄一份整套引擎, 改一处要
好几份同步, 抄着抄着各自改出了不同版本。通用的收到这里, 队伍代码这样用:

    from src.combat.MacroKit import MacroKit, MacroBroken, send_input_left
    class Hsin(MacroKit, NativeHsin):
        ...

- 只放方法, 不放类常量、不写 __init__: 节奏、阈值这些常量各队写在自己类上, 这里的方法照样用 self.XXX 取。
- 哪支队伍要不一样的写法, 在自己类里照写一个同名方法, 盖过这里的 (MRO: 队伍类 -> MacroKit -> 原生角色类)。
- 不要收框架 BaseChar 或原生角色类上已有的名字: 会盖掉没重写它的队伍原来走的框架版本。
- 也不要随手加新方法: 队伍代码里有 hasattr(char, 'quick_switch') 这种按名字认持宏角色的写法,
  持宏类凭空多出一个名字, 队友代码的判断就变了。
- 分享时 (CustomCharLoader.export_custom_team) 整个文件会原样内联进 zip 里的代码, 替换上面那行 import,
  原版 OKWW 和工坊拿到的还是自包含的文件。所以这里只能 import 标准库、numpy、cv2 和原版 OKWW 也有的框架模块,
  模块级名字也别和队伍代码里的撞 (内联后在同一个模块里)。
- 队伍代码转成用这里: tools/macrokit_convert.py (只删和这里逐字一样的方法, 删前删后逐个方法比对)。
"""

import ctypes
import time

import numpy as np


# ---- SendInput 左键 (attack_down / release_attack 用; 系统级按下, 游戏才认长按) ----
_INPUT_MOUSE = 0
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', ctypes.c_ushort), ('wScan', ctypes.c_ushort), ('dwFlags', ctypes.c_ulong),
                ('time', ctypes.c_ulong), ('dwExtraInfo', ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', ctypes.c_ulong),
                ('dwFlags', ctypes.c_ulong), ('time', ctypes.c_ulong), ('dwExtraInfo', ctypes.c_size_t)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', ctypes.c_ulong), ('wParamH', ctypes.c_ushort), ('wParamL', ctypes.c_ushort)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [('ki', _KEYBDINPUT), ('mi', _MOUSEINPUT), ('hi', _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [('type', ctypes.c_ulong), ('u', _INPUTUNION)]


def send_input_left(up):
    """系统级左键按下/抬起。返回是否发出去了(发不出去调用方退回 PostMessage)。"""
    try:
        inp = _INPUT(type=_INPUT_MOUSE)
        inp.u.mi = _MOUSEINPUT(0, 0, 0, _MOUSEEVENTF_LEFTUP if up else _MOUSEEVENTF_LEFTDOWN, 0, 0)
        return ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT)) == 1
    except Exception:
        return False


class MacroBroken(Exception):
    """某一步切人没成功 / HUD 长时间不在, 后面的按键会落在错的人身上 —— 整圈放弃, 交回框架。"""


class MacroKit:
    """持宏角色的宏原语。混在原生角色类前面用: class Hsin(MacroKit, NativeHsin)。说明见文件开头。

    方法里 self.XXX 读的常量在队伍类上 (各队节奏不一样), 用到哪个方法, 队伍类就要有它读的常量:
    A_* 普攻节奏, KEY_* 技能键重发, SWITCH_* 切人, HUD_* / FIELD_* 在场判定, CON_* 协奏,
    LIB_* / R_* 大招, BREAK_* 破韧提示, E_RESEND_STEP, PRECHARGE_TO_SWITCH, SKILL_BAR_SETTLE,
    TRACE_SWITCH, UNTRUSTED_CONFIRM, RETRY_HUD_CAP。状态 (macro_t0、macro_marks、holding_attack……)
    在队伍类的 __init__ / reset_state 里初始化。
    """

    def teammate(self, name):
        for char in self.task.chars:
            if char is not None and char.name == name:
                return char
        return None

    def opener_pending(self):
        return self.opener_blocked_by() is None

    def macro_wait(self, sec):
        """宏里的精确等待: 不插框架的战斗判定 (框架的 sleep 每 0.4 秒判一次, 判的时候可能中键锁敌好几秒)。

        coco-ww 的 BaseChar 有 precise_wait: 停任务马上生效, 暂停 / 游戏不在前台时松开按着的键、宏从头来。
        原版 OKWW 没有, 退回原来的切片等待 (只管停任务, 不管暂停)。
        """
        precise = getattr(self, 'precise_wait', None)
        if precise is not None:
            return precise(sec)
        if sec <= 0:
            self.task.executor.check_enabled(check_pause=False)
            return
        end = time.time() + sec
        while True:
            left = end - time.time()
            if left <= 0:
                return
            time.sleep(min(0.1, left))
            self.task.executor.check_enabled(check_pause=False)

    def macro_gap(self, sec, tag=None):
        """间隙。【持续普攻打开时自动变成连点】—— 这就是"我没说停就一直A"。"""
        if sec <= 0:
            return 0
        if not self.poking:
            self.macro_wait(sec)
            return 0
        return self.macro_spam(sec, self.A_INTERVAL, tag=tag or 'gapA')

    def macro_start(self):
        self.macro_t0 = time.time()
        self.macro_marks = []

    def macro_mark(self, name):
        self.macro_marks.append(f'{name}@{time.time() - self.macro_t0:.2f}')

    def macro_timeline(self, since=0):
        return ' '.join(self.macro_marks[since:])

    def macro_spam(self, window, interval=None, tag='A', sample=None, sample_every=2,
                   max_clicks=None):
        """连点一个窗口。

        打出几段由 window 决定, 不由单次点击的时机决定 —— 动画期间的点击会被丢掉,
        连点保证总有一下落在动画刚结束的瞬间。时间轴上记首尾和点了几下, 对着录像
        能反推一段动画多长: 窗口里打出 n 段, 一段就约等于 window/n。
        """
        interval = self.A_INTERVAL if interval is None else interval
        start = time.time()
        n = 0
        # 次数上限: 光靠时间兜底的话, interval 被调成 0 或者机器卡一下就会瞬间
        # 灌进去几千次点击
        cap = int(window / max(interval, 0.01)) + 2
        # 【可以再封一层】: 用在【空中】那几格 —— 多余的点击会变成下落攻击,
        # 落地会打断/改变后面的动作。封顶【不缩短窗口】, 所以不花时间
        max_clicks = cap if max_clicks is None else min(cap, max_clicks)
        self.macro_mark(f'{tag}_start')
        self.spam_samples = []
        while time.time() - start < window and n < max_clicks:
            self.click()
            n += 1
            if sample is not None and n % sample_every == 0:
                self.spam_samples.append(f'{time.time() - start:.2f}:{1 if sample() else 0}')
            # 最后一段等待按剩余时间裁剪, 别整个 interval 等下去 —— 那是白送的延迟
            remaining = window - (time.time() - start)
            if remaining <= 0:
                break
            self.macro_wait(min(interval, remaining))
        self.macro_mark(f'{tag}_end(x{n})')
        return n

    def segment_window(self, seg, n=1, lead=None):
        """n 段普攻要给多长的连点窗口。见 spam_segments 的说明。

        Args:
            lead: 覆盖 A_LEAD。【只给个别格子用】—— 某一格要"更早切人"就调它,
                不要去动全局的 A_LEAD(那会把二十来格一起改慢/改快)。
        """
        return max(0.0, (n - 1) * seg) + (self.A_LEAD if lead is None else lead)

    def spam_segments(self, seg, n=1, tag='A', lead=None, interval=None, max_clicks=None):
        """打出 n 段普攻。【调用点写的是段数, 不是秒数】。

        窗口 = (n-1) * 一段 + A_LEAD:
          - 前 n-1 段各要等自己的动画走完, 所以按段长累加;
          - 最后一段只要【递出去】就行 —— 它的动画会在切人之后继续演(合轴),
            所以不给它留时长, 只留 A_LEAD 保证有一下落在能出招的第一帧。

        【为什么还是连点, 不是点 n 下】: 动画期间的点击是被丢掉的、不排队,
        离散点击 + 固定间隔猜错一次那一段就没了。连点打出几段只由窗口长度决定,
        多出来的点击落在动画里, 丢掉不花钱。
        """
        return self.macro_spam(self.segment_window(seg, n, lead),
                               self.A_INTERVAL if interval is None else interval,
                               tag=f'{tag}[{n}seg]', max_clicks=max_clicks)

    def macro_key(self, key, settle=0.0, tag=None):
        self.task.send_key(key)
        self.macro_mark(tag or str(key))
        self.macro_gap(settle)

    def spam_key(self, send, window, interval=None, tag='key', poke=None, presses=None,
                 click_interval=None, stop_when=None):
        """在一个窗口里反复发同一个技能键, 用来盖住动画那一段。

        动画期间的按键是被丢掉的、不排队, 所以单发必丢 —— 这个形状在爱琳莫那条轴上
        踩到过六次, 症状统一是"那一步慢了"(要等整个动画演完才有第二次机会)。

        【必须在这个角色自己的回合里跑完, 不要跟切人并行】: 切人期间发出去的键会被
        游戏带过换人边界落在新角色身上。点击可以并行(quick_switch 的 click_during),
        技能键不行。唯一的例外是 switch_into_lib()。

        Args:
            poke: 发键期间要不要照常点普攻。默认跟随全局的持续普攻开关。
            click_interval: 点普攻的间隔, 默认 A_INTERVAL。给 A_INTERVAL_FAST
                就是"技能键按自己的节奏、普攻按加密节奏", 两条流互不影响。
            stop_when: 每发一次键之后调一次, 返回 True 就停。用在【多按一下会
                烧掉后面要用的充能】的地方 —— 一旦读到技能已经不可用就立刻收手。
                【会读屏, 别配太密的 interval】。
            presses: 只发这么多次, 均匀铺在窗口里。用在"连续点按两次E"那种
                【次数本身有意义】的地方 —— 连发会把两发挤成一发。
                【给了 presses 就由它说了算, window 只用来推间隔】: 否则
                window=0(要求两发贴着发)会在第一发之后就把循环停掉, 变成单发。
        """
        interval = self.KEY_INTERVAL if interval is None else interval
        poke = self.poking if poke is None else poke
        click_interval = self.A_INTERVAL if click_interval is None else click_interval
        if presses is not None and presses > 0:
            interval = max(interval, window / presses)
        start = time.time()
        n = 0
        clicks = 0
        next_click = 0.0
        while True:
            send()
            n += 1
            if stop_when is not None and stop_when():
                break
            if presses is not None:
                if n >= presses:
                    break
                left = interval
            else:
                left = window - (time.time() - start)
                if left <= 0:
                    break
            step_end = time.time() + min(interval, left)
            # 发键的节奏和点击的节奏各走各的 —— 挂在一起的话点击会被技能键的
            # 间隔卡住(爱琳莫那边 R 被 E2_POLL 卡住就是这个)
            while True:
                now = time.time()
                if now >= step_end:
                    break
                if poke and now >= next_click:
                    self.click()
                    clicks += 1
                    next_click = now + click_interval
                self.macro_wait(min(0.02, step_end - time.time()))
        # 【点击数也要打进去】: x{n} 只数了技能键, 看不出这段时间有没有在持续普攻。
        # 用户 2026-08-16 问过一次"E的期间也要一直普攻" —— 实际一直在点,
        # 只是日志里看不见。A x0 就是真的没点(poke=False 的那几格)
        self.macro_mark(f'{tag}(x{n},A x{clicks})')
        return n

    def resonance_gone(self, char):
        """这个角色的 E 是不是已经不可用了(放出去了 / 进了 CD)。

        【读屏】(task.available -> has_cd), 只给 spam_key 的 stop_when 用,
        别放进热路径。冷启动那段发机甲 E 的循环用的是同一个判据。
        """
        try:
            self.task.next_frame()
            return not char.resonance_available()
        except Exception:
            return False

    def resend_until_fired(self, char, cd_name, key, time_out, interval=None, tag='E'):
        """反复发同一个技能键, 直到它真的放出去了(进了 CD)。

        【发出去】和【放出来】是两回事: 动画期间的按键会被丢掉, 而日志上只看得到
        "键发过了"。进了 CD 立刻停, 不会多按掉后面还要用的那一发。
        """
        interval = self.KEY_INTERVAL if interval is None else interval
        start = time.time()
        n = 0
        max_presses = int(time_out / max(interval, 0.01)) + 2
        while time.time() - start < time_out and n < max_presses:
            if self.task.get_cd(cd_name) > 0:
                char.record_resonance_use()
                self.macro_mark(f'{tag}_ok(x{n})')
                return True
            self.task.send_key(key)
            n += 1
            self.macro_gap(interval)
        self.macro_mark(f'{tag}_timeout(x{n})')
        self.logger.warning(f'{tag} never entered cd after {n} presses '
                            f'({time_out:.1f}s), swallowed by an animation?')
        return False

    def macro_hold_attack(self, hold, settle=0.0, tag='hold'):
        self.task.mouse_down()
        self.holding_attack = True
        self.macro_mark(f'{tag}_down')
        try:
            self.macro_wait(hold)
        finally:
            self.release_attack()
        self.macro_mark(f'{tag}_up')
        self.macro_gap(settle)

    def release_attack(self):
        if self.holding_attack:
            if getattr(self, 'si_holding', False):
                send_input_left(True)
                if track := getattr(self.task, 'track_direct_macro_attack', None):
                    track(False, send_input_left)
                self.si_holding = False
            else:
                self.task.mouse_up()
            self.holding_attack = False

    def quick_switch(self, target, click=False, click_during=None, settle=None, time_out=None,
                     read_con=False, assume_con=False, click_interval=None,
                     click_first=False):
        """按数字键直切给指定角色。

        不走 switch_next_char(): 那个要先跑 _choose_switch_target 选人, 顺序是框架
        说了算; 而且它每次发数字键都跟一次左键, 想不要那下 A 就没法不要。

        Args:
            click: 到场之后补一下普攻(复刻框架 BaseCombatTask.py:644 的行为)。
                这条轴上一般不用 —— 持续普攻本身就在点, 再补就是多推一段连段。
            click_during: 等换人生效的这段时间里继续点。默认跟随持续普攻开关。
                这就是用户说的"狂点普攻切人": 换人不是瞬间的, 这几下落在上一个
                角色身上, 正好把他最后那一段打出来。
            read_con: 按键之前读一次协奏, 决定要不要按"带变奏"记账。
                【不便宜】(能量环连通域分析), 只有真的要变奏的那两三处才传 True。
            assume_con: 不读屏, 直接按满协奏记。用在【刚放完大招】之后 ——
                那时协奏必满, 而演出期间能量环读数不可信。

        Returns: 是否真的切过去了。
        """
        if target is None:
            return False
        if target is self.cur:
            # 目标已经在场。【这里必须早退】: 不早退的话到场判据立刻成立,
            # 整步 50 毫秒走完, 后面那些"给他的"按键其实发在了别人身上
            self.macro_mark(f'>{target.name[:3]}(already)')
            return True
        entry = time.time()
        time_out = self.SWITCH_TIME_OUT if time_out is None else time_out
        settle = self.SWITCH_SETTLE if settle is None else settle
        click_during = self.poking if click_during is None else click_during
        click_interval = self.A_INTERVAL if click_interval is None else click_interval
        source = self.cur if self.cur is not None else self
        # 【第一个数字键要抢在读协奏之前发】: 读协奏是能量环的连通域分析, 少则
        # 二三十毫秒、睡完之后的第一次读屏能到 0.86 秒 —— 夹在"上一个动作"和
        # "数字键"之间就是白白的延迟。切人本身要 0.06~0.11 才落地, 来得及读完
        slot = target.index + 1
        # 【记下第一个数字键的时刻】: 有几格是靠它当锚点的。
        # 用户逐帧量的都是"从切人到 A 出手", 而窗口默认从【检测到到场】算起 ——
        # 中间隔着切人生效 + 读屏确认, 两者差好几十毫秒
        self.switch_press_at = time.time()
        # 【先点几下再发第一个数字键】(click_first = 点几下)。用在"边打A边不停切人"
        # 的格子上: 游戏在角色动作期间会拒绝切人 —— 这正是那种写法不会掐掉 A 的原因。
        # 但如果这一刻场上角色【刚到场、还没起手】, 切人键就没有东西挡着, 会当场生效,
        # 她一下都不打就走。
        # 【一下不够】(用户 2026-08-16: "这里千咲又没A出来了"): 那一下要是没被接受
        # 就白给了。所以改成可以指定点几下 —— 每多一下只把切人键推迟一个
        # click_interval(0.06), 但多一次撞上"能出招的那一帧"的机会
        for i in range(int(click_first)):
            self.click()
            if i + 1 < int(click_first):
                self.macro_wait(click_interval)
        self.task.send_key(slot, down_time=self.SWITCH_KEY_DOWN_TIME)
        if assume_con:
            con_full = True
        elif read_con:
            con_full = bool(source.is_con_full())
        else:
            con_full = False
        con_cost = time.time() - entry

        start = time.time()
        last = start   # 第一个数字键已经在上面发过了
        next_click = 0.0
        trace = [] if self.TRACE_SWITCH else None
        team_size = len([c for c in self.task.chars if c is not None])
        untrusted_hits = 0
        clicks = 0
        while time.time() - start < time_out:
            now = time.time()
            if now - last >= self.SWITCH_KEY_INTERVAL:
                self.task.send_key(slot, down_time=self.SWITCH_KEY_DOWN_TIME)
                last = now
            # 点击的节奏跟切人键解耦: 切人键 0.03 秒一发, 点击照旧 A_INTERVAL,
            # 否则这段时间会以 0.03 的密度灌点击, 远低于安全下限
            if click_during and now >= next_click:
                self.click()
                clicks += 1
                next_click = now + click_interval
            self.task.next_frame()
            in_team, index, count = self.task.in_team()
            # 【count 不达标的 index 打折扣, 但不能一票否决】: in_team() 在只找到
            # 一个槽位文本时照样返回 True 和一个 index(那是渲染顺序的产物);
            # 但一票否决会造成假失败 —— 有槽位被特效盖住时 count 就是不达标,
            # 切人明明成功了也判不出来, 卡满超时, 整条轴从这里崩
            hit = in_team and index == target.index
            trusted = in_team and count >= team_size
            untrusted_hits = untrusted_hits + 1 if (hit and not trusted) else 0
            if trace is not None:
                trace.append(f'{time.time() - start:.2f}:'
                             f'{(index if trusted else f"?{index}") if in_team else "x"}')
            if hit and (trusted or untrusted_hits >= self.UNTRUSTED_CONFIRM):
                self.handoff(source, target, con_full)
                self.macro_mark(f'>{target.name[:3]}{"^" if con_full else ""}'
                                f'({time.time() - entry:.2f}|con{con_cost:.2f}|A x{clicks})')
                if trace:
                    self.logger.info(f'switch trace -> {target.name}: {" ".join(trace)}')
                if click:
                    self.click()
                    self.macro_mark(f'{target.name[:3]}A')
                self.macro_gap(settle)
                return True
        # 【失败时更要打 trace】:
        #   一直是旧角色的 index  -> 游戏真的在拒绝切人(上一个动作还没演完)
        #   带 ? 的都是目标 index -> 切过去了, 是 count 判据把它挡住了
        #   全是 x               -> HUD 整个不在(演出/时停里)
        self.logger.warning(f'switch to {target.name} slot {slot} timed out '
                            f'after {time_out:.1f}s (stuck in an animation?)'
                            + (f' trace: {" ".join(trace)}' if trace else ''))
        self.macro_mark(f'>{target.name[:3]}FAIL')
        return False

    def handoff(self, from_char, to_char, con_full):
        """复刻 switch_next_char() 尾部那套交接记账 (BaseCombatTask.py:663-672)。

        直接按数字键绕开了框架逻辑, 不补的话没人的 is_current_char 是 True,
        get_current_char() 返回 None, AutoCombatTask 主循环当场崩。
        """
        self.task.in_liberation = False
        from_char.switch_out(con_full=con_full)
        to_char.is_current_char = True
        to_char.has_intro = con_full
        to_char.has_sub_dps_intro = con_full and from_char.is_sub_dps
        to_char.last_switch_in_time = time.time()
        if con_full:
            now = time.time()
            self.task.add_freeze_duration(now, to_char.intro_motion_freeze_duration, -100)
            from_char.last_outro_time = now
        self.cur = to_char

    def switch_cd_left(self, char):
        """某个角色的换人 CD 还剩多久 —— 【只算不等】。

        【不读屏】: 头像上那个小数字是 OCR, 不便宜也不稳; 而 last_switch_time 是
        我们自己在 handoff -> switch_out 里落的笔, 免费且精确(框架自己判换人 CD
        用的也是它, BaseCombatTask.py:451)。
        """
        last = getattr(char, 'last_switch_time', -1)
        if last is None or last < 0:
            return 0.0
        return max(0.0, self.SWITCH_CD - (time.time() - last))

    def wait_switch_ready(self, char, tag='swCD', lead=0.0):
        """等某个角色的换人 CD 转好。

        用户在启动轴上明写: "要等千咲切人CD转好后立刻E1切千咲"。

        Args:
            lead: 【提前这么多就返回】, 把剩下这段留给调用方拿去跟切人并行。
                用在"等CD -> 发技能 -> 切人"这种串行链上 —— quick_switch 本来
                就会按 SWITCH_KEY_INTERVAL 一直重发数字键, 所以让它压着 CD 尾巴
                开始按, 游戏 CD 一到那一帧就生效, 而不是"CD到了才开始按、再花
                0.13 秒确认到场"。
                【实测值】(2026-08-19 日志, 连续两轮一致): 这一格切千耗时 0.13,
                整条链 denA12结束@14.36 -> 等CD 0.44 -> denE1@14.81 -> 千到场@14.94。
                lead 就是从那 0.13 里省出来的。
        Returns: 实际等了多久。
        """
        left = self.switch_cd_left(char)
        wait = left - lead
        if wait <= 0:
            self.macro_mark(f'{tag}(0.00|left{left:.2f})')
            return 0.0
        self.macro_gap(wait, tag=tag)
        self.macro_mark(f'{tag}({wait:.2f}|lead{left - wait:.2f})')
        return wait

    def switch_out_while_key(self, target, source, key_send, click=True,
                             read_con=False, time_out=None, tag=None):
        """一边切人, 一边给【离场角色】补技能键 —— 键只在 HUD 还读得到他时才发。

        用户 2026-08-19: "E和切人同时进行, 同时持续攻击"。

        【为什么要那道门】: 切人期间发出去的技能键会被游戏【带过换人边界, 落在新上场
        的角色身上】—— 真同时发的话那发 E 很可能变成达妮娅放的, 白烧她一层充能,
        而且小爱没变成机甲。这条在 达E1 那格已经烧过一次(所以那里改成了单发)。
        所以判据是【HUD 还显示离场角色在场 = 这一发还会落在他身上】, 一从 HUD 上
        消失就立刻停发。

        跟 switch_into_lib 是同一个机制、相反的方向: 那边要 R 落在【新】角色身上,
        所以【等】离场角色消失才开始发; 这边要 E 落在【老】角色身上, 所以他一消失
        就【停】。

        点击不受这道门约束 —— 点击落错人无所谓(顶多多推一段连段)。
        """
        if target is None:
            return False
        if target is self.cur:
            self.macro_mark(f'>{target.name[:3]}(already)')
            return True
        entry = time.time()
        time_out = self.SWITCH_TIME_OUT if time_out is None else time_out
        src = source if source is not None else (self.cur or self)
        slot = target.index + 1
        self.switch_press_at = entry
        # 【第一个数字键要抢在读协奏之前发】(quick_switch 里早就是这么做的, 这个新方法
        # 漏了 —— 用户 2026-08-19 报"小爱E切达还是快0.2s")。
        # 读协奏是能量环的连通域分析: 帧是热的时候二三十毫秒, 但【睡完之后的第一次
        # 读屏要等一张新截图, 实测能到 0.86 秒】。夹在"上一个动作"和"数字键"之间
        # 就是纯延迟, 而切人本身要 0.06~0.11 才落地, 完全来得及在换人之前读完
        self.task.send_key(slot, down_time=self.SWITCH_KEY_DOWN_TIME)
        con_full = bool(src.is_con_full()) if read_con else False
        team_size = len([c for c in self.task.chars if c is not None])
        n_key = n_click = 0
        untrusted_hits = 0
        arrived = False
        next_click = 0.0
        while time.time() - entry < time_out:
            now = time.time()
            self.task.send_key(slot, down_time=self.SWITCH_KEY_DOWN_TIME)
            self.task.next_frame()
            in_team, index, count = self.task.in_team()
            # 只要 HUD 还认为离场角色在场, 这一发技能键就还落在他身上
            if in_team and index == src.index:
                key_send()
                n_key += 1
            if click and now >= next_click:
                self.click()
                n_click += 1
                next_click = now + self.A_INTERVAL
            hit = in_team and index == target.index
            trusted = in_team and count >= team_size
            untrusted_hits = untrusted_hits + 1 if (hit and not trusted) else 0
            if hit and (trusted or untrusted_hits >= self.UNTRUSTED_CONFIRM):
                arrived = True
                break
        label = tag or f'>{target.name[:3]}+key'
        if arrived:
            self.handoff(src, target, con_full)
            self.macro_mark(f'{label}{"^" if con_full else ""}'
                            f'({time.time() - entry:.2f}|key x{n_key},A x{n_click})')
        else:
            self.logger.warning(f'switch_out_while_key: {target.name} never came in '
                                f'({n_key} keys, {n_click} clicks)')
            self.macro_mark(f'{label}FAIL(x{n_key})')
        return arrived

    def switch_into_lib(self, target, lag_presses=1, tag='R'):
        """一边疯狂切人一边预输入大招键 —— 【本文件里唯一允许技能键跨切人边界的地方】。

        用户 2026-08-16: "疯狂切达的同时就开始预输入R, 但是R的输入要比切人慢一拍,
        这样就不会误触小爱的R"。

        【为什么要这么写】: 切人期间发出去的键会被游戏带过换人边界落在新角色身上 ——
        平时这是灾难(白烧一个 CD), 这里正是要的机制: 演出/切人的那零点几秒里
        R 已经递进去了, 达尼娅一落地就出手, 省掉"等她到场再发 R"的一整段。

        【为什么要慢一拍】: 第一发 R 要是在切人键之前发出去, 场上还是爱弥斯 ——
        那就是她的大招, 整条轴当场作废。所以先发 lag_presses 次数字键, 再开始
        跟着发 R。这是这个方法唯一的安全边界, 别把 lag 调成 0。
        """
        if target is None:
            return False
        if target is self.cur:
            self.macro_mark(f'>{target.name[:3]}(already)')
            return True
        entry = time.time()
        source = self.cur if self.cur is not None else self
        slot = target.index + 1
        team_size = len([c for c in self.task.chars if c is not None])
        n_key = 0
        n_lib = 0
        untrusted_hits = 0
        arrived = False
        last = 0.0
        # 【R 的放行门】: 只要队伍 HUD 还【明确显示离场角色在场】, 就一发 R 都不发。
        # 原来是按【按键次数】lag(lag_presses=1), 而后来 SWITCH_KEY_INTERVAL 被改成 0
        # (每轮都发切人键), 于是“一拍”变成了几毫秒 —— 爱弥斯还在场上就开始
        # 收到 R, 误开她的大招(用户 2026-08-17: "爱切达还是经常容易误开爱的R1")。
        # 换成看状态就不会随发键密度漂: HUD 还读到她 = 绝对不发。
        # 另加一道时间下界, 防的是“HUD 读不到/读错”时马上就发
        r_open = False
        while time.time() - entry < self.SWITCH_TIME_OUT:
            now = time.time()
            if now - last >= self.SWITCH_KEY_INTERVAL:
                self.task.send_key(slot, down_time=self.SWITCH_KEY_DOWN_TIME)
                n_key += 1
                if r_open and now - entry >= self.R_PREINPUT_MIN_LAG:
                    target.send_liberation_key()
                    n_lib += 1
                last = now
            self.task.next_frame()
            in_team, index, count = self.task.in_team()
            # 离场角色已经不在 HUD 上了 -> 切人基本已经坐实, 可以开始预输入 R
            if not (in_team and index == source.index):
                r_open = True
            hit = in_team and index == target.index
            trusted = in_team and count >= team_size
            untrusted_hits = untrusted_hits + 1 if (hit and not trusted) else 0
            if hit and (trusted or untrusted_hits >= self.UNTRUSTED_CONFIRM):
                arrived = True
                break
        if arrived:
            self.handoff(source, target, False)
            self.macro_mark(f'>{target.name[:3]}+R({time.time() - entry:.2f}|'
                            f'key x{n_key},R x{n_lib})')
            if n_lib == 0:
                # 一发 R 都没递进去: 预输入没生效, 后面那句 fire_lib 会补上,
                # 只是慢一点。比误开爱弥斯的 R1 强得多
                self.logger.info('switch_into_lib: R never sent before arrival '
                                 '(HUD still showed the outgoing char) — R will be sent after')
        else:
            self.logger.warning(f'switch_into_lib: {target.name} never came in '
                                f'({n_key} keys, {n_lib} R)')
            self.macro_mark(f'>{target.name[:3]}+RFAIL(x{n_key})')
        return arrived

    def fire_lib(self, char, tag='R', window=None):
        """把大招发出去。判据是【队伍 HUD 掉下去 = 演出开始】。

        不用 click_liberation(): 它一路阻塞到演出结束才返回, 而这条轴上好几处要在
        演出【期间】继续做事(预输入普攻 / 连发 E / 疯狂切人)。

        【发键之前不读屏确认可放】: 那次读屏是纯延迟, 夹在"上一个动作"和"R键"之间;
        而且它并不能替我们做决定 —— 读到不可用我们照样要发(读数会抖, "没放出来"
        的代价远大于"多按一下")。可用性只在失败分支里读一次, 用来分辨
        "能量不够" 和 "键被动画吞了"。

        【窗口给短】: 正常一两发就进去了。给长的话万一 HUD 判据失灵, 这里会一直
        按 R —— 把后面轮到的那一发大招白按掉。宁可这一次没放出来, 也不要乱放。
        """
        window = self.LIB_FIRE_WINDOW if window is None else window
        start = time.time()
        # 【记下按 R 的时刻】: 后面几格拿它当锚点, 不拿"HUD 回来"。
        # 按键时刻是我们自己发的、精确; HUD 要读屏, 每轮抖几十毫秒。
        # 用户 2026-08-16 逐帧: 达按 R -> A 抬手 = 7s22~12s01 = 4.65 秒,
        # 同一格 HUD 消失 4.18 秒 —— 【HUD 回来之后她还要 0.47 秒才能出招】
        self.lib_press_at = start
        n = 0
        while time.time() - start < window:
            # 【先发键再读屏】(用户 2026-08-16: "QR的还是慢了一点点")。
            # 原来是"读一帧 -> 判HUD -> 才发R", 于是【每次放大招前都白读一次屏】——
            # 实机 denQ@4.49 -> denR1_fired@4.59, 那 0.10 秒全是这次读屏。
            # 而第一轮那次判断本来就没意义: 刚按完 Q, 不可能已经在演出里。
            # 多发的那一下不会有副作用 —— 演出期间的按键被丢掉、不排队
            char.send_liberation_key()
            n += 1
            # 【发键的节奏和读屏的节奏各走各的】(同 spam_key 里那条):
            # 读屏要 0.04, 挂在一起就等于把重试周期翻倍, 而 R 被接受的时刻
            # 只跟【按键什么时候落下】有关
            if n % self.LIB_READ_EVERY == 0:
                self.task.next_frame()
                if not self.task.in_team()[0]:
                    char.record_liberation_use()
                    self.macro_mark(f'{tag}_fired(x{n})')
                    return True
            self.sleep(self.LIB_KEY_INTERVAL, check_combat=False)
        # 最后再确认一次: 键刚发出去、演出还差一帧才开始的情况很常见
        self.task.next_frame()
        if not self.task.in_team()[0]:
            char.record_liberation_use()
            self.macro_mark(f'{tag}_fired(x{n})')
            return True
        self.macro_mark(f'{tag}_NOFIRE(x{n})')
        # 失败了才去读一次能量环: lit=False 是"能量不够/大招还没转好",
        # lit=True 是"键被上一个动作的动画吞了" —— 两种要改的地方完全不同
        try:
            lit = bool(char.liberation_available())
        except Exception:
            lit = 'err'
        self.logger.warning(f'{tag}: {char.name} liberation never started an animation '
                            f'after {n} presses (icon lit={lit})')
        return False

    def spam_key_through_lib(self, send, tag='key', time_out=None, tail=None, poke=None):
        """演出期间一直发某个技能键, 发到【演出真的结束】(HUD 回来)再补一小段。

        【为什么不能按固定时长】(爱琳莫那条轴上标定出来的): 大招哪一刻出手是浮动的 ——
        早出手时演出早结束, 固定窗口的尾巴白发; 晚出手时演出还没完窗口就停了,
        那些键一发都没进去(症状是"R完不接E")。盯 HUD 就没有这个问题。
        【tail 不能省】: HUD 回来那一刻角色多半还在收招里, 那几下照样被吞。

        【"HUD 回来"要先确认它消失过】: 上一句 fire_lib 是"HUD 一掉下去就返回"的,
        进到这里时画面正在渐变, 读一帧很可能读回 True —— 那就会在演出刚开头
        就判成"演出结束了"。所以要么先看到它真的消失过, 要么连着 NO_ANIM_GRACE
        秒都读到在场(说明这一次压根没有演出, 多半是大招没放出来)。

        Returns: 演出有没有正常结束(False 说明跑满了上限, 后面多半也不对)。
        """
        time_out = self.LIB_ANIM_TIME_OUT if time_out is None else time_out
        tail = self.LIB_ANIM_TAIL if tail is None else tail
        poke = self.poking if poke is None else poke
        start = time.time()
        n = 0
        gone_seen = False
        back_at = None
        next_click = 0.0
        while time.time() - start < time_out:
            send()
            n += 1
            now = time.time()
            if poke and now >= next_click:
                self.click()
                next_click = now + self.A_INTERVAL
            self.task.next_frame()
            on_hud = self.task.in_team()[0]
            if not on_hud:
                gone_seen = True
                back_at = None
            elif back_at is None:
                if gone_seen or time.time() - start >= self.HUD_NO_ANIM_GRACE:
                    back_at = time.time()
            elif time.time() - back_at >= tail:
                break
            # 【必须 check_combat=False】: 演出期间读不到目标, 默认的 sleep 会跑
            # 战斗判定并抛异常, 整个连发在第一轮就被打断、接着判脱战
            self.sleep(self.KEY_INTERVAL, check_combat=False)
        self.add_freeze_duration(start, time.time() - start)
        self.macro_mark(f'{tag}(x{n},{"ok" if back_at else "timeout"},'
                        f'{"anim" if gone_seen else "NOANIM"},{time.time() - start:.2f}s)')
        return back_at is not None

    def poke_until(self, deadline, tag='poke', interval=None, max_clicks=None,
                   quiet_tail=0.0):
        """一直点普攻到某个【绝对时刻】为止, 顺路记录 HUD 什么时候回来。

        【锚点是按键时刻, 不是 HUD】(用户 2026-08-16 逐帧标定):
        达尼娅按 R 到 A 抬手是 4.65 秒, 同一格 HUD 消失 4.18 秒 ——
        【HUD 回来之后她还要约 0.47 秒才能出招】。两个锚点差的是常量,
        但按键时刻是我们自己发出去的、精确到毫秒, 而 HUD 要靠 in_team() 读屏,
        每轮抖动几十毫秒 —— 所以锚在按键上。

        HUD 回来的时刻照样记进日志(hud=...), 用来盯那个 0.47 稳不稳:
        它要是每轮都在变, 说明演出长度本身有抖动, 那就得改回 HUD 锚点。
        """
        interval = self.A_INTERVAL if interval is None else interval
        start = time.time()
        n = 0
        hud_at = None
        gone_seen = False
        next_click = 0.0
        while True:
            now = time.time()
            if now >= deadline:
                break
            # 【安静尾巴】: 截止前的最后这一段不再点。
            # 目的是让最后一下点击有时间被消费掉, 而不是贴着切人键又起一个
            # 新动作把切人堵住(那个现象实测过)。
            # 【比 max_clicks 好】: 封顶次数会把“后面才能出招”的机会一并堵掉 ——
            # 千咲 A2 那格就是这么死的: 25 轮里 23 轮的 >Den 只有 0.07,
            # 说明根本没有动作挡着切人, 也就是 A2 压根没起手
            if (now >= next_click and now < deadline - quiet_tail
                    and (max_clicks is None or n < max_clicks)):
                self.click()
                n += 1
                next_click = now + interval
            self.task.next_frame()
            if not self.task.in_team()[0]:
                gone_seen = True
            elif gone_seen and hud_at is None:
                hud_at = time.time() - start
            self.macro_wait(0.01)
        # 这一段是大招演出, 计入 freeze, 否则框架会把它算成"这个角色磨蹭了几秒"
        self.add_freeze_duration(start, time.time() - start)
        self.macro_mark(f'{tag}(x{n},{time.time() - start:.2f}s,'
                        f'hud{"%.2f" % hud_at if hud_at is not None else "-"})')
        return hud_at

    def poke_until_hud_back(self, tag='anim', time_out=None, tail=None):
        """演出期间一直点普攻, 等队伍 HUD 回来(演出结束)再往下走。

        【为什么点】: 演出结束的第一帧就要有输入落进去, 而演出期间的点击是被丢掉的、
        不排队 —— 连点免疫被吞, 单发要么埋在演出里要么等太久。
        【为什么还要 tail】: HUD 回来那一刻角色多半还在收招里, 那几下照样被吞。

        用户在启动轴上明写了这一格: "达妮娅动画期间一直点普攻触发不了, 所以需要等
        一点点时间等出手再切, 或者说你识别到了HUD就可以切了"。

        【"HUD 回来"要先确认它消失过】: 同 spam_key_through_lib —— 进来的这一刻
        画面还在渐变, 读一帧很可能读回 True, 那就是"演出刚开头就判成结束"。
        """
        time_out = self.LIB_ANIM_TIME_OUT if time_out is None else time_out
        tail = self.LIB_ANIM_TAIL if tail is None else tail
        start = time.time()
        n = 0
        gone_seen = False
        back = False
        next_click = 0.0
        while time.time() - start < time_out:
            now = time.time()
            if now >= next_click:
                self.click()
                n += 1
                next_click = now + self.A_INTERVAL
            self.task.next_frame()
            if not self.task.in_team()[0]:
                gone_seen = True
            elif gone_seen or time.time() - start >= self.HUD_NO_ANIM_GRACE:
                back = True
                break
            self.macro_wait(0.01)
        # 演出这一段计入 freeze, 否则框架的各种 time_elapsed_accounting_for_freeze
        # 会把它算成"这个角色磨蹭了 5 秒"
        self.add_freeze_duration(start, time.time() - start)
        self.macro_mark(f'{tag}({"ok" if back else "timeout"},'
                        f'{"anim" if gone_seen else "NOANIM"},x{n},'
                        f'{time.time() - start:.2f}s)')
        if tail > 0:
            self.macro_spam(tail, self.A_INTERVAL, tag=f'{tag}Tail')
        return back

    def on_field_char(self, time_out=None):
        """现在场上是谁 —— 【只在拿不到入口角色时才用】, 因为它开局会说谎。

        in_team() 的判据是"哪个槽位的名字文本【找不到】, 谁就在场"(BaseWWTask.py:930)。
        战斗刚开始时队伍 HUD 还在渐入, 三个槽位的文本不是同时出现的 —— 这时它只找到
        一个文本, 但 exist_count == 1 那个分支【照样返回 True 和一个 index】,
        而那个 index 只是渲染顺序的产物。可信判据是 count >= 队伍人数。
        """
        time_out = self.FIELD_SETTLE_TIME_OUT if time_out is None else time_out
        expected = len([c for c in self.task.chars if c is not None])
        end = time.time() + time_out
        while True:
            self.task.next_frame()   # in_team() 读的是缓存帧, 不刷就是反复读同一张图
            in_team, index, count = self.task.in_team()
            if in_team and count >= expected:
                for char in self.task.chars:
                    if char is not None and char.index == index:
                        return char
                return None
            if time.time() >= end:
                self.logger.warning(f'team HUD never settled in {time_out:.1f}s '
                                    f'(in_team={in_team} index={index} count={count} '
                                    f'expected={expected}), cannot tell who is on field')
                return None
            self.macro_wait(0.03)

    def hold_into_switch(self, target, hold, tag='hold'):
        """切人的同时按住攻击键, 到场之后再按住 hold 秒。

        【按下沿必须提到切人之前】: 按住 = 先普攻、续按才变重击, 所以
          - 切完再按住 -> 新角色多出一下平A;
          - 按完立刻切 -> 上一个角色来不及吃掉这个按下沿, 新角色带着"按住"状态上场,
            同样多一下平A。
        爱琳莫那条轴上两处都栽过, 定下来的做法是"按下 -> 留一点点被离场角色消化 -> 切"。

        【一次 mouse_down 就一直有效, 包括跨过切人】—— 但期间【绝对不要】再补按:
        mouse_down 内部会投 WM_ACTIVATE, 窗口收到就把已经按住的状态打断。
        """
        self.task.mouse_down()
        self.holding_attack = True
        self.macro_mark(f'{tag}_down')
        try:
            self.macro_wait(self.PRECHARGE_TO_SWITCH)
            self.quick_switch(target, click_during=False)
            # 用户给的 2.2 秒是【从切到千咲开始】算的, 所以计时起点在这里
            self.macro_wait(hold)
        finally:
            self.release_attack()
        self.macro_mark(f'{tag}_up')

    def wait_con_at_least(self, char, level, tag='con', cap=None, interval=None, poke=True):
        """边打边等协奏圈涨到 level 以上(0~1)。到上限也往下走, 不把轴卡死。

        跟 wait_con_for_intro 的区别: 那个是"等满才交棒"(门槛是 CON_ENOUGH=0.99,
        【那个值是"环还没闭合"的哨兵, 不是真满】—— 要真满就把 level 传 1.0), 这个是
        【等到某个门槛才做下一个动作】—— 用户 2026-08-21: "达妮娅有时候被打断,
        能不能确保协奏圈超过75%才开R2Q切人"。

        【为什么是门槛不是满】: R2 和 Q 自己还会把圈推上去一截, 所以起手时到 75%
        就够她离场时是满的。等满再开 R2 反而是把这一截白等掉。

        【读协奏不便宜】(能量环连通域分析), 所以轮询间隔别调太小。
        【等的期间必须继续打】: 圈是靠打中涨的, 干站着等只会等到超时。
        """
        cap = self.CON_WAIT_TIME_OUT if cap is None else cap
        interval = self.CON_POLL_INTERVAL if interval is None else interval
        start = time.time()
        n = 0
        con = 0.0
        hit = False
        samples = []
        next_click = 0.0
        while self.time_elapsed_accounting_for_freeze(start) < cap:
            try:
                con = float(char.get_current_con())
            except Exception:
                con = 0.0
            if len(samples) < self.CON_SAMPLE_MAX:
                samples.append(f'{time.time() - start:.2f}:{con:.2f}')
            if con >= level:
                hit = True
                break
            now = time.time()
            if poke and now >= next_click:
                self.click()
                n += 1
                next_click = now + self.A_INTERVAL
            self.macro_wait(interval)
        self.macro_mark(f'{tag}({con:.2f},{"ok" if hit else "CAP"},A x{n},'
                        f'{time.time() - start:.2f}s)')
        if not hit:
            self.logger.info(f'{tag}: con only reached {con:.2f} (< {level:.2f}) in '
                             f'{cap:.1f}s — {" ".join(samples)}')
        return hit

    def wait_hud_back(self, tag='anim', time_out=None, tail=0.0):
        """等演出结束(队伍 HUD 回来), 【期间一下都不点】。

        跟 poke_until_hud_back 的唯一差别就是不点普攻 —— 【角色在空中时必须用这个】:
        那时候的点击会变成下落攻击, 一下就把她砸回地面, 后面整段空中戏就没了。

        【"HUD 回来"要先确认它消失过】: 进来的这一刻画面可能还在渐变, 读一帧很可能
        读回 True, 那就是"演出刚开头就判成结束"。
        """
        time_out = self.LIB_ANIM_TIME_OUT if time_out is None else time_out
        start = time.time()
        gone_seen = False
        back = False
        while time.time() - start < time_out:
            self.task.next_frame()
            if not self.task.in_team()[0]:
                gone_seen = True
            elif gone_seen or time.time() - start >= self.HUD_NO_ANIM_GRACE:
                back = True
                break
            self.macro_wait(0.01)
        self.add_freeze_duration(start, time.time() - start)
        self.macro_mark(f'{tag}({"ok" if back else "timeout"},'
                        f'{"anim" if gone_seen else "NOANIM"},{time.time() - start:.2f}s)')
        self.macro_wait(tail)
        return back

    def send_echo_now(self, char, tag='Q', presses=2, window=0.0):
        """立刻放 Q。【三个角色统一走这里, 而且都放在离场前的最后一步】
        (用户 2026-08-21: "因为声骸套装不一样, 统一设定最后放")。

        【不读屏】: click_echo(time_out=0) 的第一件事是读屏 echo_available(),
        读到 False 就掉进慢路径 —— 那条路要 OCR 一次 echo 的 CD, 再轮询最多 1 秒。
        而 Q 的位置个个都在处决/大招刚结束那一带, 那几帧的读数正是最不可信的时候。
        发键不读屏: 落在 CD 上是空操作, 不花钱。
        """
        self.spam_key(char.send_echo_key, window, interval=0.0, tag=tag,
                      presses=presses, poke=False)
        char.record_echo_use()

    def dodge(self, tag='闪避'):
        """闪避。这条轴上它【只用来取消后摇】, 不是为了躲伤害。

        【发完立刻返回】(after_sleep=0): 后面紧跟着的连点要尽早开始 ——
        闪避本身也有 0.27~0.35 秒吃输入, 晚一点开始连点就等于把 A 推到闪避演完之后。
        """
        self.task.send_key(self.task.key_config.get('Dodge Key'), after_sleep=0)
        self.macro_mark(tag)

    def press_e_then_switch(self, char, target, window, to_switch, interval=None, tag='E'):
        """发 E, 【从第一发 E 起算】过 to_switch 秒切给 target。补发窗口必须 <= to_switch。"""
        interval = self.KEY_INTERVAL if interval is None else interval
        e_at = time.time()
        self.spam_key(char.send_resonance_key, window, interval=interval, tag=tag, poke=False)
        char.record_resonance_use()
        left = to_switch - (time.time() - e_at)
        if left > 0:
            self.macro_wait(left)
        return self.quick_switch(target)

    def wait_until_time(self, deadline):
        self.macro_wait(deadline - time.time())

    def hud_ok(self):
        """队伍 HUD 在不在(读当前帧)。见到就记下时刻, 给看门狗用。"""
        ok = bool(self.task.in_team()[0])
        if ok:
            self.hud_seen_at = time.time()
        return ok

    def game_foreground(self):
        try:
            return bool(self.task.executor.interaction.hwnd_window.is_foreground())
        except Exception:
            return False

    def attack_down(self, direct):
        """按下左键。direct = 走 SendInput(失败自动退回 PostMessage)。返回实际走没走 SendInput。"""
        if direct and self.game_foreground() and send_input_left(False):
            self.si_holding = True
            if track := getattr(self.task, 'track_direct_macro_attack', None):
                track(True, send_input_left)
        else:
            direct = False
            self.task.mouse_down()
        self.holding_attack = True
        return direct

    def tap(self, hold=None):
        """点一下普攻, 【真的按住 hold 秒】。"""
        hold = self.A_TAP if hold is None else hold
        self.task.mouse_down()
        self.holding_attack = True
        try:
            self.macro_wait(hold)
        finally:
            self.task.mouse_up()
            self.holding_attack = False

    def switch_retry(self, target, tag, **kw):
        """quick_switch, 超时了先等 HUD 回来再切, 最多再试 SWITCH_RETRIES 次。只花时间。"""
        if self.quick_switch(target, **kw):
            return True
        for i in range(self.SWITCH_RETRIES):
            self.wait_hud_up(cap=2.0, tag=f'{tag}重切前HUD')
            self.macro_mark(f'{tag}切{target.name[:3]}重试#{i + 1}')
            kw2 = dict(kw)
            kw2['time_out'] = self.SWITCH_RETRY_TIME_OUT
            if self.quick_switch(target, **kw2):
                return True
        return False

    def wait_hud_up(self, cap=None, tag='HUD'):
        """等队伍 HUD 【现在】在场。按 R 之前用 —— HUD 本来就不在的时候判"演出开始了"是假成功。"""
        cap = self.HUD_UP_CAP if cap is None else cap
        start = time.time()
        while time.time() - start < cap:
            self.task.next_frame()
            if self.hud_ok():
                if time.time() - start > 0.05:
                    self.macro_mark(f'{tag}在场({time.time() - start:.2f}s)')
                return True
            self.macro_wait(0.02)
        self.macro_mark(f'{tag}一直不在({cap:.1f}s)')
        return False

    def mark_busy(self, busy):
        """F 键监视线程靠它区分"战斗中手动处决"和"重开副本"。"""
        self.task._ww_macro_busy = busy
        self.task._three_fire_macro_busy = busy

    def need(self, ok, what):
        if not ok:
            raise MacroBroken(what)

    def press_key_until_cd(self, send, available, cap, tag, ready_grace=0.15, poke=False):
        """一直按某个技能键到它进 CD。返回放出去了没有(本来就在 CD 上返回 False)。

        【先见过"亮"才认"暗"】: 刚切人那几帧技能栏还是上一个人的, 读到的是【上一个人】的 CD。
        实机 2026-09-11 两处都栽在这:
          - 维里奈刚放完 Q 切今汐, 今汐到场 0.21s 就"判到 Q 进 CD", 可她那时还在变奏入场的不响应输入里,
            角根本没召出来 -> 惊龙破空后协奏只有 0.50, 长离没变奏;
          - 长离刚放完 E 切维里奈, 维里奈到场 0.12s 就"判到 E 进 CD"(读的是长离的 E CD 数字)。
        所以要先读到过一次可用, 之后变成不可用才算放出去; ready_grace 秒都没见过可用, 才当它本来就在
        CD 上、直接跳过。(别的队伍那份引擎里的 press_e_until_cd 没有这道门, 这里不用它。)
        poke: 按键之间顺手点普攻(两条节奏各走各的, 不挤在同一帧)。
        """
        start = time.time()
        n = live = clicks = 0
        seen_ready = False
        next_click = 0.0
        while time.time() - start < cap:
            self.task.next_frame()
            hud = bool(self.task.in_team()[0])
            if hud:
                if available():
                    seen_ready = True
                elif seen_ready and live > 0:
                    self.macro_mark(f'{tag}_ok(x{n},A x{clicks},{time.time() - start:.2f}s)')
                    return True
                elif not seen_ready and time.time() - start >= ready_grace:
                    # 两种情况分不开: 本来就在 CD 上 / 第一发就被接受、技能栏换过来时已经在 CD 了
                    # (没有入场锁的角色切进来第一发 E 常常就是这样)。都不用再按
                    self.macro_mark(f'{tag}_没见过亮(x{n},{time.time() - start:.2f}s)')
                    return False
            send()
            n += 1
            if hud:
                live += 1
            step_end = time.time() + self.E_RESEND_STEP
            while True:
                now = time.time()
                if now >= step_end:
                    break
                if poke and now >= next_click:
                    self.click()
                    clicks += 1
                    next_click = now + self.A_INTERVAL
                self.macro_wait(min(0.02, step_end - now))
        self.macro_mark(f'{tag}_CD?(x{n},seen{int(seen_ready)},{cap:.1f}s)')
        self.logger.info(f'{tag}: never read as on-cooldown after {n} presses (seen ready={seen_ready})')
        return False

    def press_res_until_cd(self, char, cap, tag, ready_grace=None, poke=False):
        ready_grace = self.SKILL_BAR_SETTLE if ready_grace is None else ready_grace
        return self.press_key_until_cd(char.send_resonance_key, char.resonance_available, cap, tag,
                                       ready_grace=ready_grace, poke=poke)

    def fire_r(self, char, tag, window):
        """发大招到队伍 HUD【连续】消失 LIB_GONE_CONFIRM 帧。返回放出去没有。

        发键之前先等 HUD 在场(HUD 本来就不在会假成功)。确认期间继续按 R 没有副作用 —— 演出里的按键被丢掉。
        """
        self.wait_hud_up(tag=f'{tag}前HUD')
        start = time.time()
        self.lib_press_at = start
        n = gone = 0
        fired = False
        while time.time() - start < window:
            char.send_liberation_key()
            n += 1
            self.task.next_frame()
            if not self.hud_ok():
                gone += 1
                if gone >= self.LIB_GONE_CONFIRM:
                    fired = True
                    break
            else:
                gone = 0
            self.macro_wait(self.LIB_KEY_INTERVAL)
        self.task.skip_combat_check = True
        if fired:
            char.record_liberation_use()
            self.macro_mark(f'{tag}_fired(x{n},{time.time() - start:.2f}s)')
            return True
        self.macro_mark(f'{tag}_NOFIRE(x{n})')
        try:
            lit = bool(char.liberation_available())
        except Exception:
            lit = 'err'
        # lit=True: 键被上一个动作吞了; lit=False: 能量不够
        self.logger.warning(f'{tag}: {char.name} liberation never started an animation '
                            f'after {n} presses (icon lit={lit})')
        return False

    def lib_ready_reads(self, char, frames):
        """HUD 在场时连续 frames 帧读到 char 的 R 可用。HUD 不在的帧不算, 最多读 frames*3 帧。"""
        hits = 0
        for _ in range(frames * 3):
            self.task.next_frame()
            if self.hud_ok():
                try:
                    ready = bool(char.liberation_available())
                except Exception:
                    ready = False
                if not ready:
                    return False
                hits += 1
                if hits >= frames:
                    return True
            self.macro_wait(0.02)
        return False

    def ensure_r(self, char, tag, window, cap, build):
        """R 一定要放出来。读 R 亮 -> 按; 亮着却没放出去就再按, 最多 R_TRIES 次;
        不亮 -> build(轮次) 攒一小段再读, 每 R_BLIND_EVERY 轮盲按一次防读数不准。上限 cap 只防打不到怪。
        """
        start = time.time()
        tries = rounds = 0
        while time.time() - start < cap:
            if self.lib_ready_reads(char, 2):
                tries += 1
                if self.fire_r(char, f'{tag}R' if tries == 1 else f'{tag}R重按#{tries - 1}', window):
                    if rounds:
                        self.logger.info(f'{tag}: {char.name} R 攒了 {time.time() - start:.1f}s 能量才放出去')
                    return True
                if tries >= self.R_TRIES:
                    break
                continue
            rounds += 1
            if rounds == 1:
                self.macro_mark(f'{tag}R没亮(攒能量)')
            build(rounds)
            if rounds % self.R_BLIND_EVERY == 0 and not self.lib_ready_reads(char, 2) and \
                    self.fire_r(char, f'{tag}R盲按#{rounds}', self.R_BLIND_WINDOW):
                return True
        self.logger.warning(f'{tag}: {char.name} 的 R 保底 {time.time() - start:.1f}s 还是没放出去 '
                            f'(亮了按 {tries} 次, 攒能量 {rounds} 轮), 不放了')
        return False

    def read_cd(self, name='resonance', char=None):
        """读技能框里的 CD 数字(秒)。不在 CD / 读不到都返回 0(框架没 CD 时返回负数, 截成 0)。"""
        try:
            index = None if char is None else char.index
            return max(0.0, float(self.task.get_cd(name, index)))
        except Exception:
            return 0.0

    def read_con(self, want, settle=None, click=False, tag=None):
        """读协奏: 自己刷帧、给结算留时间, 连着几帧达到 want 就立刻返回。返回期间读到的最大值。"""
        settle = 0.50 if settle is None else settle
        start = time.time()
        best = 0.0
        hits = 0
        next_click = 0.0
        while True:
            now = time.time()
            if click and now >= next_click:
                self.click()
                next_click = now + self.A_INTERVAL
            self.task.next_frame()
            self.hud_ok()
            try:
                con = self.con_now()
            except Exception:
                con = 0.0
            best = max(best, con)
            hits = hits + 1 if con >= want else 0
            if hits >= self.CON_FULL_CONFIRM or time.time() - start >= settle:
                break
            self.macro_wait(self.CON_POLL)
        if tag:
            self.macro_mark(f'{tag}(con{best:.2f},{time.time() - start:.2f}s)')
        return best

    def wait_con_full(self, who, cap, tag, poke=True):
        """边打边等协奏真满(连着几帧)。返回满没满。"""
        start = time.time()
        samples = []
        hits = 0
        next_click = 0.0
        while time.time() - start < cap:
            now = time.time()
            if poke and now >= next_click:
                self.click()
                next_click = now + self.A_INTERVAL
            self.task.next_frame()
            self.hud_ok()
            try:
                con = self.con_now()
            except Exception:
                con = 0.0
            if len(samples) < self.CON_SAMPLE_MAX:
                samples.append(f'{time.time() - start:.2f}:{con:.2f}')
            hits = hits + 1 if con >= self.CON_ENOUGH else 0
            if hits >= self.CON_FULL_CONFIRM:
                self.macro_mark(f'{tag}(满,{time.time() - start:.2f}s)')
                return True
            self.macro_wait(self.CON_POLL)
        self.macro_mark(f'{tag}(没满,{time.time() - start:.2f}s)')
        self.logger.info(f'{tag}: {who} 协奏 {" ".join(samples)}')
        return False

    def con_now(self):
        """当前角色协奏(读当前帧)。框架的 0.99 哨兵里面积已经满了的, 连 CON_SOFT_FRAMES 帧就当 1.0, 见 CON_SOFT_RATIO。"""
        task = self.task
        con = float(task.get_current_con())
        frame = task.frame
        if getattr(self, '_con_soft_frame', None) is frame:
            return 1.0 if getattr(self, "_con_soft_n", 0) >= self.CON_SOFT_FRAMES and con >= 0.99 else con
        self._con_soft_frame = frame
        ratio = 0.0
        if 0.985 <= con < 1.0:
            try:
                from src.task.BaseCombatTask import con_colors
                idx = task._ensure_ring_index()
                full = float(task.con_full_size.get(str(idx), 0) or 0)
                if full > 0:
                    cropped = task.get_con_box().crop_frame(frame)
                    area, _ = task.count_rings(cropped, con_colors[idx],
                                               1500 / 3840 / 2160 * task.screen_width * task.screen_height)
                    ratio = area / full
            except Exception:
                ratio = 0.0
        lo, hi = self.CON_SOFT_RATIO
        self._con_soft_n = getattr(self, "_con_soft_n", 0) + 1 if lo <= ratio <= hi else 0
        if self._con_soft_n >= self.CON_SOFT_FRAMES:
            if self._con_soft_n == self.CON_SOFT_FRAMES:
                self.logger.info(f'con_now: 环没认成闭合但面积已满({ratio:.3f}) 连 {self._con_soft_n} 帧 -> 当满')
            return 1.0
        return con

    def break_prompt(self):
        """怪身上有处决提示(屏幕中间那个 F, 排除拾取 F)。读当前帧。不看顶部的谐度满(f_break_full): 那个比提示早好几秒, 那时按 F 是空按。"""
        task = self.task
        try:
            hit = task.find_one('f_break', box=task.box_of_screen(0.2, 0.2, 0.75, 0.8, hcenter=True, vcenter=True),
                                target_height=720, threshold=self.BREAK_CENTER_MIN)
            return bool(hit) and not task.is_pick_f()
        except Exception as e:
            self.logger.info(f'处决提示读失败 {e}')
            return False

    def press_sure(self, send, available, cap, tag, ready_grace=None):
        """press_key_until_cd; 到上限没进 CD、图标还亮着(按键全被硬直吞了)就等 HUD 回来再按一轮 KEY_RETRY_CAP。
        本来就在 CD 上(没见过亮)的不补。返回放出去没有。"""
        ready_grace = self.SKILL_BAR_SETTLE if ready_grace is None else ready_grace
        if self.press_key_until_cd(send, available, cap, tag, ready_grace=ready_grace):
            return True
        self.wait_hud_up(cap=self.RETRY_HUD_CAP, tag=f'{tag}补按前HUD')
        if not self.icon_lit(available):
            return False
        return self.press_key_until_cd(send, available, self.KEY_RETRY_CAP, f'{tag}补', ready_grace=0.0)

    def fire_r_sure(self, char, tag, window):
        """fire_r; 没放出来而 R 图标还亮着(被打断/键被吞)就等 HUD 回来再按, 最多 R_RETRIES 轮。图标不亮不补。"""
        if self.fire_r(char, tag, window):
            return True
        for i in range(self.R_RETRIES):
            self.wait_hud_up(cap=self.RETRY_HUD_CAP, tag=f'{tag}补按前HUD')
            if not self.icon_lit(char.liberation_available):
                return False
            if self.fire_r(char, f'{tag}补#{i + 1}', self.R_RETRY_WINDOW):
                return True
        return False

    def con_wait(self, who, cap, tag, poke_after=0.0):
        """等协奏真满(连 CON_FULL_CONFIRM 帧), poke_after 秒之后每 A_INTERVAL 补一下普攻。返回满没满。"""
        start = time.time()
        samples = []
        hits = 0
        next_click = start + poke_after
        clicks = 0
        while time.time() - start < cap:
            now = time.time()
            if now >= next_click:
                self.tap()
                clicks += 1
                next_click = time.time() + self.A_INTERVAL
            self.task.next_frame()
            self.hud_ok()
            try:
                con = self.con_now()
            except Exception:
                con = 0.0
            if len(samples) < self.CON_SAMPLE_MAX:
                samples.append(f'{time.time() - start:.2f}:{con:.2f}')
            hits = hits + 1 if con >= self.CON_ENOUGH else 0
            if hits >= self.CON_FULL_CONFIRM:
                self.macro_mark(f'{tag}(满,{time.time() - start:.2f}s,A x{clicks})')
                return True
            self.macro_wait(self.CON_POLL)
        self.macro_mark(f'{tag}(没满,{time.time() - start:.2f}s,A x{clicks})')
        self.logger.info(f'{tag}: {who} 协奏 {" ".join(samples)}')
        return False

    def warn_no_con(self, full, who, nxt):
        """协奏没满就交棒时记一笔 —— 下一个人拿不到变奏入场, 这一圈从这里开始就不对了。"""
        if full:
            return True
        self.logger.warning(f'【协奏没满就交棒】{who} -> {nxt}: {nxt}拿不到变奏入场')
        self.macro_mark(f'{who}协奏不满!')
        return False

    def break_press(self, tag):
        """提示在就按 F, 按完 BREAK_RESEND 提示还在再按; 提示连 BREAK_GONE_FRAMES 帧不见 = 起手了。
        返回(起手前最后一下 F 的时刻 或 None, 按了几下)。"""
        presses = 0
        last_f = 0.0
        gone = 0
        while True:
            if gone == 0 and time.time() - last_f >= self.BREAK_RESEND:
                if presses >= self.BREAK_PRESSES:
                    return None, presses
                self.task.send_key('f', down_time=0.05)
                presses += 1
                last_f = time.time()
            self.macro_wait(0.03)
            self.task.next_frame()
            if self.hud_ok() and self.break_prompt():
                gone = 0
            else:
                gone += 1
                if gone >= self.BREAK_GONE_FRAMES:
                    return last_f, presses

    def macro_exit(self, previous):
        # 长按跨了好几个方法, 中途抛异常的话鼠标会一直按着。这里是唯一保证松手的地方
        self.release_attack()
        self.poking = False
        self.task.skip_combat_check = previous
        self.mark_busy(False)

    def fire_echo(self, char, tag='Q'):
        """把声骸键发出去 —— 【一次, 不读屏、不等】。

        声骸是【脱手技能】: 键递出去角色马上就能做别的, 不需要留时间给它。
        所以这里既不读屏也不连发 —— 那两样都是错的(前一条是纯延迟, 落在 CD 上
        发键本来就是空操作; 后一条实打实占时间, 会把后面的时序整体推歪)。
        它是零耗时的, 放在轴上任何位置都不用再算"塞进哪段死时间"。

        【这条轴上弗洛洛和坎特蕾拉的 Q 靠它】: 弗洛洛用它打断音符后摇、
        坎特蕾拉用它取消强化A 的后摇。
        """
        char.send_echo_key()
        char.record_echo_use()
        self.macro_mark(tag)
        return True

    def pass_intro(self, source, target, cap, tag, poke=False):
        """等 source 协奏真满, 然后切给 target(带变奏记账)。"""
        self.wait_con_at_least(source, self.CON_FULL_LEVEL, tag=tag, cap=cap, poke=poke)
        return self.quick_switch(target, read_con=True)

    def press_echo_until_cd(self, char, cap, tag, ready_grace=0.15):
        return self.press_key_until_cd(char.send_echo_key, char.echo_available, cap, tag,
                                       ready_grace=ready_grace)

    @staticmethod
    def glyph_vec(a):
        v = a.astype(np.float32).flatten()
        v = v - v.mean()
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v

    def lib_ready_now(self, char, reads):
        for i in range(reads):
            self.task.next_frame()
            try:
                if self.task.in_team()[0] and char.liberation_available():
                    return True
            except Exception:
                pass
            if i + 1 < reads:
                self.macro_wait(0.03)
        return False

    def break_ring(self):
        """boss 头像外圈满了(共振度满, 能处决)。读当前帧。没有 boss 血条的怪永远 False。"""
        try:
            return bool(self.task.find_one('f_break_full', threshold=self.BREAK_RING_MIN))
        except Exception:
            return False

    def note_break_prompt(self):
        """切给嘉贝之前读一帧处决提示: 小怪没有外圈, 靠这一下决定嘉贝入场后要不要等提示回来。"""
        self.task.next_frame()
        if self.hud_ok() and self.break_prompt():
            self.break_seen_at = time.time()
