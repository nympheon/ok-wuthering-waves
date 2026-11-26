"""Observe EchoDesk's installed ok-script runtime for the axis recorder.

The hook points follow coco-ww cd8c76e (src/recorder/recorder.py).
"""

import functools
import inspect
import logging
import os
import sys
import threading
from time import monotonic


_LOCAL = threading.local()
_LOCK = threading.Lock()
_HOOKS_INSTALLED = False
_INTERACTION_METHODS = {
    'send_key': 'key', 'send_key_down': 'key down', 'send_key_up': 'key up',
    'click': 'click', 'middle_click': 'click', 'right_click': 'click',
    'mouse_down': 'mouse down', 'mouse_up': 'mouse up', 'scroll': 'scroll',
}
log = logging.getLogger(__name__)


def recorder_for(executor):
    for candidate in getattr(executor, 'trigger_tasks', ()):
        if type(candidate).__name__ == 'AxisRecorderTask':
            return candidate.recorder
    return None


def _capture(executor, task=None):
    recorder = getattr(executor, '_axis_recording', None)
    run = recorder.run if recorder else None
    if (run is None or not recorder.owner.enabled
            or task is not None and run.task is not task):
        return None, None
    return recorder, run


def _source():
    frame = sys._getframe(2)
    while frame:
        file = frame.f_code.co_filename.replace('\\', '/')
        if any(part in file for part in ('/src/char/', '/src/task/', '/src/combat/', '/custom_chars/')):
            return f'{os.path.basename(file)}:{frame.f_lineno} {frame.f_code.co_name}'
        frame = frame.f_back
    return ''


def _read_call(kind, original):
    signature = inspect.signature(original)

    @functools.wraps(original)
    def observe(task, *args, **kwargs):
        result = original(task, *args, **kwargs)
        recorder, run = _capture(task.executor, task)
        if run is not None and run.settings['reads'] and task.executor.is_executor_thread():
            try:
                params = signature.bind_partial(task, *args, **kwargs).arguments
                details, frame = _recognition(task, kind, params, result)
                recorder.read(run, details, frame)
            except Exception:
                _log_error_once('recognition')
        return result

    return observe


def _rectangle(box):
    if hasattr(box, 'width'):
        return [int(value) for value in (box.x, box.y, box.width, box.height)]
    return None


def _recognition(task, kind, params, result):
    frame = params.get('frame')
    if frame is None:
        frame = getattr(task.executor, '_frame', None)
    box = params.get('box')
    label = (params.get('feature_name') or params.get('box_name') or params.get('to_find')
             or params.get('name') or getattr(box, 'name', None) or params.get('match') or kind)
    if isinstance(label, (tuple, list)):
        label = ', '.join(map(str, label))
    label = str(label)
    hits = result if isinstance(result, (list, tuple)) else [result]
    boxes = []
    for hit in hits:
        if rect := _rectangle(hit):
            boxes.append({'name': str(hit.name or ''), 'rect': rect,
                          'confidence': round(float(hit.confidence), 3)})
    if boxes:
        value = ', '.join(hit['name'] or label for hit in boxes)
    elif kind in ('OCR', 'Template'):
        value = None
    elif hasattr(result, '__float__'):
        value = round(float(result), 3)
    else:
        value = str(result)
    region = _rectangle(box)
    if region is None and boxes:
        region = boxes[0]['rect']
    source_size = list(frame.shape[1::-1]) if frame is not None else None
    return {'reader': kind, 'label': label, 'value': value, 'boxes': boxes, 'region': region,
            'frame_size': source_size, 'source': _source()}, frame


def _combat_check(original):
    @functools.wraps(original)
    def observe(task, *args, **kwargs):
        result = original(task, *args, **kwargs)
        if result:
            _safely(_observe_combat, task)
        return result

    return observe


def _observe_combat(task):
    executor = task.executor
    if executor is None or not executor.is_executor_thread() or executor.current_task is None:
        return
    recorder = recorder_for(executor)
    if recorder is None or not recorder.owner.accepts_automatic(task) or recorder.run:
        return
    interaction = executor.interaction
    if interaction is not None:
        _observe_interaction_class(type(interaction))
    run = recorder.start(task, 'Automatic')
    if run is None:
        return
    _LOCAL.input_recorder = recorder
    for member in task.chars:
        if member is not None and member.is_current_char:
            recorder.field(run, member.index)
            break
    recorder.frame(run, getattr(executor, '_frame', None))


def _combat_end(original):
    @functools.wraps(original)
    def observe(task, *args, **kwargs):
        try:
            return original(task, *args, **kwargs)
        finally:
            recorder, run = _capture(task.executor, task)
            if run is not None and run.mode == 'Automatic':
                reason = getattr(task, 'out_of_combat_reason', None) or 'Combat ended'
                _safely(recorder.stop, str(reason), run)

    return observe


def _field_read(original):
    @functools.wraps(original)
    def observe(task, *args, **kwargs):
        result = original(task, *args, **kwargs)
        recorder, run = _capture(task.executor, task)
        if run is not None and result is not None and task.executor.is_executor_thread():
            shown, slot, _ = result
            _safely(recorder.field, run, slot if shown and slot >= 0 else None)
        return result

    return observe


def _perform(original):
    @functools.wraps(original)
    def observe(char, *args, **kwargs):
        recorder, run = _capture(char.task.executor, char.task)
        if run is None or run.mode != 'Automatic':
            return original(char, *args, **kwargs)
        _safely(recorder.event, run, 'action', slot=char.index, action='start')
        try:
            return original(char, *args, **kwargs)
        finally:
            _safely(recorder.event, run, 'action', slot=char.index, action='end')

    return observe


