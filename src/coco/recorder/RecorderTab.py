"""Local combat-axis replay adapted from coco-ww cd8c76e (RecorderTab.py)."""

from bisect import bisect_left, bisect_right
from datetime import datetime
from time import monotonic

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHeaderView, QHBoxLayout, QLabel,
                               QSlider, QTableView, QVBoxLayout, QWidget)

from ok import og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.widget.CustomTab import CustomTab

from .hooks import recorder_for
from .recording import recordings, run_directory
from .replay import CROP_NAME, ReplayMedia, local_image, read_recording


LANES = (('field', 'On field'), ('input', 'Inputs'), ('action', 'Actions'), ('read', 'Recognition'), ('log', 'Logs'))
KINDS = dict(LANES) | {'note': 'Events'}
SLOT_COLORS = ('#3f86dc', '#a05bd1', '#d67d43')
MARK_COLORS = {'input': '#307ee5', 'action': '#1e9d81', 'read': '#a872d0', 'log': '#8592a3'}


def tr(text):
    return og.app.tr(text) if getattr(og, 'app', None) is not None else text


def clock(seconds):
    return f'{int(seconds) // 60:02d}:{seconds % 60:06.3f}'


def slot_name(team, slot):
    if slot is None:
        return tr('HUD hidden')
    return team.get(slot) or tr('Slot {slot}').format(slot=slot + 1)


def event_text(event, team):
    kind = event['kind']
    if kind == 'field':
        return slot_name(team, event.get('slot'))
    if kind == 'input':
        text = f"{tr(event['action'])}  {event['key']}"
        if 'duration' in event:
            text += f"  {event['duration']:.3f} s"
        return text
    if kind == 'action':
        return f"{slot_name(team, event['slot'])}  ·  {tr(event['action'])}"
    if kind == 'read':
        value = tr('No match') if event.get('value') is None else str(event['value'])
        return f"{tr(event['reader'])}  ·  {event['label']}  ·  {value}"
    if kind == 'log':
        return f"{event.get('level', '')}  {event.get('message', '')}"
    return tr(event.get('message', ''))


def _image(array):
    if array is None:
        return QImage()
    height, width = array.shape[:2]
    return QImage(array.data, width, height, array.strides[0], QImage.Format.Format_BGR888).copy()


