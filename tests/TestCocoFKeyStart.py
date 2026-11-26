import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok import Box
from src.coco.f_key_start import FKeyStart, FStartCombatTask, INJECTED, KEY_DOWN, KEY_UP, VK_F


class TestCocoFKeyStart(unittest.TestCase):
    def setUp(self):
        self.task = Mock(config={'Auto Target': True}, f_start_enabled=True, f_start_delay=0.5, f_grace_limit=2.0)
        self.task.find_f_with_text.return_value = None
        self.task.is_browser.return_value = False
        self.watcher = FKeyStart(self.task)
        self.watcher._game_in_foreground = Mock(return_value=True)
        self.watcher.listen = Mock()
        self.now = 123.0
        clock = patch('src.coco.f_key_start.time.monotonic', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def press(self, flags=0, message=KEY_DOWN[0]):
        self.watcher._on_key_event(message, SimpleNamespace(vkCode=VK_F, flags=flags))

    def test_physical_press_starts_once_after_delay_and_holds_until_timeout(self):
        self.assertFalse(self.watcher.should_start())
        self.press()
        self.now += 0.25
        self.press()  # physical key repeat
        self.assertFalse(self.watcher.should_start())
        self.now += 0.25
        self.assertTrue(self.watcher.should_start())
        self.assertFalse(self.watcher.should_start())

        self.assertTrue(self.watcher.hold_without_target())
        self.task.middle_click.assert_called_once_with(interval=0.3)
        self.now += 2
        self.assertFalse(self.watcher.hold_without_target())

    def test_injected_unfocused_disabled_and_open_world_f_do_not_start(self):
        self.watcher.armed = True
        self.press(flags=INJECTED)
        self.watcher._game_in_foreground.return_value = False
        self.press()
        self.press(message=KEY_UP[0])
        self.watcher._game_in_foreground.return_value = True
        self.task.f_start_enabled = False
        self.press()
        self.press(message=KEY_UP[0])
        self.assertEqual(self.watcher.last_press, float('-inf'))

        self.task.f_start_enabled = True
        self.task.in_realm.return_value = False
        self.assertFalse(self.watcher.should_start())
        self.press()
        self.assertEqual(self.watcher.last_press, float('-inf'))

    def test_absorb_prompt_blocks_press_even_after_prompt_disappears(self):
        self.task.find_f_with_text.return_value = Box(100, 50, 10, 10, name='F')
        self.task.ocr.return_value = [Box(160, 50, 30, 14, name='吸收')]
        self.assertFalse(self.watcher.should_start())
        self.press()
        self.now += 0.7
        self.task.find_f_with_text.return_value = None

        self.assertFalse(self.watcher.should_start())
        self.task.load_chars.assert_not_called()

    def test_legacy_team_shortcut_is_disabled_during_injected_f(self):
        self.task._f_key_start = self.watcher
        adapter = FStartCombatTask.__new__(FStartCombatTask)
        adapter._auto_combat = lambda: self.task
        self.assertTrue(adapter.enabled)
        self.press(flags=INJECTED)
        self.assertFalse(adapter.enabled)
        self.press(flags=INJECTED, message=KEY_UP[0])
        self.assertFalse(adapter.enabled)
        self.now += 0.25
        self.assertTrue(adapter.enabled)


if __name__ == '__main__':
    unittest.main()
