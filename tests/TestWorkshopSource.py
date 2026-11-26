import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ok.util.config import Config
from src.char.WorkshopSource import DEFAULT_BASE_URL, archive_url, index_url, load_settings, repository_url, save_settings


class TestWorkshopSource(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder_patch = patch.object(Config, 'config_folder', self.temp.name)
        self.folder_patch.start()

    def tearDown(self):
        self.folder_patch.stop()
        self.temp.cleanup()

    def test_default_source_uses_coco_repository(self):
        self.assertEqual(index_url(),
                         'https://raw.githubusercontent.com/wk321425/coco-ww-char-code/main/teams.json')
        self.assertEqual(repository_url(), 'https://github.com/wk321425/coco-ww-char-code')

    def test_saved_source_is_used_by_fresh_load_and_team_requests(self):
        save_settings({'base_url': ' https://example.org/my/library/ ', 'download_dir': 'saved'})
        settings = load_settings()
        self.assertEqual(settings['base_url'], 'https://example.org/my/library')
        self.assertEqual(settings['download_dir'], 'saved')
        self.assertEqual(index_url('teams/A_B_C.json'), 'https://example.org/my/library/teams/A_B_C.json')

    def test_invalid_save_preserves_previous_source(self):
        save_settings({'base_url': 'https://example.org/working'})
        for value in ('http://example.org', 'https://user:password@example.org',
                      'https://example.org/?query=1', '', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                save_settings({'base_url': value})
        self.assertEqual(index_url(), 'https://example.org/working/teams.json')

    def test_failed_atomic_replace_preserves_saved_source(self):
        save_settings({'base_url': 'https://example.org/working'})
        with patch('src.char.WorkshopSource.os.replace', side_effect=OSError('read only')):
            with self.assertRaises(OSError):
                save_settings({'base_url': 'https://example.org/new'})
        self.assertEqual(index_url(), 'https://example.org/working/teams.json')
        self.assertEqual(list(Path(self.temp.name).glob('*.tmp')), [])

    def test_corrupt_settings_fall_back_without_overwriting_file(self):
        path = Path(self.temp.name) / 'code_fetch.json'
        path.write_text('{broken', encoding='utf-8')
        self.assertEqual(index_url(), f'{DEFAULT_BASE_URL}/teams.json')
        self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_existing_plugin_settings_remain_compatible(self):
        path = Path(self.temp.name) / 'code_fetch.json'
        path.write_text(json.dumps({'base_url': 'https://example.org/repo',
                                    'extra_archive_hosts': [' CDN.Example.org ']}), encoding='utf-8-sig')
        self.assertEqual(archive_url('https://cdn.example.org/team.zip'), 'https://cdn.example.org/team.zip')

    def test_archive_sources_allow_release_and_relative_links(self):
        for value, expected in (
            ('https://github.com/example/workshop/releases/download/1/team.zip',
             'https://github.com/example/workshop/releases/download/1/team.zip'),
            ('codes/team.zip', f'{DEFAULT_BASE_URL}/codes/team.zip'),
            ('https://cfokwwchar.ok-script.com/codes/team.zip',
             f'{DEFAULT_BASE_URL}/codes/team.zip'),
        ):
            with self.subTest(value=value):
                self.assertEqual(archive_url(value), expected)

    def test_unconfigured_archive_host_and_credentials_are_rejected(self):
        for value in ('https://unrelated.example/team.zip', 'http://github.com/team.zip',
                      'https://user:password@github.com/team.zip', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                archive_url(value)

    def test_repository_link_follows_saved_pages_source(self):
        save_settings({'base_url': 'https://another.github.io/custom-workshop/'})
        self.assertEqual(repository_url(), 'https://github.com/another/custom-workshop')


if __name__ == '__main__':
    unittest.main()
