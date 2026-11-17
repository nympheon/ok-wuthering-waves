import importlib
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QPushButton
from ok import og
from ok.ui.qt.MainWindow import MainWindow

from src.globals import Globals
from src.gui.SourceAboutTab import SourceAboutTab
from src.identity import configure_process_identity


class TestSourceStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_source_startup_installs_page_without_updater_or_links(self):
        about_module = importlib.import_module('ok.ui.qt.about.AboutTab')
        with patch.object(about_module, 'AboutTab'), patch.object(og, 'config', {'gui': {'type': 'qt'}}):
            Globals(None)
            page = about_module.AboutTab({'gui_title': '回声 · EchoDesk'})
            try:
                self.assertIsInstance(page, SourceAboutTab)
                self.assertIsNone(page.update_card)
                self.assertEqual(page.findChildren(QPushButton), [])
                self.assertEqual(self.app.applicationName(), 'EchoDesk')
                self.assertEqual(self.app.applicationDisplayName(), '回声 · EchoDesk')
                self.assertEqual(self.app.organizationName(), 'Nympheon')
                self.assertEqual(self.app.desktopFileName(), 'Nympheon.EchoDesk')
                # The real framework returns before invoking an update check.
                MainWindow._startup_update_check(SimpleNamespace(about_tab=page))
            finally:
                page.deleteLater()

    def test_headless_globals_do_not_install_qt_page(self):
        with patch.object(og, 'config', {'gui': None}), \
                patch('src.gui.SourceAboutTab.install_source_ui') as install:
            Globals(None)
        install.assert_not_called()

    def test_startup_disables_shortcut_creation_and_settings(self):
        global_options = importlib.import_module('ok.util.GlobalConfig')
        shortcut = importlib.import_module('ok.util.shortcut')
        window_module = importlib.import_module('ok.ui.qt.MainWindow')
        from ok.util.config import Config

        with tempfile.TemporaryDirectory() as folder, \
                patch.object(Config, 'config_folder', folder), \
                patch.object(global_options, 'shortcut_supported'), \
                patch('pyappify.create_shortcut', return_value=[]) as create:
            configure_process_identity()
            settings = global_options.GlobalConfig([global_options.create_basic_options()])
            global_options.register_basic_options(settings)
            option = settings.config_options['Basic Options']
            for key in (global_options.CREATE_START_MENU_SHORTCUT, global_options.CREATE_DESKTOP_SHORTCUT):
                self.assertTrue(option.config_type[key]['hidden'])
            enabled_preferences = {
                global_options.CREATE_START_MENU_SHORTCUT: True,
                global_options.CREATE_DESKTOP_SHORTCUT: True,
            }
            for startup in (shortcut.create_app_shortcut, window_module.create_app_shortcut):
                worker = startup(enabled_preferences)
                if worker is not None:
                    worker.join()
            create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