def _frame(original):
    @functools.wraps(original)
    def observe(executor, *args, **kwargs):
        image = original(executor, *args, **kwargs)
        recorder, run = _capture(executor)
        if run is not None and image is not None and executor.is_executor_thread():
            if run.mode == 'Automatic' and executor.current_task is run.scheduled_task:
                if recorder.owner.manual_mode:
                    _safely(recorder.stop, 'Recording mode changed', run)
                else:
                    _safely(recorder.frame, run, image)
            elif run.mode == 'Manual' and executor.current_task is recorder.owner:
                if recorder.owner.manual.foreground():
                    _safely(recorder.frame, run, image)
        return image

    return observe


def _finish_task(original):
    @functools.wraps(original)
    def observe(executor, task, is_trigger_task):
        try:
            return original(executor, task, is_trigger_task)
        finally:
            recorder, run = _capture(executor)
            if run is not None and (run.mode == 'Automatic' and run.scheduled_task is task
                                    or run.mode == 'Manual' and not is_trigger_task):
                _safely(recorder.stop, 'Task ended', run)

    return observe


def _pause(original):
    @functools.wraps(original)
    def observe(executor, *args, **kwargs):
        result = original(executor, *args, **kwargs)
        recorder, run = _capture(executor)
        if recorder is not None and executor.paused:
            _safely(recorder.stop, 'Executor paused', run)
        return result

    return observe


def note_automation_input(task, action, key, **fields):
    recorder, run = _capture(task.executor, task)
    if run is not None and run.mode == 'Automatic' and task.executor.is_executor_thread():
        _safely(recorder.event, run, 'input', action=action, key=str(key), source=_source(), **fields)


def _observe_interaction_class(cls):
    with _LOCK:
        for parent in cls.__mro__:
            for method, action in _INTERACTION_METHODS.items():
                original = vars(parent).get(method)
                if callable(original) and not getattr(original, '_axis_input_observer', False):
                    setattr(parent, method, _input_call(method, action, original))


def _input_call(method, action, original):
    signature = inspect.signature(original)

    @functools.wraps(original)
    def observe(interaction, *args, **kwargs):
        recorder = getattr(_LOCAL, 'input_recorder', None)
        run = recorder.run if recorder else None
        if (run is None or run.mode != 'Automatic' or recorder.executor.current_task is not run.scheduled_task
                or recorder.executor.interaction is not interaction or getattr(_LOCAL, 'input_depth', 0)):
            return original(interaction, *args, **kwargs)
        sent_at = monotonic()
        _LOCAL.input_depth = 1
        try:
            result = original(interaction, *args, **kwargs)
        finally:
            _LOCAL.input_depth = 0
        if result is not False:
            try:
                params = signature.bind(interaction, *args, **kwargs)
                params.apply_defaults()
                values = params.arguments
                extras = values.get('kwargs', {})
                button = {'middle_click': 'middle', 'right_click': 'right'}.get(method)
                key = button or values.get('key') or extras.get('key') or ('left' if action == 'click' else method)
                point = (values.get('x'), values.get('y'))
                details = {'action': action, 'key': str(key), 'source': _source()}
                if all(isinstance(value, (float, int)) for value in point):
                    details['point'] = point
                duration = values.get('down_time', extras.get('down_time'))
                if isinstance(duration, (float, int)):
                    details['duration'] = duration
                recorder.event(run, 'input', sent_at, **details)
            except Exception:
                _log_error_once('input')
        return result

    observe._axis_input_observer = True
    return observe


def _log_error_once(name):
    if not getattr(_LOCAL, f'{name}_reported', False):
        setattr(_LOCAL, f'{name}_reported', True)
        log.exception('Axis recorder failed to observe %s', name)


def _safely(callback, *args, **kwargs):
    try:
        callback(*args, **kwargs)
    except Exception:
        _log_error_once(callback.__name__)


def install_hooks():
    global _HOOKS_INSTALLED
    with _LOCK:
        if _HOOKS_INSTALLED:
            return
        from ok.task.TaskExecutor import TaskExecutor
        from ok.task.task import ExecutorOperation, FindFeature, OCR
        from src.char.BaseChar import BaseChar
        from src.combat.CombatCheck import CombatCheck
        from src.task.BaseCombatTask import BaseCombatTask
        from src.task.BaseWWTask import BaseWWTask

        for owner, name, wrap in (
            (CombatCheck, 'in_combat', _combat_check),
            (CombatCheck, 'reset_to_false', _combat_end),
            (BaseCombatTask, 'combat_end', _combat_end),
            (BaseChar, 'perform', _perform),
            (BaseWWTask, 'in_team', _field_read),
            (TaskExecutor, 'next_frame', _frame),
            (TaskExecutor, '_finish_task', _finish_task),
            (TaskExecutor, 'pause', _pause),
        ):
            setattr(owner, name, wrap(getattr(owner, name)))
        for owner, name, kind in (
            (FindFeature, 'find_feature', 'Template'),
            (FindFeature, 'find_best_match_in_box', 'Template'),
            (FindFeature, 'find_first_match_in_box', 'Template'),
            (OCR, 'ocr', 'OCR'),
            (ExecutorOperation, 'calculate_color_percentage', 'Color'),
            (BaseCombatTask, 'get_cd', 'Cooldown'),
            (BaseCombatTask, 'get_current_con', 'Concerto'),
        ):
            setattr(owner, name, _read_call(kind, getattr(owner, name)))
        _HOOKS_INSTALLED = True
