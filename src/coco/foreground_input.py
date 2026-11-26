"""Optional Windows SendInput backend. Normal input stays scoped to the game window."""

import ctypes
import time
from ctypes import wintypes
from threading import RLock
from weakref import WeakSet

from ok import Logger
from ok.core.events import communicate
from ok.device.interaction_methods.base import BaseInteraction
from ok.device.interaction_methods.keys import get_mouse_button, is_mouse_button, vk_key_dict

logger = Logger.get_logger(__name__)


class _KeyboardInput(ctypes.Structure):
    _fields_ = [('vk', wintypes.WORD), ('scan', wintypes.WORD), ('flags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]


class _MouseInput(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('data', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]


class _Payload(ctypes.Union):
    _fields_ = [('keyboard', _KeyboardInput), ('mouse', _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('payload', _Payload)]


_user32 = ctypes.WinDLL('user32', use_last_error=True)
_send_input = _user32.SendInput
_send_input.argtypes = (wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int)
_send_input.restype = wintypes.UINT
_mouse_flags = {
    'left': (0x0002, 0x0004),
    'right': (0x0008, 0x0010),
    'middle': (0x0020, 0x0040),
}
_active_backends = WeakSet()


def _release_on_pause(paused):
    if paused:
        for backend in list(_active_backends):
            backend.release_all()


communicate.executor_paused.connect(_release_on_pause)


def _keyboard(key, up):
    flags = 0x0002 if up else 0
    name = str(key).upper()
    vk = vk_key_dict.get(name)
    if vk is None and len(name) == 1:
        value = _user32.VkKeyScanW(ord(name)) & 0xffff
        if value != 0xffff:
            vk = value & 0xff
    if vk is None:
        raise ValueError(f'Unknown SendInput key: {key}')
    scan = _user32.MapVirtualKeyW(vk, 4)
    if scan and scan >> 8 in (0, 0xe0):
        flags |= 0x0008 | (0x0001 if scan >> 8 else 0)
        vk = 0
    return _Input(1, _Payload(keyboard=_KeyboardInput(vk, scan & 0xff, flags, 0, 0)))


def _mouse(key, up):
    key = key.lower()
    if is_mouse_button(key):
        flags = 0x0100 if up else 0x0080
        data = get_mouse_button(key)
    else:
        flags = _mouse_flags[key][int(up)]
        data = 0
    return _Input(0, _Payload(mouse=_MouseInput(0, 0, data, flags, 0, 0)))


def _send(packet):
    if _send_input(1, ctypes.byref(packet), ctypes.sizeof(_Input)) != 1:
        logger.warning(f'SendInput 发送失败，Windows 错误 {ctypes.get_last_error()}')
        return False
    return True


class SendInput(BaseInteraction):
    def __init__(self, capture, hwnd_window):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self._held = {}
        self._input_lock = RLock()
        _active_backends.add(self)

    def clickable(self):
        return self.hwnd_window.is_foreground()

    def should_capture(self):
        if self.clickable():
            return True
        self.release_all()
        return False

    def on_run(self):
        self.hwnd_window.bring_to_front()

    def on_destroy(self):
        self.release_all()
        _active_backends.discard(self)

    def _press(self, token, make_packet):
        with self._input_lock:
            if self.clickable() and _send(make_packet(token[1], False)):
                self._held[token] = make_packet(token[1], True)
                return True
        return False

    def _release(self, token):
        with self._input_lock:
            release = self._held.get(token)
            if release is not None and _send(release):
                self._held.pop(token)

    def release_all(self):
        with self._input_lock:
            for token in list(self._held):
                self._release(token)

    def send_key_down(self, key):
        key = str(key).lower()
        if is_mouse_button(key):
            return self.mouse_down(key=key)
        return self._press(('key', key), _keyboard)

    def send_key_up(self, key):
        key = str(key).lower()
        if is_mouse_button(key):
            return self.mouse_up(key=key)
        self._release(('key', key))

    def send_key(self, key, down_time=0.01):
        if self.send_key_down(key):
            try:
                time.sleep(max(0.0, down_time))
            finally:
                self.send_key_up(key)

    def mouse_down(self, x=-1, y=-1, name=None, key='left'):
        if self.clickable() and x != -1 and y != -1:
            self.move(x, y)
        return self._press(('mouse', key.lower()), _mouse)

    def mouse_up(self, key='left'):
        self._release(('mouse', key.lower()))

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=False, key='left'):
        from pynput.mouse import Controller

        if not self.clickable():
            return
        BaseInteraction.click(self, x, y, name=name)
        if move_back:
            cursor = Controller()
            previous = cursor.position
        try:
            if self.mouse_down(x, y, name=name, key=key):
                try:
                    time.sleep(max(0.0, down_time))
                finally:
                    self.mouse_up(key=key)
        finally:
            if move_back and self.clickable():
                cursor.position = previous

    def move(self, x, y):
        from pynput.mouse import Controller

        if self.clickable():
            Controller().position = self.capture.get_abs_cords(x, y)

    def scroll(self, x, y, scroll_amount):
        from pynput.mouse import Controller

        self.move(x, y)
        mouse = Controller()
        direction = 1 if scroll_amount > 0 else -1
        for _ in range(abs(int(scroll_amount))):
            if not self.clickable():
                return
            mouse.scroll(0, direction)
            time.sleep(0.001)

    def swipe(self, x1, y1, x2, y2, duration, settle_time=0):
        if not self.mouse_down(x1, y1):
            return
        steps = max(int(duration / 10), 1)
        try:
            for step in range(1, steps + 1):
                if not self.clickable() or ('mouse', 'left') not in self._held:
                    return
                self.move(x1 + (x2 - x1) * step / steps, y1 + (y2 - y1) * step / steps)
                time.sleep(max(0, duration) / steps / 1000)
            if settle_time and self.clickable():
                time.sleep(settle_time)
        finally:
            self.mouse_up()
