"""Persist source preferences independently of team profiles."""

import json
from functools import cache
from importlib import import_module
from pathlib import Path

from ok.util.config import Config

NATIVE = 'native'
COCO = 'coco'


@cache
def source_versions():
    path = Path(__file__).with_name('versions.json')
    return json.loads(path.read_text(encoding='utf-8'))


@cache
def _settings(folder):
    return Config('default_character_sources', {'sources': {}}, folder=folder)


def source_preferences():
    if not (Path(Config.config_folder) / 'default_character_sources.json').is_file():
        return {}
    return _settings(Config.config_folder).get('sources', {})


def set_source(class_name, source):
    settings = _settings(Config.config_folder)
    choices = dict(settings.get('sources', {}))
    if source == COCO and class_name in source_versions()['coco']:
        choices[class_name] = COCO
    else:
        choices.pop(class_name, None)
    settings['sources'] = choices


def set_all_sources(source):
    settings = _settings(Config.config_folder)
    settings['sources'] = {name: COCO for name in source_versions()[COCO]} if source == COCO else {}


@cache
def _coco_class(class_name):
    version = source_versions()['coco'][class_name]
    module = import_module(f"src.coco.characters.{version['module']}")
    return getattr(module, class_name)


def resolve_default_class(native_class, preferences):
    class_name = native_class.__name__
    if preferences.get(class_name) == COCO and class_name in source_versions()['coco']:
        return _coco_class(class_name)
    return native_class
