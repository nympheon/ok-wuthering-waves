"""Application identity for the personal EchoDesk source build."""

import ctypes
import logging
import os
from functools import partial

APP_NAME = 'EchoDesk'
DISPLAY_NAME = '回声 · EchoDesk'
APP_ID = 'Nympheon.EchoDesk'
ORGANIZATION_NAME = 'Nympheon'
LOG_NAME = 'echodesk'


def configure_process_identity():
    import ok
    from ok.util.logger import config_logger

    # The pinned framework resolves this callable before constructing the app.
    ok.config_logger = partial(config_logger, name=LOG_NAME)
    if os.name == 'nt':
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        result = setter(APP_ID)
        if result < 0:
            logging.getLogger(__name__).warning('Could not set application identity: HRESULT %s', result)


def apply_qt_identity():
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance()
    if isinstance(app, QGuiApplication):
        app.setApplicationName(APP_NAME)
        app.setApplicationDisplayName(DISPLAY_NAME)
        app.setOrganizationName(ORGANIZATION_NAME)
        app.setDesktopFileName(APP_ID)
