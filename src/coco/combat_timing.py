"""Interruptible timing and held-input cleanup for combat rotations."""

import time
from contextlib import contextmanager
from threading import RLock

from ok import FinishedException, Logger
from ok.core.events import communicate
from ok.device.interaction_methods.pynput import PynputInteraction
from src.coco.foreground_input import SendInput

logger = Logger.get_logger(__name__)


class RotationPaused(BaseException):
    pass


class RotationTimedOut(BaseException):
    pass


class _Rotation:
    def __init__(self, char):
        self.char = char
        self.timeout = getattr(char, 'PERFORM_HARD_TIMEOUT', None)
        self.executor = getattr(char.task, 'executor', None)
        self.pause_start = getattr(self.executor, 'pause_start', None)
        self.paused = False
        self.held = {}
        self.direct_mouse_release = None
        self.lock = RLock()

    def on_pause(self, paused):
        if paused:
            self.paused = True
            self.release_all()

    def on_task_changed(self, task):
        if task is self.char.task and task.paused:
            self.on_pause(True)

    def hold(self, kind, key):
        interaction = self.executor.interaction
        with self.lock:
            self.held[kind, key.lower()] = interaction
            if self.paused:
                self.release_all()

    def release(self, kind, key):
        with self.lock:
            interaction = self.held.pop((kind, key.lower()), None)
            if interaction is None:
                return
            try:
                if (type(interaction) is PynputInteraction and not interaction.clickable()):
                    # The shortcut releases an input we pressed before the game lost focus.
                    if kind == 'key':
                        controller, key = interaction._key_controller(key)
                        controller.release(key)
                    else:
                        from pynput import mouse
                        mouse.Controller().release(interaction.get_mouse_button(key))
                elif kind == 'key':
                    interaction.send_key_up(key)
                else:
                    interaction.mouse_up(key=key)
            except Exception as error:
                logger.debug(f'松开战斗输入 {key} 失败：{error}')

    def release_all(self):
        with self.lock:
            if self.direct_mouse_release is not None:
                self.direct_mouse_release()
                self.direct_mouse_release = None
            for kind, key in list(self.held):
                self.release(kind, key)

    def is_paused(self):
        executor = self.executor
        if executor is None or getattr(executor, 'debug_mode', False):
            return False
        interaction = executor.interaction
        return (self.paused or self.pause_start != executor.pause_start or executor.blocked_by_pause()
                or self.char.task.paused or (interaction is not None and not interaction.should_capture()))


def _watch(task):
    watch = getattr(task, '_rotation_watch', None)
    return watch if isinstance(watch, _Rotation) else None


@contextmanager
def _observe_focus(watch):
    executor = watch.executor
    interaction = getattr(executor, 'interaction', None)
    if not isinstance(interaction, (PynputInteraction, SendInput)) or executor.debug_mode:
        yield
        return
    original = interaction.should_capture
    instance_override = vars(interaction).get('should_capture')

    def check_focus():
        ready = original()
        if not ready:
            watch.on_pause(True)
        return ready

    # The executor can wait for the foreground window inside next_frame().
    interaction.should_capture = check_focus
    try:
        yield
    finally:
        if interaction.should_capture is check_focus:
            if instance_override is None:
                del interaction.should_capture
            else:
                interaction.should_capture = instance_override


@contextmanager
def monitor_rotation(char):
    task = char.task
    previous = _watch(task)
    watch = task._rotation_watch = _Rotation(char)
    try:
        with (_observe_focus(watch), communicate.executor_paused.subscribed(watch.on_pause),
              communicate.task.subscribed(watch.on_task_changed)):
            try:
                yield
            except RotationTimedOut:
                watch.timeout = None
                watch.release_all()
                char.logger.warning(f'{char} 上场超时，结束当前行动并切人')
                char.switch_next_char()
    except RotationPaused:
        watch.release_all()
        char.logger.debug(f'{char} 上场行动因暂停结束')
        if watch.executor is not None:
            task._rotation_watch = previous
            while task.paused:
                if watch.executor.exit_event.is_set():
                    raise FinishedException()
                watch.executor.check_enabled(check_pause=False)
                time.sleep(0.05)
            watch.executor.next_frame()
            in_team, current, _count = task.in_team()
            if in_team:
                task.in_liberation = False
                for teammate in task.chars:
                    if teammate is not None:
                        teammate.is_current_char = teammate.index == current
    except BaseException:
        watch.release_all()
        raise
    finally:
        task._rotation_watch = previous


def stop_rotation_timeout(char):
    watch = _watch(char.task)
    if watch is not None and watch.char is char:
        watch.timeout = None


def check_rotation(task):
    watch = _watch(task)
    if watch is None:
        return
    if watch.is_paused():
        watch.release_all()
        raise RotationPaused()
    if (watch.timeout and not task.in_liberation
            and watch.char.time_elapsed_accounting_for_freeze(watch.char.last_perform) >= watch.timeout):
        raise RotationTimedOut()


def remember_held_input(task, kind, key):
    watch = _watch(task)
    if watch is not None and watch.executor is not None:
        watch.hold(kind, str(key))


def release_paused_input(task, kind, key):
    watch = _watch(task)
    if watch is not None and watch.is_paused():
        watch.release(kind, str(key))
        return True
    return False


def forget_held_input(task, kind, key):
    watch = _watch(task)
    if watch is not None:
        with watch.lock:
            watch.held.pop((kind, str(key).lower()), None)


def set_direct_mouse_release(task, callback):
    watch = _watch(task)
    if watch is not None:
        with watch.lock:
            watch.direct_mouse_release = callback
            if watch.paused:
                watch.release_all()


def precise_wait(task, seconds):
    executor = task.executor
    end = time.perf_counter() + max(0.0, seconds)
    while True:
        if executor.exit_event.is_set():
            raise FinishedException()
        executor.check_enabled(check_pause=False)
        check_rotation(task)
        remaining = end - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.025))
