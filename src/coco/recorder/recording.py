"""Local axis recording format and background media encoding.

Adapted from coco-ww cd8c76e (src/recorder/recorder.py and media.py).
"""

import json
import logging
import queue
import re
import threading
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from time import monotonic

import cv2


RUN_FOLDER = re.compile(r'\d{8}_\d{6}_\d{6}')
MEDIA_FILE = re.compile(r'(?:frame_\d+\.jpg|read_\d+\.png|video\.mp4)')
QUALITY = {'Standard': (960, 82), 'High': (1600, 92), 'Original': (None, 97)}
VIDEO_FPS = 12
logger = logging.getLogger('ok')
_WRITERS_LOCK = threading.Lock()
_WRITING = set()


def run_directory():
    return Path.cwd() / 'logs' / 'axis_runs'


def recordings(root):
    if not root.is_dir():
        return []
    return sorted((path for path in root.iterdir()
                   if RUN_FOLDER.fullmatch(path.name) and not path.is_symlink()
                   and (path / 'events.jsonl').is_file()), reverse=True)


def _prune(root, keep_runs, keep_media):
    for index, folder in enumerate(recordings(root)):
        if index < keep_media or folder in _WRITING or folder.resolve().parent != root.resolve():
            continue
        for path in folder.iterdir():
            if MEDIA_FILE.fullmatch(path.name):
                path.unlink(missing_ok=True)
        if index >= keep_runs:
            (folder / 'events.jsonl').unlink(missing_ok=True)
            try:
                folder.rmdir()
            except OSError:
                # A local recording folder may also contain the user's own files.
                pass


def party_snapshot(task):
    members = []
    for char in getattr(task, 'chars', None) or ():
        if char is None:
            continue
        name = getattr(char, 'display_name', None) or getattr(char, 'name', None) or type(char).__name__
        members.append({'slot': char.index, 'name': str(name), 'class': type(char).__name__,
                        'role': str(getattr(char, 'char_type', '') or ''),
                        'confidence': round(float(getattr(char, 'confidence', 0) or 0), 3)})
    return members


def _game_frame(image):
    # ok-script frames are BGR; a few Windows capture paths expose BGRA.
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def _fit_width(image, width, even=False):
    height, original_width = image.shape[:2]
    width = min(width, original_width) if width else original_width
    height = max(1, round(height * width / original_width))
    if even:
        width, height = width - width % 2, height - height % 2
    if image.shape[:2] == (height, width):
        return image
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


