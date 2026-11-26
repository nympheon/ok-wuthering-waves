"""Read EchoDesk's local axis recordings for replay and inspection."""

import json
import math
import re
from bisect import bisect_right

import cv2
import numpy as np


FRAME_NAME = re.compile(r'frame_\d+\.jpg')
CROP_NAME = re.compile(r'read_\d+\.png')


def read_recording(folder):
    header, end, events = {}, None, []
    with (folder / 'events.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict) or not isinstance(event.get('t'), (int, float)):
                continue
            if not math.isfinite(event['t']) or event['t'] < 0:
                continue
            if event.get('kind') == 'start':
                header = event
            elif event.get('kind') == 'end':
                end = event
            else:
                events.append(event)
    events.sort(key=lambda event: event['t'])
    return header, end, events


def local_image(folder, name, pattern):
    if not name or not pattern.fullmatch(name):
        return None
    file = folder / name
    if not file.is_file() or file.is_symlink():
        return None
    try:
        return cv2.imdecode(np.frombuffer(file.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    except (OSError, cv2.error):
        return None


class ReplayMedia:
    def __init__(self, folder, events, ended):
        self.folder = folder
        video_path = folder / 'video.mp4'
        has_video = video_path.is_file() and not video_path.is_symlink()
        self.pending = has_video and not ended
        self.video_path = video_path if has_video and ended else None
        images = {path.name for path in folder.glob('frame_*.jpg')}
        self.frames = [event for event in events if event.get('kind') == 'frame'
                       and (event.get('file') in images or 'index' in event and self.video_path)]
        self.times = [event['t'] for event in self.frames]
        self.capture = None
        self.video_index = -1
        self.frame_index = -1

    def close(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def frame_at(self, seconds):
        return max(0, bisect_right(self.times, seconds) - 1) if self.frames else -1

    def frame(self, index):
        if not 0 <= index < len(self.frames):
            return None, None
        event = self.frames[index]
        if 'file' in event:
            return local_image(self.folder, event['file'], FRAME_NAME), event
        if self.capture is None:
            self.capture = cv2.VideoCapture(str(self.video_path))
        if not self.capture.isOpened():
            return None, event
        wanted = event['index']
        if wanted != self.video_index + 1:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, wanted)
        ok, image = self.capture.read()
        self.video_index = wanted if ok else -1
        return image if ok else None, event