class AxisTimeline(QWidget):
    seek_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(128)
        self.setAccessibleName(tr('Combat timeline'))
        self.duration = 0.0
        self.cursor = 0.0
        self.team = {}
        self.events = {}

    def set_data(self, duration, team, events):
        self.duration = duration
        self.team = team
        self.events = {kind: [] for kind, _ in LANES}
        for event in events:
            kind = event['kind']
            if kind in self.events:
                self.events[kind].append(event)
        self.update()

    def set_cursor(self, seconds):
        self.cursor = seconds
        self.update()

    def _start(self):
        return max(self.fontMetrics().horizontalAdvance(tr(label)) for _, label in LANES) + 16

    def paintEvent(self, event):
        painter = QPainter(self)
        margin = self._start()
        width = max(1, self.width() - margin - 3)
        step = self.height() / len(LANES)
        duration = max(self.duration, 0.001)
        palette = self.palette()
        for row, (kind, label) in enumerate(LANES):
            y = row * step
            painter.fillRect(QRectF(margin, y + 1, width, step - 2), palette.alternateBase())
            painter.setPen(palette.text().color())
            painter.drawText(QRectF(0, y, margin - 6, step), Qt.AlignmentFlag.AlignVCenter, tr(label))
            events = self.events.get(kind, ())
            if kind == 'field':
                for i, field in enumerate(events):
                    slot = field.get('slot')
                    start = field['t']
                    end = events[i + 1]['t'] if i + 1 < len(events) else self.duration
                    if slot is None:
                        continue
                    color = QColor(SLOT_COLORS[slot % len(SLOT_COLORS)])
                    rect = QRectF(margin + width * start / duration, y + 2, max(2, width * (end - start) / duration), step - 4)
                    painter.fillRect(rect, color)
                    name = slot_name(self.team, slot)
                    if painter.fontMetrics().horizontalAdvance(name) + 8 < rect.width():
                        painter.setPen(QColor('#ffffff'))
                        painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, name)
            else:
                painter.setPen(QPen(QColor(MARK_COLORS[kind]), 2))
                marks = {int(margin + width * tick['t'] / duration) for tick in events}
                for x in marks:
                    painter.drawLine(x, round(y + 4), x, round(y + step - 4))
        if self.duration:
            x = int(margin + width * self.cursor / duration)
            painter.setPen(QPen(palette.highlight().color(), 2))
            painter.drawLine(x, 0, x, self.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._seek(event.position().x())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._seek(event.position().x())

    def _seek(self, x):
        margin = self._start()
        ratio = (x - margin) / max(1, self.width() - margin - 3)
        self.seek_requested.emit(self.duration * min(1.0, max(0.0, ratio)))


class FrameView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(430, 238)
        self.image = QImage()
        self.mark = None
        self.zoom = 1.0
        self.offset = QPointF()
        self.drag = None
        self.message = tr('No recorded image at this time')

    def set_zoom(self, zoom):
        self.zoom = zoom
        self.offset = QPointF()
        cursor = Qt.CursorShape.OpenHandCursor if zoom > 1 else Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)
        self.update()

    def _display_size(self):
        return self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio) * self.zoom

    def mousePressEvent(self, event):
        if self.zoom > 1 and event.button() == Qt.MouseButton.LeftButton:
            self.drag = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.drag is not None:
            offset = self.offset + event.position() - self.drag
            size = self._display_size()
            x = max(0, (size.width() - self.width()) / 2)
            y = max(0, (size.height() - self.height()) / 2)
            self.offset = QPointF(max(-x, min(x, offset.x())), max(-y, min(y, offset.y())))
            self.drag = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drag is not None:
            self.drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#181d26'))
        if self.image.isNull():
            painter.setPen(QColor('#cfdae7'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        size = self._display_size()
        x = (self.width() - size.width()) / 2 + self.offset.x()
        y = (self.height() - size.height()) / 2 + self.offset.y()
        rect = QRectF(x, y, size.width(), size.height())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(rect, self.image)
        if not self.mark or not self.mark.get('frame_size'):
            return
        source_width, source_height = self.mark['frame_size']
        regions = self.mark.get('boxes') or []
        if not regions and self.mark.get('region'):
            regions = [{'rect': self.mark['region']}]
        painter.setPen(QPen(QColor('#36e0a9'), 2))
        for region in regions:
            left, top, width, height = region['rect']
            painter.drawRect(QRectF(x + left * size.width() / source_width, y + top * size.height() / source_height,
                                    width * size.width() / source_width, height * size.height() / source_height))


class EventModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.events = []
        self.team = {}

    def set_data(self, events, team):
        self.beginResetModel()
        self.events = events
        self.team = team
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.events)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return tr(('Time', 'Type', 'Event')[section])
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None
        event = self.events[index.row()]
        if index.column() == 0:
            return clock(event['t'])
        if index.column() == 1:
            return tr(KINDS.get(event['kind'], 'Events'))
        return event_text(event, self.team)


class AxisRecorderTab(CustomTab):
    icon = 'play'

    @property
    def name(self):
        return 'Combat Replay'

    def __init__(self):
        super().__init__()
        self.root = run_directory()
        self.folder = None
        self.file_stamp = None
        self.media = None
        self.events = []
        self.team = {}
        self.duration = self.position = 0.0
        self.selected_event = None
        self._play_origin = 0.0
        self._last_tick = 0.0

        controls = QHBoxLayout()
        self.run_picker = QComboBox(self)
        self.run_picker.currentIndexChanged.connect(self._load)
        controls.addWidget(self.run_picker, 1)
        refresh = Button(self.tr('Refresh'), 'refresh')
        refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh)
        folder = Button(self.tr('Local folder'), 'folder')
        folder.clicked.connect(self._open_folder)
        controls.addWidget(folder)
        settings = Button(self.tr('Recorder settings'), 'gear')
        settings.clicked.connect(self._settings)
        controls.addWidget(settings)
        self.addLayout(controls)
        self.status = Label('', 'secondary', word_wrap=True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.add_widget(self.status)

        frame_row = QHBoxLayout()
        self.frame_view = FrameView(self)
        frame_row.addWidget(self.frame_view, 3)
        sidebar = QVBoxLayout()
        self.zoom = QComboBox()
        self.zoom.setAccessibleName(self.tr('Image zoom'))
        self.zoom.addItem(self.tr('Fit to view'), 1.0)
        for value in (1.5, 2.0, 3.0):
            self.zoom.addItem(f'{value:g}×', value)
        self.zoom.currentIndexChanged.connect(lambda _index: self.frame_view.set_zoom(self.zoom.currentData()))
        sidebar.addWidget(self.zoom, 0, Qt.AlignmentFlag.AlignLeft)
        self.details = Label('', 'secondary', word_wrap=True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        sidebar.addWidget(self.details)
        self.crop = QLabel()
        self.crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar.addWidget(self.crop)
        sidebar.addStretch()
        frame_row.addLayout(sidebar, 2)
        self.addLayout(frame_row)

        self.timeline = AxisTimeline(self)
        self.timeline.seek_requested.connect(self._seek_from_user)
        self.add_widget(self.timeline)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setAccessibleName(self.tr('Seek recording'))
        self.slider.valueChanged.connect(lambda value: self._seek_from_user(value / 1000))
        self.add_widget(self.slider)

        playback = QHBoxLayout()
        self.play = Button(self.tr('Play'), 'play', variant='primary')
        self.play.clicked.connect(self._play_pause)
        playback.addWidget(self.play)
        self._navigation = []
        for label, direction, callback in (('Previous frame', -1, self._step_frame), ('Next frame', 1, self._step_frame),
                                            ('Previous event', -1, self._step_event), ('Next event', 1, self._step_event)):
            button = Button(self.tr(label))
            button.clicked.connect(lambda checked=False, step=direction, move=callback: move(step))
            playback.addWidget(button)
            self._navigation.append(button)
        self.speed = QComboBox()
        self.speed.setAccessibleName(self.tr('Playback speed'))
        for value in (0.25, 0.5, 1, 1.5, 2):
            self.speed.addItem(f'{value:g}×', value)
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(self._reset_play_clock)
        playback.addWidget(self.speed)
        playback.addStretch()
        self.position_text = Label('', 'mono')
        playback.addWidget(self.position_text)
        self.addLayout(playback)

        self.event_filter = QComboBox()
        self.event_filter.setAccessibleName(self.tr('Event type'))
        self.event_filter.addItem(self.tr('All events'), None)
        for kind, text in KINDS.items():
            self.event_filter.addItem(self.tr(text), kind)
        self.event_filter.currentIndexChanged.connect(self._update_events)
        self.add_widget(self.event_filter, 0, Qt.AlignmentFlag.AlignLeft)
        self.model = EventModel(self)
        self.table = QTableView()
        self.table.setMinimumHeight(220)
        self.table.setModel(self.model)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().currentRowChanged.connect(self._event_row)
        self.add_widget(self.table)

        self.player = QTimer(self)
        self.player.setInterval(33)
        self.player.timeout.connect(self._play_tick)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.refresh)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.refresh_timer.start()

    def hideEvent(self, event):
        self._pause()
        self.refresh_timer.stop()
        if self.media is not None:
            self.media.close()
        self.file_stamp = None
        super().hideEvent(event)

    def refresh(self):
        try:
            paths = recordings(self.root)
        except OSError:
            paths = []
        selected = self.run_picker.currentData()
        existing = [self.run_picker.itemData(i) for i in range(self.run_picker.count())]
        if existing != paths:
            self.run_picker.blockSignals(True)
            self.run_picker.clear()
            for path in paths:
                label = datetime.strptime(path.name, '%Y%m%d_%H%M%S_%f').strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                self.run_picker.addItem(label, path)
            self.run_picker.setCurrentIndex(paths.index(selected) if selected in paths else (0 if paths else -1))
            self.run_picker.blockSignals(False)
        self._load()

    def _load(self, _index=None):
        folder = self.run_picker.currentData()
        if folder is None:
            if self.folder is not None:
                self._reset()
            self.status.setText(self.tr('No local recordings. Enable Combat Axis Recorder in Tasks to record a battle.'))
            self._update_buttons()
            return
        try:
            stamp = (folder / 'events.jsonl').stat().st_mtime_ns
            if self.folder == folder and self.file_stamp == stamp:
                return
            header, end, events = read_recording(folder)
        except (OSError, UnicodeError):
            self.status.setText(self.tr('The selected recording could not be read.'))
            return
        if folder != self.folder:
            self._reset()
        elif self.media is not None:
            self.media.close()
        self.folder, self.file_stamp = folder, stamp
        self.media = ReplayMedia(folder, events, end is not None)
        self.events = [event for event in events if event.get('kind') in KINDS]
        self.team = {member['slot']: self.tr(member['name']) for member in header.get('team', ())}
        self.duration = end['t'] if end else (events[-1]['t'] if events else 0.0)
        caption = [self.tr(header.get('mode', '')), self.tr(header.get('task', '')), ' · '.join(self.team.values()),
                   self.tr(end.get('reason', '')) if end else self.tr('Recording or interrupted')]
        if end and (dropped := end.get('dropped_frames')):
            caption.append(self.tr('{count} dropped frames').format(count=dropped))
        self.status.setText('  ·  '.join(item for item in caption if item))
        self.timeline.set_data(self.duration, self.team, self.events)
        self.slider.blockSignals(True)
        self.slider.setRange(0, round(self.duration * 1000))
        self.slider.blockSignals(False)
        self._update_events()
        self._seek(self.position)
        self._update_buttons()

    def _reset(self):
        self._pause()
        if self.media is not None:
            self.media.close()
        self.folder, self.file_stamp, self.media = None, None, None
        self.events, self.team = [], {}
        self.duration = self.position = 0.0
        self.selected_event = None
        self.timeline.set_data(0, {}, [])
        self.slider.setRange(0, 0)
        self._update_events()
        self._seek(0)

    def _update_events(self, _index=None):
        kind = self.event_filter.currentData()
        self.model.set_data([event for event in self.events if kind is None or kind == event['kind']], self.team)

    def _update_buttons(self):
        self.play.setEnabled(self.duration > 0)
        for button in self._navigation[:2]:
            button.setEnabled(bool(self.media and self.media.frames))
        for button in self._navigation[2:]:
            button.setEnabled(bool(self.events))

    def _event_row(self, index, _previous):
        if index.isValid():
            self._pause()
            self.selected_event = self.model.events[index.row()]
            self._seek(self.selected_event['t'])

    def _seek_from_user(self, seconds):
        self._pause()
        self.selected_event = None
        self._seek(seconds)

    def _seek(self, seconds):
        self.position = max(0, min(seconds, self.duration))
        self.timeline.set_cursor(self.position)
        self.slider.blockSignals(True)
        self.slider.setValue(round(self.position * 1000))
        self.slider.blockSignals(False)
        self.position_text.setText(f'{clock(self.position)}  /  {clock(self.duration)}')
        no_frame = self.tr('Video will be available after recording ends') if self.media and self.media.pending else self.tr('No recorded image at this time')
        self.frame_view.message = no_frame
        frame_index = self.media.frame_at(self.position) if self.media else -1
        if self.media is None:
            self.frame_view.image = QImage()
        elif self.media.frame_index != frame_index or frame_index < 0:
            image, _frame = self.media.frame(frame_index)
            self.media.frame_index = frame_index
            self.frame_view.image = _image(image)
        self.frame_view.mark = self.selected_event if self.selected_event and self.selected_event['kind'] == 'read' else None
        self.frame_view.update()
        self._show_details()

    def _show_details(self):
        event = self.selected_event
        if not event:
            self.details.clear()
            self.crop.clear()
            return
        details = [event_text(event, self.team), event.get('source')]
        for box in event.get('boxes') or ():
            details.append(f"{box['name']}   {box['confidence']:.3f}   {box['rect']}")
        if event.get('point'):
            details.append(str(event['point']))
        self.details.setText('\n'.join(item for item in details if item))
        image = _image(local_image(self.folder, event.get('crop'), CROP_NAME)) if self.folder else QImage()
        if image.isNull():
            self.crop.clear()
        else:
            self.crop.setPixmap(QPixmap.fromImage(image).scaled(270, 130, Qt.AspectRatioMode.KeepAspectRatio,
                                                               Qt.TransformationMode.SmoothTransformation))

    def _step_frame(self, direction):
        if self.media and self.media.frames:
            index = self.media.frame_at(self.position)
            step = min(len(self.media.frames) - 1, max(0, index + direction))
            self._seek_from_user(self.media.times[step])

    def _step_event(self, direction):
        events = self.model.events
        if not events:
            return
        current = self.table.currentIndex()
        if self.selected_event is not None and current.isValid():
            row = current.row() + direction
        else:
            times = [event['t'] for event in events]
            row = bisect_right(times, self.position) if direction > 0 else bisect_left(times, self.position) - 1
        self.table.selectRow(min(len(events) - 1, max(0, row)))

    def _reset_play_clock(self, _index=None):
        self._play_origin, self._last_tick = self.position, monotonic()

    def _play_pause(self):
        if self.player.isActive():
            self._pause()
            return
        self.selected_event = None
        if self.position >= self.duration:
            self._seek(0.0)
        self._reset_play_clock()
        self.play.setText(self.tr('Pause'))
        self.play.set_icon('pause')
        self.player.start()

    def _pause(self):
        self.player.stop()
        self.play.setText(self.tr('Play'))
        self.play.set_icon('play')

    def _play_tick(self):
        seconds = self._play_origin + (monotonic() - self._last_tick) * self.speed.currentData()
        self._seek(seconds)
        if seconds >= self.duration:
            self._pause()

    def _open_folder(self):
        self.root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.root)))

    def _settings(self):
        recorder = recorder_for(self.executor)
        if recorder is not None and og.main_window is not None:
            og.main_window.show_task(recorder.owner)
