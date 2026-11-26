"""Physical F start for the Auto Combat trigger (coco-ww)."""

import re
import time

from ok import TriggerTask
from ok.util.window import is_foreground_window

F_START_KEY = 'Start Combat with F'
F_DELAY_KEY = 'F Start Delay (seconds)'
F_GRACE_KEY = 'F Start Target Grace (seconds)'
F_DELAY_MAX = 10.0
F_GRACE_MAX = 600.0
F_PRESS_LIFETIME = 10.0
ABSORB_PROMPT_WINDOW = 1.0
PROMPT_REREAD_INTERVAL = 0.5
ABSORB_TEXT = re.compile(r'吸收|Absorb', re.I)

VK_F = 0x46
KEY_DOWN = (0x0100, 0x0104)
KEY_UP = (0x0101, 0x0105)
INJECTED = 0x10 | 0x02  # LLKHF_INJECTED and LLKHF_LOWER_IL_INJECTED
LEGACY_INJECTION_GRACE = 0.2


class FKeyStart:
    def __init__(self, task):
        self.task = task
        self.listener = None
        self.listen_failed = False
        self.armed = False
        self.key_down = False
        self.injected_f_down = False
        self.injected_f_until = 0.0
        self.last_press = float('-inf')
        self.consumed_until = self.last_press
        self.grace_started = None
        self.prompt = None
        self.prompt_read_at = 0.0
        self.prompt_is_absorb = False
        self.absorb_seen_at = float('-inf')

    def listen(self):
        if self.listen_failed:
            return False
        if self.listener is None:
            try:
                from pynput.keyboard import Listener

                self.listener = Listener(win32_event_filter=self._on_key_event)
                self.listener.start()
                self.listener.wait()
            except (ImportError, OSError, RuntimeError) as error:
                self.task.log_warning(f'无法监听物理 F 键：{error}')
                self.listen_failed = True
                return False
        return self.listener.is_alive()

    def close(self):
        self.reset()
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self.listen_failed = False
        self.key_down = False
        self.injected_f_down = False
        self.injected_f_until = 0.0

    def reset(self):
        self.armed = False
        self.consumed_until = time.monotonic()
        self.grace_started = None
        self.prompt = None
        self.absorb_seen_at = float('-inf')

    def _on_key_event(self, message, event):
        # PostMessage never reaches this hook. SendInput and pynput mark their
        # foreground events as injected. Returning False only skips our listener.
        if event.vkCode != VK_F:
            return False
        if event.flags & INJECTED:
            if message in KEY_DOWN:
                self.injected_f_down = True
            elif message in KEY_UP:
                self.injected_f_until = time.monotonic() + LEGACY_INJECTION_GRACE
                self.injected_f_down = False
        elif message in KEY_UP:
            self.key_down = False
        elif message in KEY_DOWN and not self.key_down:
            self.key_down = True
            if self.armed and self.task.f_start_enabled and self._game_in_foreground():
                self.last_press = time.monotonic()
        return False

    @property
    def injected_f_active(self):
        # Legacy team code reads the keyboard state and this task's enabled
        # property separately. Keep synthetic F invisible to that shortcut too.
        return self.injected_f_down or time.monotonic() < self.injected_f_until

    def _game_in_foreground(self):
        if self.task.is_browser():
            hwnd = getattr(self.task.executor.device_manager.capture_method, 'hwnd', 0)
            return bool(hwnd and is_foreground_window(hwnd))
        window = self.task.hwnd
        return bool(window and window.is_foreground())

    def _observe_prompt(self, now):
        prompt = self.task.find_f_with_text()
        if not prompt:
            self.prompt = None
            return
        if (self.prompt is None or abs(prompt.x - self.prompt.x) > prompt.width / 2
                or abs(prompt.y - self.prompt.y) > prompt.height / 2
                or now - self.prompt_read_at >= PROMPT_REREAD_INTERVAL):
            # Read before the key is pressed. The Echo prompt can disappear
            # before the trigger's next screenshot after the player presses F.
            text_box = prompt.copy(x_offset=prompt.width * 5.2, width_offset=prompt.width * 6,
                                   height_offset=4.5 * prompt.height, y_offset=-0.8 * prompt.height)
            self.prompt_is_absorb = bool(self.task.ocr(box=text_box, match=ABSORB_TEXT))
            self.prompt_read_at = now
        self.prompt = prompt
        if self.prompt_is_absorb:
            self.absorb_seen_at = now

    def should_start(self):
        if not self.listen():
            return False
        if not self.task.in_realm():
            self.reset()
            return False
        self.armed = True
        now = time.monotonic()
        self._observe_prompt(now)
        pressed = self.last_press
        if pressed <= self.consumed_until:
            return False
        delay = self.task.f_start_delay
        waited = now - pressed
        if abs(pressed - self.absorb_seen_at) <= ABSORB_PROMPT_WINDOW or waited > delay + F_PRESS_LIFETIME:
            self.consumed_until = pressed
            return False
        if waited < delay or not self.task.load_chars():
            return False
        self.consumed_until = pressed
        self.armed = False
        self.grace_started = now
        return True

    def hold_without_target(self):
        if self.grace_started is None or not self.task.f_start_enabled:
            return False
        limit = self.task.f_grace_limit
        if limit and time.monotonic() - self.grace_started >= limit:
            self.grace_started = None
            return False
        if self.task.config.get('Auto Target', True):
            self.task.middle_click(interval=0.8 if self.task.is_browser() else 0.3)
        return True


class FStartCombatTask(TriggerTask):
    """Lets existing workshop team code read the F settings by task class name."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = F_START_KEY
        self.visible = False
        self.trigger_interval = 60

    def _auto_combat(self):
        from src.task.AutoCombatTask import AutoCombatTask

        return self.get_task_by_class(AutoCombatTask)

    @property
    def enabled(self):
        task = self._auto_combat()
        return bool(task and task.enabled and task.f_start_enabled and not task._f_key_start.injected_f_active)

    @property
    def f_start_delay(self):
        task = self._auto_combat()
        return task.f_start_delay if task is not None else 0.0

    @property
    def grace_limit(self):
        task = self._auto_combat()
        return task.f_grace_limit if task is not None else 0.0

    def run(self):
        return False
