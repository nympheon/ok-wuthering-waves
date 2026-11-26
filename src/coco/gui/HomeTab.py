"""Home quick controls adapted from coco-ww cd8c76e (HomeTab.py)."""

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QMenu, QVBoxLayout

from ok import og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.shell.run_bar import game_display_name
from ok.ui.qt.tasks.tasks_page import set_trigger_enabled, start_task, stop_task, task_active, task_status
from ok.ui.qt.widget.CustomTab import CustomTab

from src.coco.gui.DashboardTab import DashboardTab
from src.coco.recorder.RecorderTab import AxisRecorderTab
from src.coco.recorder.recording import party_snapshot


class HomeTab(CustomTab):
    icon = 'grid'

    @property
    def name(self):
        return 'Home'

    @property
    def add_after_default_tabs(self):
        return False

    def __init__(self):
        super().__init__()
        connection = QHBoxLayout()
        text = QVBoxLayout()
        self.connection = Label('', 'title')
        self.connection_detail = Label('', 'secondary')
        text.addWidget(self.connection)
        text.addWidget(self.connection_detail)
        connection.addLayout(text, 1)
        connect = Button(self.tr('Game connection'), 'gamepad')
        connect.clicked.connect(self._connection)
        connection.addWidget(connect)
        self.executor_button = Button(self.tr('Start'), 'power', variant='primary')
        self.executor_button.clicked.connect(self._toggle_executor)
        connection.addWidget(self.executor_button)
        self.addLayout(connection)

        self.team = Label('', 'body', word_wrap=True)
        self.team.setTextFormat(Qt.TextFormat.PlainText)
        self.add_card(self.tr('Party'), self.team)

        cards = QHBoxLayout()
        combat_card, self.combat_status, self.combat_details, self.combat_button = self._card(
            'Auto Combat', self._toggle_combat, lambda: self._settings('AutoCombatTask'))
        farm_card, self.farm_status, self.farm_details, self.farm_button = self._card(
            'Farm 4C Echo', self._toggle_farm, lambda: self._settings('FarmEchoTask'))
        self.farm_target = Button(self.tr('Farm target'), 'chevron-down')
        self.farm_target.clicked.connect(self._farm_menu)
        farm_card.layout().addWidget(self.farm_target, alignment=Qt.AlignmentFlag.AlignLeft)
        cards.addWidget(combat_card, 1)
        cards.addWidget(farm_card, 1)
        self.addLayout(cards)

        tools = QHBoxLayout()
        dashboard = Button(self.tr('Combat Dashboard'), 'pulse')
        dashboard.clicked.connect(lambda: self._open_tab(DashboardTab))
        tools.addWidget(dashboard)
        replay = Button(self.tr('Combat Replay'), 'play')
        replay.clicked.connect(lambda: self._open_tab(AxisRecorderTab))
        tools.addWidget(replay)
        tools.addStretch()
        self.addLayout(tools)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)

    def _card(self, title, trigger, settings):
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(Label(self.tr(title), 'subtitle'))
        status = Label('', 'body')
        layout.addWidget(status)
        details = Label('', 'secondary', word_wrap=True)
        details.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(details, 1)
        actions = QHBoxLayout()
        button = Button('', 'play', variant='primary')
        button.clicked.connect(trigger)
        actions.addWidget(button)
        options = Button(self.tr('Settings'), 'gear')
        options.clicked.connect(settings)
        actions.addWidget(options)
        actions.addStretch()
        layout.addLayout(actions)
        return card, status, details, button

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _task(self, class_name):
        executor = self.executor or getattr(og, 'executor', None)
        return executor.get_task_by_class_name(class_name) if executor is not None else None

    @staticmethod
    def _run_bar():
        return getattr(getattr(og, 'main_window', None), 'run_bar', None)

    def refresh(self):
        window = getattr(og, 'main_window', None)
        run_bar = self._run_bar()
        if run_bar is not None:
            self.executor_button.setText(run_bar.executor_button.text())
            self.executor_button.setEnabled(run_bar.executor_button.isEnabled())
            self.executor_button.set_hint(run_bar.hotkey())
        else:
            self.executor_button.setEnabled(False)
        manager = getattr(og, 'device_manager', None)
        device = manager.get_preferred_device() if manager else None
        self.connection.setText(game_display_name(getattr(og, 'config', None) or {}))
        if not device:
            self.connection_detail.setText(self.tr('No game selected'))
        else:
            details = [self.tr('Connected') if device.get('connected') else self.tr('Disconnected')]
            if device.get('resolution'):
                details.append(str(device['resolution']))
            self.connection_detail.setText('  ·  '.join(details))
        executor = self.executor or getattr(og, 'executor', None)
        current = getattr(executor, 'current_task', None)
        auto, farm = self._task('AutoCombatTask'), self._task('FarmEchoTask')
        members = party_snapshot(current) or party_snapshot(auto) or party_snapshot(farm)
        self.team.setText('  ·  '.join(self.tr(member['name']) for member in members)
                          or self.tr('Party not recognized yet'))
        self._show_combat(auto, current)
        self._show_farm(farm, window, executor)

    def _show_combat(self, task, current):
        self.combat_button.setEnabled(task is not None)
        enabled = task is not None and task.enabled
        active = enabled and current is task and getattr(task, '_in_combat', False)
        self.combat_status.setText(self.tr('In combat' if active else 'Enabled' if enabled else 'Disabled'))
        self.combat_button.setText(self.tr('Disable' if enabled else 'Enable'))
        self.combat_button.set_icon('stop' if enabled else 'play')
        keys = ('Auto Target', 'Use Liberation', 'Start Combat with F')
        options = [self.tr(key) for key in keys if task is not None and task.config.get(key, False)]
        self.combat_details.setText('  ·  '.join(options))

    def _show_farm(self, task, window, executor):
        self.farm_button.setEnabled(task is not None and window is not None)
        self.farm_target.setEnabled(task is not None)
        active = task is not None and task_active(task)
        paused = task is not None and task.enabled and task.paused
        status = task_status(task, executor) if task is not None and executor is not None else None
        self.farm_status.setText(status[0] if status else self.tr('Ready'))
        self.farm_button.setText(self.tr('Stop' if active else 'Resume' if paused else 'Start'))
        self.farm_button.set_icon('stop' if active else 'play')
        if task is None:
            self.farm_details.clear()
            return
        target = task.config.get('Teleport to Boss')
        boss = task.config.get('Boss', 'Other')
        configs = [self.tr(target)] if target and target != 'No' else []
        if teleport := getattr(task, 'TELEPORT_CHOICES', {}).get(target):
            from src.coco.boss_book import LIST_POSITION, name_from_option
            _, name_key, position_key = teleport
            option = task.config.get(name_key)
            if option == LIST_POSITION:
                configs.append(f"#{task.config.get(position_key)}")
            elif option:
                configs.append(name_from_option(option))
        if boss and boss != 'Other':
            configs.append(self.tr(boss))
        if (count := task.info.get('Echo Count')) is not None:
            configs.append(self.tr('{count} Echoes').format(count=count))
        if (rate := task.info.get('Echo per Hour')) is not None:
            configs.append(self.tr('{rate} per hour').format(rate=rate))
        self.farm_details.setText('  ·  '.join(configs))

    def _farm_menu(self):
        task = self._task('FarmEchoTask')
        if task is None:
            return
        menu = QMenu(self)
        for key in ('Teleport to Boss', 'Boss'):
            options = task.config_type[key]['options']
            self._farm_options(menu.addMenu(self.tr(key)), task, key, options)
        current = task.config.get('Teleport to Boss')
        if teleport := getattr(task, 'TELEPORT_CHOICES', {}).get(current):
            _, key, _ = teleport
            self._farm_options(menu.addMenu(self.tr(key)), task, key, task.config_type[key]['options'])
        menu.exec(self.farm_target.mapToGlobal(QPoint(0, self.farm_target.height())))
        menu.deleteLater()

    def _farm_options(self, menu, task, key, options):
        for value in options:
            action = menu.addAction(self.tr(value))
            action.setCheckable(True)
            action.setChecked(task.config.get(key) == value)
            action.triggered.connect(lambda _checked, option=value: self._set_farm_config(task, key, option))

    def _set_farm_config(self, task, key, value):
        task.config[key] = value
        self.refresh()

    def _toggle_executor(self):
        if (run_bar := self._run_bar()) is not None:
            run_bar.refresh()
            run_bar.toggle_executor()

    def _toggle_combat(self):
        if (task := self._task('AutoCombatTask')) is not None:
            set_trigger_enabled(task, not task.enabled)
            self.refresh()

    def _toggle_farm(self):
        if (task := self._task('FarmEchoTask')) is not None:
            if task_active(task):
                stop_task(task)
            else:
                start_task(task, self)
            self.refresh()

    def _connection(self):
        if (run_bar := self._run_bar()) is not None:
            run_bar.open_popover()

    def _settings(self, class_name):
        if (task := self._task(class_name)) is not None and og.main_window is not None:
            og.main_window.show_task(task)

    @staticmethod
    def _open_tab(tab_class):
        window = og.main_window
        if window is not None and (tab := window.findChild(tab_class)) is not None:
            window.switch_to(tab)
