import re
from functools import cache
from pathlib import Path

from PySide6.QtGui import QPixmap

from src.char.CharFactory import char_dict


@cache
def _templates_by_label():
    folder = Path(__file__).resolve().parents[3] / 'assets' / 'templates'
    paths = {}
    for path in sorted(folder.glob('*.png')):
        match = re.match(r'(.+?)_\d+x\d+_', path.stem)
        if match:
            paths.setdefault(match[1], path)
    return paths


def character_portrait(class_name: str) -> QPixmap:
    for label, info in char_dict.items():
        if info['cls'].__name__ == class_name:
            path = _templates_by_label().get(getattr(label, 'value', label))
            if path is not None:
                return QPixmap(str(path))
    return QPixmap()
