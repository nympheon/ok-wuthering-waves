"""Live combat dashboard adapted from coco-ww cd8c76e (DashboardTab.py and live.py)."""

from statistics import median
from time import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QVBoxLayout

from ok import og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.widget.CustomTab import CustomTab

from src.coco.recorder.RecorderTab import AxisRecorderTab, AxisTimeline, clock, slot_name
from src.coco.recorder.hooks import recorder_for
from src.coco.recorder.recording import party_snapshot


def repeated_rotations(changes):
    # Find the shortest repeating swap order covering the longest suffix.
    slots = [slot for _, slot in changes]
    count = len(slots)
    candidates = []
    for period in range(2, min(16, (count - 1) // 2) + 1):
        start = count - period
        while start > 0 and slots[start - 1] == slots[start - 1 + period]:
            start -= 1
        if (count - 1 - start) // period >= 2:
            candidates.append((start, period))
    if not candidates:
        return []
    start, period = min(candidates)
    return [changes[i + period][0] - changes[i][0] for i in range(start, count - period, period)]


class DashboardTab(CustomTab):
    icon = 'pulse'

    @property
    def name(self):
        return 'Combat Dashboard'

    def __init__(self):
        super().__init__()
        controls = QHBoxLayout()
        self.task = Label('', 'title', word_wrap=True)
        controls.addWidget(self.task, 1)
        settings = Button(self.tr('Recorder settings'), 'gear')
        settings.clicked.connect(self._settings)
        controls.addWidget(settings)
        replay = Button(self.tr('Combat Replay'), 'play')
        replay.clicked.connect(self._replay)
        controls.addWidget(replay)
        self.addLayout(controls)
        self.status = Label('', 'secondary', word_wrap=True)
        self.add_widget(self.status)

        stats = QHBoxLayout()
        self.duration = self._metric(stats, self.tr('Elapsed'))
        self.switches = self._metric(stats, self.tr('Switches'))
        self.switch_delay = self._metric(stats, self.tr('Switch delay'))
        self.input_count = self._metric(stats, self.tr('Inputs'))
        self.rotation = self._metric(stats, self.tr('Latest rotation'))
        self.addLayout(stats)

        self.party = Label('', 'body', word_wrap=True)
        self.party.setTextFormat(Qt.TextFormat.PlainText)
        self.add_card(self.tr('Party'), self.party)
        self.timeline = AxisTimeline(self)
        self.add_card(self.tr('Last 30 seconds'), self.timeline)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(140)
        self.logs.document().setMaximumBlockCount(80)
        self.add_card(self.tr('Combat logs'), self.logs)

        self._last_log = None
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.refresh)

    @staticmethod
    def _metric(row, title):
        card = Card()
        layout = QVBoxLayout(card)
        layout.addWidget(Label(title, 'secondary'))
        value = Label('—', 'subtitle')
        layout.addWidget(value)
        row.addWidget(card, 1)
        return value

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self):
        executor = self.executor or getattr(og, 'executor', None)
        recorder = recorder_for(executor)
        current = getattr(executor, 'current_task', None)
        running = current if getattr(current, 'running', False) else None
        auto = executor.get_task_by_class_name('AutoCombatTask') if executor else None
        snapshot = recorder.snapshot() if recorder is not None else None
        paused = executor is None or executor.paused
        if snapshot and not snapshot['end']:
            status = self.tr('Recording')
        elif paused:
            status = self.tr('Executor paused')
        elif recorder is None or not recorder.owner.enabled:
            status = self.tr('Recorder disabled')
        elif recorder.owner.manual_mode:
            status = self.tr(recorder.owner.manual.status)
        else:
            status = self.tr('Waiting for combat')
        if snapshot and snapshot['error']:
            status = snapshot['error']
        task_name = snapshot['header']['task'] if snapshot and not snapshot['end'] else getattr(running, 'name', '')
        self.task.setText(self.tr(task_name) if task_name else self.tr('Combat Dashboard'))
        self.status.setText(f"{status}  ·  {self.tr('Last recording')}" if snapshot and snapshot['end'] else status)

        if not snapshot:
            party_task = running if getattr(running, 'chars', None) else auto
            slot = next((char.index for char in getattr(party_task, 'chars', ())
                         if char is not None and char.is_current_char), None)
            self._show_party(party_snapshot(party_task), slot, {})
            self.timeline.set_data(0, {}, ())
            self.timeline.set_cursor(0)
            self._show_logs(())
            for metric in (self.duration, self.switches, self.switch_delay, self.input_count, self.rotation):
                metric.setText('—')
            started = getattr(running, 'combat_start', 0)
            if getattr(running, '_in_combat', False) and started and not paused:
                self.duration.setText(clock(max(0, time() - started)))
            return
        elapsed = snapshot['elapsed']
        self.duration.setText(clock(elapsed))
        self.switches.setText(str(max(0, len(snapshot['switches']) - 1)))
        delays = snapshot['switch_delays']
        self.switch_delay.setText(f'{median(delays) * 1000:.0f} ms' if delays else '—')
        self.input_count.setText(str(snapshot['counts'].get('input', 0)))
        rotations = repeated_rotations(snapshot['switches'])
        self.rotation.setText(f'{rotations[-1]:.2f} s' if rotations else '—')
        members = snapshot['header']['team']
        self._show_party(members, snapshot['active'], snapshot['field_times'])
        team = {member['slot']: self.tr(member['name']) for member in members}
        start = max(0, elapsed - 30)
        recent = [dict(event, t=event['t'] - start) for event in snapshot['events']
                  if event['kind'] != 'field' and event['t'] >= start]
        fields = snapshot['field']
        before = next((slot for at, slot in reversed(fields) if at <= start), None)
        recent.extend([{'kind': 'field', 't': 0, 'slot': before}]
                      + [{'kind': 'field', 't': at - start, 'slot': slot} for at, slot in fields if at > start])
        self.timeline.set_data(elapsed - start, team, recent)
        self.timeline.set_cursor(elapsed - start)
        self._show_logs(snapshot['logs'])

    def _show_party(self, team, active, elapsed):
        lines = []
        for member in team:
            slot = member['slot']
            prefix = '●' if slot == active else '○'
            details = [self.tr(member['name']), self.tr(member['role'])]
            if slot in elapsed:
                details.append(f'{elapsed[slot]:.1f} s')
            if slot == active:
                details.append(self.tr('On field'))
            lines.append(f'{prefix}  {slot + 1}    ' + '  ·  '.join(part for part in details if part))
        if active is not None and not any(member['slot'] == active for member in team):
            lines.append(slot_name({}, active))
        self.party.setText('\n'.join(lines) or self.tr('Party not recognized yet'))

    def _show_logs(self, events):
        if events == self._last_log:
            return
        self._last_log = events
        bar = self.logs.verticalScrollBar()
        follow = bar.value() == bar.maximum()
        self.logs.setPlainText('\n'.join(f"{clock(event['t'])}  {event['level']}  {event['message']}" for event in events))
        if follow:
            bar.setValue(bar.maximum())

    def _settings(self):
        recorder = recorder_for(self.executor)
        if recorder is not None and og.main_window is not None:
            og.main_window.show_task(recorder.owner)

    def _replay(self):
        window = og.main_window
        if window is not None and (tab := window.findChild(AxisRecorderTab)) is not None:
            window.switch_to(tab)
