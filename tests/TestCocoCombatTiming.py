import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from ok.core.events import communicate
from ok.device.interaction_methods.pynput import PynputInteraction
from src.coco.combat_timing import check_rotation, monitor_rotation, remember_held_input


class TestCocoCombatTiming(unittest.TestCase):
    def setup_combat(self):
        self.foreground = True
        self.key_controller = Mock()
        interaction = object.__new__(PynputInteraction)
        interaction.clickable = lambda: self.foreground
        interaction._key_controller = lambda key: (self.key_controller, key)
        interaction.send_key_up = self.key_controller.release
        task = SimpleNamespace(paused=False, in_liberation=True, in_team=lambda: (True, 1, 2))
        char = SimpleNamespace(task=task, index=0, is_current_char=True, last_perform=0,
                               logger=Mock(), PERFORM_HARD_TIMEOUT=30,
                               time_elapsed_accounting_for_freeze=lambda _start: 45,
                               switch_next_char=Mock())
        other = SimpleNamespace(index=1, is_current_char=False)
        task.chars = [char, other]
        task.executor = SimpleNamespace(interaction=interaction, debug_mode=False, pause_start=None,
                                        blocked_by_pause=lambda: False, exit_event=Event(),
                                        check_enabled=Mock(), next_frame=Mock())
        return task, char, other

    def test_foreground_loss_releases_input_and_refreshes_current_character(self):
        task, char, other = self.setup_combat()
        with monitor_rotation(char):
            remember_held_input(task, 'key', 'e')
            self.foreground = False
            self.assertFalse(task.executor.interaction.should_capture())
            self.key_controller.release.assert_called_once_with('e')
            self.foreground = True
            check_rotation(task)
            self.fail('An interrupted rotation must not continue after the window regains focus')
        self.assertFalse(char.is_current_char)
        self.assertTrue(other.is_current_char)
        self.assertFalse(task.in_liberation)

    def test_single_task_pause_releases_input_and_waits_for_resume(self):
        task, char, _ = self.setup_combat()
        task.executor.check_enabled.side_effect = lambda **_: setattr(task, 'paused', False)
        with monitor_rotation(char):
            remember_held_input(task, 'key', 'e')
            task.paused = True
            communicate.task.emit(task)
            self.key_controller.release.assert_called_once_with('e')
            check_rotation(task)
        self.assertFalse(task.paused)
        task.executor.check_enabled.assert_called_once_with(check_pause=False)
        task.executor.next_frame.assert_called_once()

    def test_hard_timeout_waits_until_liberation_ends(self):
        task, char, _ = self.setup_combat()
        with monitor_rotation(char):
            check_rotation(task)
            char.switch_next_char.assert_not_called()
            task.in_liberation = False
            check_rotation(task)
        char.switch_next_char.assert_called_once()
