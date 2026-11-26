"""Foreground-only manual input and HUD observations for local axis recording.

Adapted from the manual mode in coco-ww cd8c76e, using Windows key state
and the current capture HWND so no system-wide input hook is needed.
"""

import threading
from time import monotonic

import win32api
import win32gui


_NATIVE_KEYS = {ord(key.upper()): key for key in 'wasdqerft1234'} | {
    0x20: 'space', 0xA0: 'lshift', 0x01: 'left', 0x02: 'right', 0x04: 'middle',
    0x05: 'mouse4', 0x06: 'mouse5',
}
_MOUSE_KEYS = frozenset((0x01, 0x02, 0x04, 0x05, 0x06))
_NAMED_KEYS = {'space': 0x20, 'shift': 0xA0, 'lshift': 0xA0, 'rshift': 0xA1,
               'tab': 0x09, 'mouse4': 0x05, 'mouse5': 0x06,
               **{f'f{i}': 0x6F + i for i in range(1, 13)}}
_COMBAT_BINDS = ('Echo Key', 'Liberation Key', 'Resonance Key', 'Tool Key', 'Jump Key', 'Dodge Key')
_SYSTEM_MODIFIERS = (0x11, 0x12, 0x5B, 0x5C)  # Ctrl, Alt, Windows keys


def _binding(name):
    name = str(name).lower()
    return ord(name.upper()) if len(name) == 1 and name.isascii() and name.isalnum() else _NAMED_KEYS.get(name)


def _down(key):
    return bool(win32api.GetAsyncKeyState(key) & 0x8000)


class ManualInputs:
    def __init__(self, driver):
        self.driver = driver
        self.plan = (0, None, {})
        self.worker = None
        self.done = threading.Event()
        self.toggle = threading.Event()

    def configure(self, hwnd, hotkey, game_keys):
        keys = _NATIVE_KEYS.copy()
        for config_key in _COMBAT_BINDS:
            name = game_keys.get(config_key)
            if code := _binding(name):
                keys[code] = name
        toggle = _binding(hotkey)
        keys.pop(toggle, None)
        self.plan = hwnd, toggle, keys
        if self.worker is None or not self.worker.is_alive():
            self.done.clear()
            self.worker = threading.Thread(target=self._poll, name='AxisManualInputs', daemon=True)
            self.worker.start()

    def foreground(self):
        hwnd = self.plan[0]
        return bool(hwnd and win32gui.GetForegroundWindow() == hwnd)

    def _poll(self):
        previous = None
        previous_plan = None
        previous_run = None
        toggle_pressed = False
        held = {}
        while not self.done.is_set():
            hwnd, toggle, keys = plan = self.plan
            if not hwnd or not self.driver.available() or win32gui.GetForegroundWindow() != hwnd:
                previous = None
                toggle_pressed = False
                held.clear()
                self.done.wait(0.06)
                continue
            if any(_down(key) for key in _SYSTEM_MODIFIERS):
                previous = None
                toggle_pressed = False
                held.clear()
                self.done.wait(0.02)
                continue
            run = self.driver.recorder.run
            if run is not previous_run:
                held.clear()
            capture_keys = keys if run is not None and run.mode == 'Manual' else {}
            codes = (*capture_keys, toggle) if toggle else capture_keys
            current = {key for key in codes if _down(key)}
            if previous is not None and previous_plan == plan and win32gui.GetForegroundWindow() == hwnd:
                if toggle in current - previous:
                    toggle_pressed = True
                if toggle in previous - current and toggle_pressed:
                    toggle_pressed = False
                    self.toggle.set()
                now = monotonic()
                changes = (current ^ previous) & capture_keys.keys() if run is previous_run else ()
                for key in changes:
                    down = key in current
                    mouse = key in _MOUSE_KEYS
                    if mouse and down and not self._pointer_in_window(hwnd):
                        continue
                    if down:
                        held[key] = now
                    elif key not in held:
                        continue
                    duration = None if down else round(now - held.pop(key), 3)
                    self.driver.input('mouse' if mouse else 'key', keys[key], down, duration)
            else:
                held.clear()
                toggle_pressed = False
            previous, previous_plan, previous_run = current, plan, run
            self.done.wait(1 / 120)

    @staticmethod
    def _pointer_in_window(hwnd):
        try:
            window = win32gui.WindowFromPoint(win32gui.GetCursorPos())
            return bool(window and win32gui.GetAncestor(window, 2) == hwnd)
        except win32gui.error:
            return False

    def stop(self):
        self.plan = (0, None, {})
        self.done.set()
        if self.worker is not None:
            self.worker.join(timeout=0.15)
            if not self.worker.is_alive():
                self.worker = None
        self.toggle.clear()