class Recording:
    def __init__(self, root, task, scheduled_task, mode, settings):
        self.root = root
        self.task = task
        self.scheduled_task = scheduled_task
        self.mode = mode
        self.settings = settings
        self.thread_id = threading.get_ident()
        wall = datetime.now().astimezone()
        self.path = root / wall.strftime('%Y%m%d_%H%M%S_%f')
        self.started = monotonic()
        task_name = 'Manual combat' if mode == 'Manual' else task.name
        self.header = {'kind': 'start', 't': 0, 'format': 1, 'date': wall.isoformat(),
                       'mode': mode, 'task': task_name, 'team': party_snapshot(task),
                       'media': settings['media'], 'quality': settings['quality']}
        self.events = deque(maxlen=4000)
        self.recent_logs = deque(maxlen=60)
        self.recent_field = deque(maxlen=120)
        self.field_changes = []
        self.field_times = Counter()
        self.switch_starts = {}
        self.switch_delays = deque(maxlen=20)
        self.counts = Counter()
        self.reads = {}
        self.slot = None
        self.slot_since = 0.0
        self.last_slot = None
        self.last_frame_at = -1.0
        self.pending_frames = threading.BoundedSemaphore(4)
        self.messages = queue.SimpleQueue()
        self.ending = None
        self.error = None
        self.worker = threading.Thread(target=self._write, name='AxisRecording', daemon=True)

    def elapsed(self, now=None):
        return round(max(0.0, (monotonic() if now is None else now) - self.started), 3)

    def add(self, kind, when=None, **fields):
        event = {'kind': kind, 't': self.elapsed(when), **fields}
        self.events.append(event)
        if kind == 'log':
            self.recent_logs.append(event)
        elif kind == 'input' and fields['action'] in ('key', 'key down') and fields['key'] in ('1', '2', '3'):
            self.switch_starts[int(fields['key']) - 1] = event['t']
        self.counts[kind] += 1
        self.messages.put((event, None))
        return event

    def field(self, slot):
        if self.slot == slot and self.counts['field']:
            return
        event = self.add('field', slot=slot)
        self.recent_field.append((event['t'], slot))
        if self.slot is not None:
            self.field_times[self.slot] += event['t'] - self.slot_since
        self.slot = slot
        self.slot_since = event['t']
        if slot is not None and self.last_slot != slot:
            self.last_slot = slot
            self.field_changes.append((event['t'], slot))
            if (started := self.switch_starts.pop(slot, None)) is not None:
                delay = event['t'] - started
                if 0 <= delay <= 3:
                    self.switch_delays.append(delay)

    def frame(self, frame):
        media = self.settings['media']
        if media == 'Off' or frame is None or not frame.size:
            return
        now = monotonic()
        interval = 1 / VIDEO_FPS if media == 'Video' else 0.25
        if now - self.last_frame_at < interval:
            return
        if not self.pending_frames.acquire(blocking=False):
            self.counts['dropped frames'] += 1
            return
        self.last_frame_at = now
        self.messages.put(({'kind': 'frame', 't': self.elapsed(now)}, frame.copy()))

    def read(self, fields, frame):
        name = (fields['reader'], fields['label'], fields.get('source'))
        data = fields.get('value'), fields.get('boxes')
        now = monotonic()
        previous = self.reads.get(name)
        if previous and previous[0] == data and now - previous[1] < 1:
            return
        self.reads[name] = (data, now)
        if not self.settings['crops'] or frame is None or not frame.size or not fields.get('region'):
            self.add('read', now, **fields)
            return
        x, y, width, height = fields['region']
        top, left = max(0, y), max(0, x)
        crop = frame[top:y + height, left:x + width] if y + height > top and x + width > left else None
        if crop is None or not crop.size or not self.pending_frames.acquire(blocking=False):
            self.add('read', now, **fields)
            return
        event = {'kind': 'read', 't': self.elapsed(now), **fields,
                 'crop': f"read_{self.counts['read']:06d}.png"}
        self.events.append(event)
        self.counts['read'] += 1
        self.messages.put((event, crop.copy()))

    def close(self, reason):
        self.ending = {'kind': 'end', 't': self.elapsed(), 'reason': reason,
                       'dropped_frames': self.counts['dropped frames']}
        self.messages.put((self.ending, None))

    def snapshot(self):
        elapsed = self.ending['t'] if self.ending else self.elapsed()
        times = dict(self.field_times)
        if self.slot is not None:
            times[self.slot] = times.get(self.slot, 0.0) + elapsed - self.slot_since
        return {'header': self.header, 'path': self.path, 'elapsed': elapsed, 'active': self.slot,
                'field_times': times, 'switches': tuple(self.field_changes), 'field': tuple(self.recent_field),
                'counts': dict(self.counts), 'switch_delays': tuple(self.switch_delays),
                'end': self.ending, 'events': tuple(self.events), 'logs': tuple(self.recent_logs), 'error': self.error}

    @staticmethod
    def _json_line(handle, event):
        handle.write(json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n')

    def _write(self):
        video = None
        frame_index = 0
        size = None
        video_requested = self.settings['media'] == 'Video'
        width, quality = QUALITY[self.settings['quality']]
        with _WRITERS_LOCK:
            _WRITING.add(self.path)
        try:
            self.path.mkdir(parents=True)
            with (self.path / 'events.jsonl').open('x', encoding='utf-8', buffering=1) as handle:
                self._json_line(handle, self.header)
                while True:
                    event, image = self.messages.get()
                    if image is not None:
                        try:
                            if event['kind'] == 'frame':
                                source_height, source_width = image.shape[:2]
                                image = _fit_width(_game_frame(image), width, even=video_requested)
                                if video_requested and video is None:
                                    size = image.shape[1], image.shape[0]
                                    video = cv2.VideoWriter(str(self.path / 'video.mp4'),
                                                            cv2.VideoWriter_fourcc(*'mp4v'), VIDEO_FPS, size)
                                    if not video.isOpened():
                                        video.release()
                                        video = None
                                        video_requested = False
                                        self._json_line(handle, {'kind': 'note', 't': event['t'],
                                                                 'message': 'Video encoder unavailable. Saving images instead.'})
                                if video is not None:
                                    if image.shape[1::-1] != size:
                                        image = cv2.resize(image, size)
                                    video.write(image)
                                    event['index'] = frame_index
                                else:
                                    filename = f'frame_{frame_index:06d}.jpg'
                                    self._write_image(filename, image, [cv2.IMWRITE_JPEG_QUALITY, quality])
                                    event['file'] = filename
                                event['source'] = [source_width, source_height]
                                frame_index += 1
                            else:
                                self._write_image(event['crop'], _game_frame(image), [cv2.IMWRITE_PNG_COMPRESSION, 2])
                        except (cv2.error, OSError, ValueError) as error:
                            event = {key: value for key, value in event.items() if key != 'crop'}
                            self._json_line(handle, {'kind': 'note', 't': event['t'], 'message': str(error)})
                            if event['kind'] == 'frame':
                                continue
                        finally:
                            self.pending_frames.release()
                    ending = event['kind'] == 'end'
                    if ending and video is not None:
                        video.release()
                        video = None
                    self._json_line(handle, event)
                    if ending:
                        break
        except (OSError, ValueError) as error:
            self.error = str(error)
            logger.error('Axis recording could not be written: %s', error)
        finally:
            if video is not None:
                video.release()
            with _WRITERS_LOCK:
                _WRITING.discard(self.path)
                if self.ending and not self.error:
                    try:
                        _prune(self.root, self.settings['keep'], self.settings['keep_media'])
                    except OSError as error:
                        logger.warning('Could not clean up old axis recordings: %s', error)

    def _write_image(self, filename, image, parameters):
        ok, encoded = cv2.imencode(Path(filename).suffix, image, parameters)
        if not ok:
            raise ValueError(f'Could not encode {filename}')
        (self.path / filename).write_bytes(encoded.tobytes())


class LogTap(logging.Handler):
    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

    def emit(self, record):
        run = self.recorder.run
        if run and run.thread_id == record.thread and run.settings['logs']:
            try:
                self.recorder.event(run, 'log', level=record.levelname, message=record.getMessage())
            except (TypeError, ValueError):
                self.handleError(record)


class Recorder:
    def __init__(self, owner, root=None):
        self.owner = owner
        self.executor = owner.executor
        self.root = root if root is not None else run_directory()
        self.lock = threading.RLock()
        self.run = None
        self.last = None
        self.workers = []
        self.log_tap = LogTap(self)

    def start(self, task, mode):
        with self.lock:
            if self.run is not None or not self.owner.enabled:
                return self.run
            scheduled_task = getattr(self.executor, 'current_task', None) or task
            run = Recording(self.root, task, scheduled_task, mode, self.owner.recording_settings())
            self.workers = [thread for thread in self.workers if thread.is_alive()]
            self.workers.append(run.worker)
            self.run = run
            self.executor._axis_recording = self
            if run.settings['logs']:
                logger.addHandler(self.log_tap)
            run.worker.start()
            return run

    def stop(self, reason, expected=None):
        with self.lock:
            run = self.run
            if run is None or expected is not None and expected is not run:
                return
            run.close(reason)
            logger.removeHandler(self.log_tap)
            self.last, self.run = run, None
            if getattr(self.executor, '_axis_recording', None) is self:
                self.executor._axis_recording = None

    def frame(self, run, frame):
        with self.lock:
            if run is self.run and not run.error:
                run.frame(frame)

    def event(self, run, kind, when=None, **fields):
        with self.lock:
            if run is self.run and not run.error:
                run.add(kind, when, **fields)

    def field(self, run, slot):
        with self.lock:
            if run is self.run and not run.error:
                run.field(slot)

    def read(self, run, fields, frame):
        with self.lock:
            if run is self.run and not run.error:
                run.read(fields, frame)

    def snapshot(self):
        with self.lock:
            run = self.run or self.last
            return run.snapshot() if run is not None else None

    def shutdown(self):
        self.stop('Application closed')
        deadline = monotonic() + 2
        for thread in self.workers:
            thread.join(timeout=max(0.0, deadline - monotonic()))
