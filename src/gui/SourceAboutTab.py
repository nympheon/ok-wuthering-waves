"""The local source build has no distribution or application-update interface."""

from importlib import import_module

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SourceAboutTab(QWidget):
    update_card = None

    def __init__(self, config, exit_event=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 32)
        layout.addWidget(QLabel(config.get('gui_title', 'OK-WW'), self))
        layout.addWidget(QLabel('个人源码版', self))
        layout.addStretch(1)


def install_source_ui():
    # ok-script 3.0.5b9 imports this page inside MainWindow.__init__.
    # Replacing that factory avoids constructing its updater or starting checks.
    about_module = import_module('ok.ui.qt.about.AboutTab')
    about_module.AboutTab = SourceAboutTab
