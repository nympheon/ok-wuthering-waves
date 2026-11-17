import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QPushButton
from ok import og
from ok.ui.qt.MainWindow import MainWindow

from src.globals import Globals
from src.gui.SourceAboutTab import SourceAboutTab


class TestSourceStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_source_startup_installs_page_without_updater_or_links(self):
        about_module = importlib.import_module('ok.ui.qt.about.AboutTab')
        with patch.object(about_module, 'AboutTab'), patch.object(og, 'config', {'gui': {'type': 'qt'}}):
            Globals(None)
            page = about_module.AboutTab({'gui_title': 'OK-WW'})
            try:
                self.assertIsInstance(page, SourceAboutTab)
                self.assertIsNone(page.update_card)
                self.assertEqual(page.findChildren(QPushButton), [])
                # The real framework returns before invoking an update check.
                MainWindow._startup_update_check(SimpleNamespace(about_tab=page))
            finally:
                page.deleteLater()

    def test_headless_globals_do_not_install_qt_page(self):
        with patch.object(og, 'config', {'gui': None}), \
                patch('src.gui.SourceAboutTab.install_source_ui') as install:
            Globals(None)
        install.assert_not_called()


if __name__ == '__main__':
    unittest.main()