class ManualDriver:
    def __init__(self, owner):
        self.owner = owner
        self.recorder = owner.recorder
        self.inputs = ManualInputs(self)
        self.combat = None
        self.last_hud_check = 0.0
        self.last_enemy = 0.0
        self.last_hud = 0.0
        self.last_action = 0.0
        self.started_by_enemy = False
        self.suppress_enemy = False
        self.had_focus = None
        self.status = ''

    def available(self):
        executor = self.owner.executor
        current = executor.current_task
        return (self.owner.enabled and not executor.paused and not executor.exit_event.is_set()
                and self.owner.manual_mode and self.combat is not None and not self.combat.enabled
                and (current is None or current in executor.trigger_tasks))

    def foreground(self):
        return self.available() and self.inputs.foreground()

    def input(self, device, key, down, duration):
        if not self.foreground():
            return
        run = self.recorder.run
        if run is not None and run.mode == 'Manual':
            if down and key not in ('w', 'a', 's', 'd', 'space', 'lshift', 'rshift'):
                self.last_action = monotonic()
            fields = {'duration': duration} if duration is not None else {}
            action = f"{device} {'down' if down else 'up'}"
            self.recorder.event(run, 'input', action=action, key=key, **fields)

    def stop(self, reason):
        self.inputs.stop()
        run = self.recorder.run
        if run is not None and run.mode == 'Manual':
            self.recorder.stop(reason, run)
        self.had_focus = None
        self.suppress_enemy = False

    def tick(self):
        owner = self.owner
        executor = owner.executor
        self.combat = combat = executor.get_task_by_class_name('AutoCombatTask')
        hwnd = self._game_window(executor)
        if not hwnd:
            self.stop('PC game window unavailable')
            self.status = 'Manual recording needs the native PC game window'
            return
        if combat is None or combat.enabled:
            self.stop('Auto Combat enabled')
            self.status = 'Turn off Auto Combat for manual recording'
            return
        self.inputs.configure(hwnd, owner.config.get('Manual recording hotkey'), combat.key_config or {})
        run = self.recorder.run
        focused = self.foreground()
        if focused != self.had_focus:
            self.had_focus = focused
            if run is not None:
                self.recorder.event(run, 'note', message='Game focused' if focused else 'Game lost focus')
        self.status = 'Recording' if run is not None else 'Waiting for manual recording hotkey'
        if not focused:
            self.inputs.toggle.clear()
            self.status = 'Waiting for game focus'
            return

        toggle = self.inputs.toggle.is_set()
        self.inputs.toggle.clear()
        now = monotonic()
        if run is not None:
            if toggle or run.elapsed(now) >= 7200:
                self.recorder.stop('Manual recording finished', run)
                owner.log_info(owner.tr('Manual recording finished'), notify=True)
                self.suppress_enemy = True
                return
            if run.settings['media'] != 'Off':
                executor.next_frame(time_out=0.2)
        auto = owner.config.get('Start manual recording on enemy')
        if not toggle and (run is None and not auto or now - self.last_hud_check < 0.25):
            return
        self.last_hud_check = now
        if executor._frame is None and executor.next_frame(time_out=0.2) is None:
            return
        in_team, slot, _ = combat.in_team()
        self.last_hud = now if in_team else self.last_hud
        enemy = bool(auto and in_team and _enemy_visible(combat))
        if enemy:
            self.last_enemy = now
        if run is None:
            if not enemy and now - self.last_enemy > 1:
                self.suppress_enemy = False
            if toggle or enemy and not self.suppress_enemy:
                # Party recognition only; this uses no combat or targeting inputs.
                if in_team:
                    combat.load_chars()
                run = self.recorder.start(combat, 'Manual')
                if run is not None:
                    self.started_by_enemy = not toggle
                    self.last_enemy = self.last_hud = now
                    self.recorder.field(run, slot if in_team else None)
                    self.recorder.frame(run, executor._frame)
                    self.status = 'Recording'
                    owner.log_info(owner.tr('Manual recording started'), notify=True)
        elif self.started_by_enemy:
            idle_seconds = max(1, owner.config.get('Manual idle seconds'))
            if ((in_team and now - max(self.last_enemy, self.last_action) >= idle_seconds)
                    or (not in_team and now - self.last_hud >= 15)):
                self.recorder.stop('Manual combat ended', run)
                owner.log_info(owner.tr('Manual recording finished'), notify=True)

    @staticmethod
    def _game_window(executor):
        device = executor.device_manager.get_preferred_device() or {}
        if device.get('device') != 'windows':
            return 0
        hwnd = getattr(executor.device_manager.hwnd_window, 'hwnd', 0)
        # Use the exact selected game window and its native game class.
        try:
            if hwnd and win32gui.IsWindow(hwnd) and win32gui.GetClassName(hwnd) == 'UnrealWindow':
                return hwnd
        except win32gui.error:
            pass
        return 0


def _enemy_visible(task):
    locked, unlocked = task.get_target_names()
    names = [locked, unlocked]
    for box in (task.get_box_by_name(locked).scale(1.1), task.get_box_by_name('box_target_enemy_long'),
                task.get_box_by_name('target_box_long2')):
        best = task.find_best_match_in_box(box, names, threshold=0.6)
        if best:
            if best.name == locked:
                return True
            break
    return task.check_health_bar()
