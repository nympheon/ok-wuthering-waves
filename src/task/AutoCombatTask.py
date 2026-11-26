import time

from ok import TriggerTask, Logger, TaskDisabledException
from src.char.CharFactory import char_names
from src.coco.f_key_start import F_DELAY_KEY, F_DELAY_MAX, F_GRACE_KEY, F_GRACE_MAX, F_START_KEY, FKeyStart
from src.scene.WWScene import WWScene
from src.task.BaseCombatTask import BaseCombatTask, NotInCombatException, CharDeadException
from src.task.task_icons import task_icon

logger = Logger.get_logger(__name__)


class AutoCombatTask(BaseCombatTask, TriggerTask):
    owns_switch_healer_config = True
    _reset_combat_on_run = False
    _f_key_start = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {'_enabled': True}
        self.trigger_interval = 0.1
        self.name = "⚔️ Auto Combat"
        self.icon = task_icon('combat')
        self.description = "Enable auto combat in Abyss, Game World etc"
        self.last_is_click = False
        self.default_config.update({
            'Auto Target': True,
            'Use Liberation': True,
            'Check Levitator': True,
            'Switch to Healer before and after Combat': True,
            F_START_KEY: False,
            F_DELAY_KEY: 0.0,
            F_GRACE_KEY: 10.0,
        })
        self.config_description = {
            'Auto Target': 'Turn off to enable auto combat only when manually target enemy using middle click',
            'Use Liberation': 'Do not use Liberation in Open World to Save Time',
            'Check Levitator': 'Toggle the levitator and verify if the character is floating',
            'Switch to Healer before and after Combat': 'Better Chance to Keep Character Alive',
            F_START_KEY: 'Press F in a focused challenge or dungeon to start combat before an enemy is visible.',
            F_DELAY_KEY: 'Wait this many seconds after pressing F. Set to 0 to start immediately.',
            F_GRACE_KEY: 'Keep fighting for this many seconds while waiting to lock onto an enemy. Set to 0 to wait until a target is found.',
        }
        self.config_type[F_START_KEY] = {'sub_configs': {True: [F_DELAY_KEY, F_GRACE_KEY]}}
        self.config_type[F_DELAY_KEY] = {'min': 0.0, 'max': F_DELAY_MAX}
        self.config_type[F_GRACE_KEY] = {'min': 0.0, 'max': F_GRACE_MAX}
        self._f_key_start = FKeyStart(self)
        self.op_index = 0
        self.char_features_warmed_up = False

    @property
    def f_start_enabled(self):
        return bool(self.config.get(F_START_KEY, False))

    @property
    def f_start_delay(self):
        return min(F_DELAY_MAX, max(0.0, self.config.get(F_DELAY_KEY, 0.0)))

    @property
    def f_grace_limit(self):
        return min(F_GRACE_MAX, max(0.0, self.config.get(F_GRACE_KEY, 10.0)))

    def do_check_in_combat(self, target):
        f_start = self._f_key_start
        if f_start is not None:
            if not self.f_start_enabled:
                if f_start.listener is not None or f_start.listen_failed:
                    f_start.close()
            elif not self._in_combat and f_start.should_start():
                self.has_lavitator = self.find_one('edge_levitator', threshold=0.65)
                if self.config.get('Auto Target', True):
                    self.middle_click()
                self._in_combat = True
                self.log_info('按 F 开始战斗')
                return self.scene.set_in_combat()
        return super().do_check_in_combat(target)

    def check_combat_end(self, has_health):
        if self._f_key_start is not None and self._f_key_start.hold_without_target():
            return self.scene.set_in_combat()
        return super().check_combat_end(has_health)

    def has_target(self, double_check=False):
        locked = super().has_target(double_check)
        if locked and self._f_key_start is not None:
            self._f_key_start.grace_started = None
        return locked

    def do_reset_to_false(self):
        if self._f_key_start is not None:
            self._f_key_start.reset()
        return super().do_reset_to_false()

    def combat_end(self):
        self._f_key_start.reset()
        super().combat_end()

    def on_destroy(self):
        self._f_key_start.close()
        super().on_destroy()

    def disable(self):
        # The UI thread only invalidates state; the executor performs the reset.
        self._reset_combat_on_run = True
        self._f_key_start.reset()
        super().disable()

    def reset_auto_combat(self, reason):
        self._reset_combat_on_run = False
        self.reset_to_false(reason)
        self.chars = [None, None, None]
        self.freeze_durations = []

    def warm_up_char_features(self):
        if self.char_features_warmed_up:
            return
        try:
            for char_name in char_names:
                self.get_feature_by_name(char_name)
        except Exception as e:
            logger.warning(f'预加载角色特征失败：{e}')
            return
        self.char_features_warmed_up = True
        logger.info(f'预加载了 {len(char_names)} 个角色特征模板')

    def run(self):
        if self._reset_combat_on_run:
            self.reset_auto_combat('auto combat restarted')
        try:
            return self.run_auto_combat()
        except TaskDisabledException:
            self.reset_auto_combat('auto combat disabled')
            raise

    def run_auto_combat(self):
        self.warm_up_char_features()
        ret = False
        if not self.scene.in_team(self.in_team_and_world):
            self.reset_auto_combat('not in team and world')
            return ret
        self.use_liberation = self.config.get('Use Liberation')
        if not self.use_liberation and not self.in_world():  # 仅大世界生效
            self.use_liberation = True
        combat_start = time.time()
        switched_to_healer = False
        while self.in_combat():
            ret = True
            try:
                if not switched_to_healer:
                    self.switch_healer()
                    switched_to_healer = True
                self.get_current_char().perform()
            except CharDeadException:
                self.log_error(self.tr('Characters dead'), notify=True)
                break
            except NotInCombatException as e:
                logger.info(f'自动战斗已退出，战斗持续 {int(time.time() - combat_start)} 秒，原因：{e}')
                break
        if ret:
            self.combat_end()
            self.switch_healer()
        return ret

    def realm_perform(self):
        if not self.last_is_click:
            if self.op_index % 10 == 0:
                self.send_key_and_wait_animation('4', self.in_illusive_realm, enter_animation_wait=0.2)
            else:
                self.click()
        else:
            if self.available('liberation'):
                self.send_key_and_wait_animation(self.get_liberation_key(), self.in_illusive_realm)
            elif self.available('echo'):
                self.send_key(self.get_echo_key())
            elif self.available('resonance'):
                self.send_key(self.get_resonance_key())
            elif self.is_con_full() and self.in_team()[0]:
                self.send_key_and_wait_animation('2', self.in_illusive_realm)
        self.last_is_click = not self.last_is_click
        self.op_index += 1
        self.sleep(0.02)


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=AutoCombatTask, debug=True)
