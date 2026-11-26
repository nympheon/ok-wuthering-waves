from pathlib import Path

from PySide6.QtCore import QProcess, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget)

from ok import Icon
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.cards import Card
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.widget.CustomTab import CustomTab

from src.char.CharFactory import char_dict
from src.char.CustomCharLoader import get_english_char_name
from src.coco.characters.defaults import COCO, NATIVE, set_all_sources, set_source, source_preferences, source_versions
from src.coco.characters.portraits import character_portrait

PROJECT = Path(__file__).resolve().parents[3]


class DefaultCharacterTab(CustomTab):
    icon = Icon.PEOPLE

    def __init__(self):
        super().__init__()
        self.versions = source_versions()
        self.native_versions = dict(self.versions[NATIVE])
        classes = {info['cls'] for info in char_dict.values()}
        self.characters = {cls.__name__: self.tr(get_english_char_name(cls)) for cls in classes}
        self.choices = source_preferences()
        self._selected = None

        heading = Label(self.name, 'title', self)
        rule = Label(self.tr('A matched team uses its own code. These defaults apply to other lineups.'), 'caption', self)
        rule.setWordWrap(True)
        intro = QVBoxLayout()
        intro.setSpacing(5)
        intro.addWidget(heading)
        intro.addWidget(rule)

        all_native = Button(self.tr('Set All to Native'))
        all_native.clicked.connect(lambda: self._select_all_sources(NATIVE))
        all_coco = Button(self.tr('Set All to Coco'), variant='tonal')
        all_coco.clicked.connect(lambda: self._select_all_sources(COCO))
        header = QHBoxLayout()
        header.addLayout(intro, 1)
        header.addWidget(all_native, alignment=Qt.AlignmentFlag.AlignTop)
        header.addWidget(all_coco, alignment=Qt.AlignmentFlag.AlignTop)
        self.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr('Search characters'))
        self.search.setClearButtonEnabled(True)
        self.has_coco = QCheckBox(self.tr('Show characters with a coco version'))
        self.list = QListWidget()
        self.list.setIconSize(QSize(36, 36))
        self.list.setUniformItemSizes(True)
        self.list.setMinimumHeight(385)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        picker = Card()
        picker.setMinimumWidth(230)
        picker_layout = QVBoxLayout(picker)
        picker_layout.setContentsMargins(14, 14, 14, 14)
        picker_layout.setSpacing(10)
        picker_layout.addWidget(self.search)
        picker_layout.addWidget(self.has_coco)
        picker_layout.addWidget(self.list)

        self.avatar = QLabel()
        self.avatar.setFixedSize(56, 56)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.character_title = Label('', 'subtitle')
        self.current_source = Label('', 'caption')
        self.current_source.setWordWrap(True)
        selection = QHBoxLayout()
        selection.addWidget(self.avatar)
        selection_text = QVBoxLayout()
        selection_text.addWidget(self.character_title)
        selection_text.addWidget(self.current_source)
        selection.addLayout(selection_text, 1)

        details = QVBoxLayout()
        details.setSpacing(12)
        details.addLayout(selection)
        self.cards = {}
        for key, name, repository in ((NATIVE, 'EchoDesk Native', 'nympheon/ok-wuthering-waves'),
                                      (COCO, 'coco Enhanced', 'wk321425/coco-ww')):
            card = Card()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(15, 12, 15, 12)
            layout.setSpacing(6)
            title = Label(self.tr(name), 'subtitle')
            layout.addWidget(title)
            layout.addWidget(Label(repository, 'caption'))
            date = Label('', 'caption')
            date.setWordWrap(True)
            layout.addWidget(date)
            button = Button(self.tr('Use as default'), variant='primary')
            button.clicked.connect(lambda checked=False, key=key: self._select_source(key))
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
            self.cards[key] = date, button
            details.addWidget(card)
        details.addStretch(1)
        detail_widget = QWidget()
        detail_widget.setLayout(details)
        detail_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout()
        layout.setSpacing(20)
        layout.addWidget(picker, 2)
        layout.addWidget(detail_widget, 3)
        self.addLayout(layout)

        self.search.textChanged.connect(self._filter)
        self.has_coco.toggled.connect(self._filter)
        self.list.currentItemChanged.connect(self._selection_changed)
        self._filter()

        self.history = QProcess(self)
        self.history.setWorkingDirectory(str(PROJECT))
        self.history.finished.connect(self._history_loaded)
        self.history.start('git', ['--no-pager', 'log', '--no-renames', '--format=@%cs %H',
                                   '--name-only', '--', 'src/char'])

    @property
    def name(self):
        return self.tr('Default Character Code')

    def _source(self, class_name):
        if class_name in self.versions[COCO] and self.choices.get(class_name) == COCO:
            return COCO
        return NATIVE

    def _item_text(self, class_name):
        source = self.tr('coco Enhanced' if self._source(class_name) == COCO else 'EchoDesk Native')
        return f'{self.characters[class_name]}  ·  {source}'

    def _filter(self):
        selected = self._selected
        query = self.search.text().strip().casefold()
        self.list.clear()
        selection = None
        for class_name, label in sorted(self.characters.items(), key=lambda item: item[1].casefold()):
            if query not in f'{label} {get_english_char_name(class_name)} {class_name}'.casefold():
                continue
            if self.has_coco.isChecked() and class_name not in self.versions[COCO]:
                continue
            item = QListWidgetItem(QIcon(character_portrait(class_name)), self._item_text(class_name))
            item.setSizeHint(QSize(0, 47))
            item.setData(Qt.ItemDataRole.UserRole, class_name)
            self.list.addItem(item)
            if class_name == selected:
                selection = item
        self.list.setCurrentItem(selection or self.list.item(0))
        if not self.list.count():
            self._update_details()

    def _selection_changed(self, current, _previous):
        self._selected = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self._update_details()

    def _update_details(self):
        character = self._selected
        self.character_title.setText(self.characters.get(character, self.tr('No matching characters')))
        if character:
            pixmap = character_portrait(character)
            self.avatar.setPixmap(pixmap.scaled(self.avatar.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
        else:
            self.avatar.clear()
        active = self._source(character)
        self.current_source.setText(self.tr('Selected default: {source}').format(
            source=self.tr('coco Enhanced' if active == COCO else 'EchoDesk Native')) if character else '')
        for key, (date, button) in self.cards.items():
            versions = self.native_versions if key == NATIVE else self.versions[COCO]
            version = versions.get(character)
            if version:
                date.setText(self.tr('Code updated on {date}').format(date=version['date']))
                date.setToolTip(version['commit'])
            else:
                date.setText(self.tr('coco version unavailable' if key == COCO else 'Update date unavailable'))
                date.setToolTip('')
            button.setText(self.tr('Selected' if character and active == key else 'Use as default'))
            button.setEnabled(character is not None and active != key and (key == NATIVE or version is not None))

    def _select_source(self, key):
        if self._selected is None:
            return
        set_source(self._selected, key)
        self.choices = source_preferences()
        self.list.currentItem().setText(self._item_text(self._selected))
        self._update_details()

    def _select_all_sources(self, key):
        set_all_sources(key)
        self.choices = source_preferences()
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setText(self._item_text(item.data(Qt.ItemDataRole.UserRole)))
        self._update_details()

    def _history_loaded(self, exit_code, _status):
        if exit_code != 0:
            return
        found = {}
        stamp = None
        for line in bytes(self.history.readAllStandardOutput()).decode('utf-8', errors='replace').splitlines():
            if line.startswith('@'):
                date, commit = line[1:].split(maxsplit=1)
                stamp = {'date': date, 'commit': commit}
            elif stamp and line.endswith('.py'):
                class_name = Path(line).stem
                if class_name in self.characters:
                    found.setdefault(class_name, stamp)
        self.native_versions.update(found)
        self._update_details()
