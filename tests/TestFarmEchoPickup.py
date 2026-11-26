import unittest
from unittest.mock import Mock, call, patch

from src.combat.CombatCheck import CombatCheck
from src.scene.WWScene import WWScene
from src.task.FarmEchoTask import FarmEchoTask


def make_task(config=None):
    task = FarmEchoTask.__new__(FarmEchoTask)
    task.tr = str
    task.config = config or {}
    task.info = {}
    task.combat_wait_time = 0
    task.bypass_end_wait = True
    task._in_realm = False
    task._has_treasure = False
    task._just_entered_boss_realm = True
    task.is_revived = False
    task.yolo_time_out = 8
    task.yolo_threshold = 0.5
    task.logger = Mock()
    for name in (
        'in_realm', 'manage_boss_parameters', 'init_parameters', 'teleport_to_boss_enabled',
        'teleport_to_configured_boss_and_prepare', 'in_realm_check', 'manage_boss_interactions',
        'in_combat', 'check_boss_name', 'combat_once', 'pick_echo', 'middle_click',
        'yolo_find_echo', 'run_in_circle_to_find_echo', 'walk_find_echo', 'incr_drop',
        'sleep', 'log_info', 'log_debug'
    ):
        setattr(task, name, Mock())
    task.in_realm.return_value = False
    task.teleport_to_boss_enabled.return_value = False
    task.in_combat.return_value = True
    return task


class TestFarmEchoPickup(unittest.TestCase):

    def test_pick_echo_on_face_skips_middle_click(self):
        task = make_task({"Repeat Farm Count": 1})
        task.pick_echo.return_value = True

        task.do_run()

        task.pick_echo.assert_called_once()
        task.middle_click.assert_not_called()
        task.incr_drop.assert_called_once_with(True)

    def test_pick_echo_failure_triggers_middle_click_before_movement(self):
        task = make_task({"Repeat Farm Count": 1, "Echo Pickup Method": "Run in Circle"})
        task.pick_echo.return_value = False
        task.run_in_circle_to_find_echo.return_value = True
        steps = Mock()
        steps.attach_mock(task.middle_click, 'middle_click')
        steps.attach_mock(task.run_in_circle_to_find_echo, 'run_in_circle_to_find_echo')

        task.do_run()

        self.assertEqual(
            [call.middle_click(after_sleep=0.2), call.run_in_circle_to_find_echo(circle_count=2)],
            steps.mock_calls
        )
        task.incr_drop.assert_called_once_with(True)

    def test_dead_lock_does_not_reenter_combat_during_pickup(self):
        task = FarmEchoTask.__new__(FarmEchoTask)
        task._collecting_echo = True
        task.is_boss = Mock(return_value=True)
        task.has_health_bar = Mock(return_value=False)

        with patch.object(CombatCheck, 'has_target', return_value=True), \
                patch('src.task.FarmEchoTask.boss_bar_has_health', return_value=False) as has_sliver:
            self.assertFalse(task.has_target())
            has_sliver.return_value = True
            self.assertTrue(task.has_target())

    def test_echo_end_needs_confirmation_and_live_health_cancels_it(self):
        task = FarmEchoTask.__new__(FarmEchoTask)
        task.combat_end_condition = Mock(return_value=True)
        task.scene = WWScene()
        task.reset_to_false = Mock(return_value=False)
        with patch('src.task.FarmEchoTask.time.monotonic', side_effect=[1.0, 2.0, 2.5]):
            self.assertTrue(task.check_combat_end(False))
            self.assertIsNone(task.check_combat_end(True))
            self.assertTrue(task.check_combat_end(False))
            self.assertFalse(task.check_combat_end(False))

        task.reset_to_false.assert_called_once_with(reason='end condition reached')

    def test_pick_echo_failure_triggers_middle_click_before_yolo(self):
        task = make_task({"Repeat Farm Count": 1, "Echo Pickup Method": "Yolo"})
        task.pick_echo.return_value = False
        task.yolo_find_echo.return_value = (True, False)
        steps = Mock()
        steps.attach_mock(task.middle_click, 'middle_click')
        steps.attach_mock(task.yolo_find_echo, 'yolo_find_echo')

        task.do_run()

        self.assertEqual(
            [
                call.middle_click(after_sleep=0.2),
                call.yolo_find_echo(turn=False, use_color=False, time_out=8, threshold=0.5)
            ],
            steps.mock_calls
        )
        task.incr_drop.assert_called_once_with(True)


if __name__ == '__main__':
    unittest.main()
