import unittest
from unittest.mock import Mock, patch

from ok import Box, TaskDisabledException
from src.coco import boss_book, boss_entry
from src.task.FarmEchoTask import FarmEchoTask
from src.task.WWOneTimeTask import WWOneTimeTask


class StaticGameLangFarm(FarmEchoTask):
    game_lang = 'zh_CN'


def make_task(config):
    task = StaticGameLangFarm.__new__(StaticGameLangFarm)
    task.config = config
    task.info = {}
    task.tr = str
    for name in ('ensure_main', 'info_set', 'openF2Book', 'open_boss_book', 'click', 'click_configured_boss_level',
                 'wait_click_travel', 'wait_in_team_and_world', 'sleep'):
        setattr(task, name, Mock())
    return task


class TestFarmEchoTeleport(unittest.TestCase):

    def test_special_nightmare_migrates_the_saved_position_to_a_name(self):
        task = make_task({'Teleport to Boss': 'Special Nightmare', 'Which Special Nightmare to Teleport': 3})
        with patch.object(boss_book, 'open_category') as open_category, \
                patch.object(boss_book, 'click_boss', return_value='梦魇·辉萤军势') as click_boss, \
                patch.object(boss_entry, 'wait_after_book_click', return_value=True), \
                patch.object(boss_entry, 'enter_challenge') as enter:
            self.assertTrue(task.teleport_to_configured_boss())

        open_category.assert_called_once_with(task, 'mengyan')
        click_boss.assert_called_once_with(task, 'mengyan', '梦魇·辉萤军势', 3)
        enter.assert_called_once_with(task)
        self.assertEqual(task.config['Special Nightmare Name'], '梦魇·辉萤军势')

    def test_saved_weekly_display_name_uses_its_realm_title(self):
        task = make_task({'Teleport to Boss': 'Weekly Challenge', 'Weekly Boss Name': '达妮娅（虚妄诞生之种）'})
        with patch.object(boss_book, 'open_category'), patch.object(boss_book, 'click_boss') as click_boss, \
                patch.object(boss_entry, 'wait_after_book_click', return_value=True), \
                patch.object(boss_entry, 'enter_challenge'):
            self.assertTrue(task.teleport_to_configured_boss())

        click_boss.assert_called_once_with(task, 'zhange', '虚妄诞生之种', 1)

    def test_other_game_languages_retain_positional_teleport(self):
        task = make_task({'Teleport to Boss': 'Boss Challenge', 'Which Boss Challenge to Teleport': 3})
        task.game_lang = 'en_US'
        with patch.object(boss_book, 'open_category'), patch.object(boss_book, 'click_boss') as click_boss, \
                patch.object(boss_entry, 'wait_after_book_click', return_value=False):
            self.assertFalse(task.teleport_to_configured_boss())

        click_boss.assert_called_once_with(task, 'qiangdi', '', 3)
        task.wait_click_travel.assert_called_once_with()
        task.wait_in_team_and_world.assert_called_once_with(time_out=120)

    def test_reentry_from_f_uses_retry_after_selecting_level(self):
        task = make_task({})
        task.wait_until = Mock(return_value=True)
        task.send_key = Mock()
        task.init_parameters = Mock()
        with patch.object(boss_entry, 'enter_challenge') as enter:
            task.enter_configured_boss_realm_from_f()
        task.click_configured_boss_level.assert_called_once_with()
        enter.assert_called_once_with(task, level_selected=True)
        self.assertTrue(task._in_realm)

    def test_retry_skips_loading_and_handles_low_waveplate_popup(self):
        task = make_task({})
        now = 1000.0
        state = 'level'
        clicks = []

        def sleep(seconds):
            nonlocal now, state
            now += seconds
            if state == 'loading' and now > 1015:
                state = 'world'

        def click(box, after_sleep):
            nonlocal state
            clicks.append(box.name)
            if clicks == ['Solo Challenge', 'Solo Challenge']:
                state = 'dialog'
            elif box.name == 'Start Challenge':
                state = 'loading'
            sleep(after_sleep)

        def confirm():
            nonlocal state
            if state == 'dialog':
                clicks.append('confirm')
                state = 'team'
                return True
            return False

        labels = {'level': 'Solo Challenge', 'team': 'Start Challenge'}
        task.ocr = lambda *args, **kwargs: [Box(10, 10, 10, 10, name=labels[state])] if state in labels else []
        task.next_frame = Mock()
        task.in_team_and_world = lambda: state == 'world'
        task.click_skip_dialog_confirm = confirm
        task.find_one = Mock(return_value=None)
        task.log_info = Mock()
        task.click_box = click
        task.sleep = sleep

        with patch.object(boss_entry.time, 'monotonic', side_effect=lambda: now):
            boss_entry.enter_challenge(task, time_out=20)

        task.click_configured_boss_level.assert_called_once_with()
        self.assertEqual(clicks, ['Solo Challenge', 'Solo Challenge', 'confirm', 'Start Challenge'])

    def test_stopping_entry_does_not_run_popup_recovery(self):
        task = make_task({})
        task.teleport_to_configured_boss = Mock(side_effect=TaskDisabledException)
        with self.assertRaises(TaskDisabledException):
            task.teleport_to_configured_boss_and_prepare()

    def test_popup_mistaken_for_claim_is_retried_at_most_three_times(self):
        task = make_task({})
        task.do_run = Mock(side_effect=RuntimeError('Teleport to boss failed'))
        task.handle_claim_button = Mock(return_value=True)
        task.handle_monthly_card = Mock(return_value=False)

        with patch.object(WWOneTimeTask, 'run'), self.assertRaises(RuntimeError):
            task.run()

        self.assertEqual(4, task.do_run.call_count)

    def test_farm_continues_after_claim_popup_is_closed(self):
        task = make_task({})
        task.do_run = Mock(side_effect=[RuntimeError('Teleport to boss failed'), None])
        task.handle_claim_button = Mock(return_value=True)
        task.handle_monthly_card = Mock(return_value=False)

        with patch.object(WWOneTimeTask, 'run'):
            task.run()

        self.assertEqual(2, task.do_run.call_count)


if __name__ == '__main__':
    unittest.main()
