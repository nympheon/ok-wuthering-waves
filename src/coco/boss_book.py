"""Find 4C bosses in the Guidebook using the row name and its action button."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ok import Box, Logger

logger = Logger.get_logger(__name__)

LIST_POSITION = 'Select by List Position'
LEARNED_FILE = Path('configs/boss_book_names.json')
# The original list order is also the migration table for saved numeric settings.
SEED_NAMES = {
    'zhange': ('定序诸理之律', '失坠困咎之庭', '虚妄诞生之种', '星海迷途之扉', '烬夜天启之章',
               '命途断章之轮', '彼世猩红之幕', '时序命定之争', '无冠巨像之心', '无序边境之火', '昔日咏叹之钟'),
    'qiangdi': ('天傀劫煞', '万囮牢·朽躯', '梦魇亚当·重锤', '无铭探索者', '海维夏', '炉芯机骸', '海之女',
                '伪作的神王', '芬莱克', '荣耀狮像', '叹息古龙', '罗蕾莱', '异构武装', '无归的谬误',
                '无冠者', '朔雷之鳞', '云闪之鳞', '燎照之骑', '飞廉之猩', '哀声鸷', '无常凶鹭',
                '辉萤军势', '聚械机偶'),
    'mengyan': ('梦魇·赫卡忒', '梦魇·凯尔匹', '梦魇·辉萤军势', '梦魇·哀声鸷', '梦魇·燎照之骑',
                '梦魇·无冠者', '梦魇·朔雷之鳞', '梦魇·云闪之鳞', '梦魇·无常凶鹭', '梦魇·飞廉之猩'),
}
WEEKLY_BOSSES = dict(zip(SEED_NAMES['zhange'], (
    '天演溯心', '千傀重楼', '达妮娅', '辛吉勒姆', '利维亚坦', '芙露德莉斯',
    '赫卡忒', '角', '无妄者', '伤痕', '鸣钟之龟',
)))
CATEGORY_TITLES = {
    'zhange': ('战歌重奏', '戰歌重奏', 'Weekly Challenge'),
    'qiangdi': ('讨伐强敌', '討伐強敵', 'Boss Challenge'),
    'mengyan': ('梦魇祓除', '夢魘祓除', 'Nightmare Purification'),
}

CONFUSABLE = str.maketrans({'魔': '魇', '夢': '梦', '魘': '魇', '維': '维', '紅': '红', '異': '异', '昇': '异', '無': '无'})
WORD_SEPARATOR = re.compile(r'[^0-9A-Za-z一-鿿]')
DECOR = re.compile(r'[战戰]歌重奏')
PROGRESS = re.compile(r'\d+\s*/\s*\d+')
BANNER = re.compile(r'提前开放|提前開放|次数|次數|筛选|篩選|奖励|獎勵|剩余|剩餘|索拉等级|索拉等級|活动|活動|'
                    r'Early\s*Access|Remaining|Filter', re.I)
BUTTON_TEXT = re.compile(r'^(?:(?:直接)?挑[战戰]|Challenge|前往|Go|Proceed)$', re.I)
NAME_AREA = (0.43, 0.10, 0.64, 0.97)
BUTTON_AREA = (0.84, 0.10, 0.985, 0.97)
ROW_SPAN = 0.095
SCROLL_TICKS = 10
SCROLL_TICK_HEIGHT = 0.0244
ROW_HEIGHT = 0.10
FIXED_TEXT_TOLERANCE = 0.003


def normalize(text):
    return ''.join(character for character in DECOR.sub('', text.translate(CONFUSABLE))
                   if character.isalnum()).casefold()


def _edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = row
    return previous[-1]


def _match_distance(a, b):
    distance = _edit_distance(a, b)
    return distance if len(a) >= 2 and distance <= (1 if len(b) <= 7 else 2) else None


def display_name(text):
    return DECOR.sub('', text).replace('・', '·').strip(' ·')


def name_from_option(option):
    match = re.fullmatch(r'.+?[（(](.+?)[）)]', option or '')
    return match[1] if match else (option or '')


def boss_option(category, name):
    if category == 'zhange' and name in WEEKLY_BOSSES:
        return f'{WEEKLY_BOSSES[name]}（{name}）'
    return name


def migrated_option(category, position):
    names = SEED_NAMES[category]
    if 1 <= position <= len(names):
        return boss_option(category, names[position - 1])
    return LIST_POSITION


def _read_learned():
    try:
        data = json.loads(LEARNED_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        logger.warning(f'无法读取刷 4C 首领列表：{error}')
        return {}


def known_names(category):
    known = {normalize(name): name for name in SEED_NAMES[category]}
    learned = _read_learned().get(category, [])
    if isinstance(learned, list):
        for name in learned:
            if isinstance(name, str) and (key := normalize(name)):
                known.setdefault(key, name)
    return list(known.values())


def known_options(category):
    return [LIST_POSITION, *(boss_option(category, name) for name in known_names(category))]


def canonical_option(category, name):
    target = normalize(name)
    matches = sorted((distance, item) for item in known_names(category)
                     if (distance := _match_distance(target, normalize(item))) is not None)
    if matches and (len(matches) == 1 or matches[0][0] < matches[1][0]):
        name = matches[0][1]
    return boss_option(category, display_name(name))


def open_category(task, category):
    task.next_frame()
    titles = {WORD_SEPARATOR.sub('', title).casefold() for title in CATEGORY_TITLES[category]}
    text = task.ocr(0.0, 0.10, 0.33, 0.97, name='boss_book_menu') or []
    matches = [box for box in text if WORD_SEPARATOR.sub('', box.name).casefold() in titles]
    if not matches:
        task.open_boss_book(category)
        return
    task.click_box(min(matches, key=lambda box: box.y), after_sleep=2)


@dataclass
class BossRow:
    name: str
    y: float
    button: Box | None
    is_nest: bool


@dataclass
class BossPage:
    rows: list[BossRow]
    signature: tuple
    text_bottom: float

    @property
    def scroll_y(self):
        ys = [row.y for row in self.rows if row.button is not None] or [row.y for row in self.rows]
        return min(0.92, (min(ys) + max(ys)) / 2 + 0.04) if ys else 0.6

    @property
    def scroll_ticks(self):
        ys = [row.y for row in self.rows if row.button is not None]
        if not ys:
            return SCROLL_TICKS
        shown = self.text_bottom - min(ys)
        return max(2, min(SCROLL_TICKS, int((shown - ROW_HEIGHT) / SCROLL_TICK_HEIGHT)))


@dataclass
class ListScan:
    previous_text: list[tuple[str, float]] = field(default_factory=list)
    previous_buttons: tuple[float, ...] = ()
    fixed_y: set[float] = field(default_factory=set)
    scroll_x: float = 0.56

    def note_fixed_text(self, text, button_y):
        if self.previous_buttons and button_y and button_y != self.previous_buttons:
            for label, y in text:
                if any(abs(y - prev_y) <= FIXED_TEXT_TOLERANCE
                       and _edit_distance(label, prev_label) <= max(1, len(label) // 3)
                       for prev_label, prev_y in self.previous_text):
                    self.fixed_y.add(y)
        self.previous_text = text
        self.previous_buttons = button_y


def _read_page(task, scan):
    task.next_frame()
    height = task.height
    texts = task.ocr(*NAME_AREA, name='boss_book_names') or []
    buttons = list(task.find_feature('boss_proceed', box=task.box_of_screen(*BUTTON_AREA), threshold=0.8) or [])
    for text in task.ocr(*BUTTON_AREA, name='boss_book_buttons') or []:
        if BUTTON_TEXT.fullmatch(re.sub(r'\s+', '', text.name)) and not any(
                abs(button.center()[1] - text.center()[1]) / height <= 0.03 for button in buttons):
            buttons.append(text)
    button_y = tuple(sorted(round(box.center()[1] / height, 3) for box in buttons))
    texts = [box for box in texts if not BANNER.search(box.name)]
    progress = [box.y / height for box in texts if PROGRESS.search(box.name)]
    is_chinese = task.game_lang == 'zh_CN'
    candidates = [box for box in texts if not PROGRESS.search(box.name) and (
        len(re.findall(r'[一-鿿]', box.name)) >= 2 or (
            not is_chinese and sum(letter.isalpha() for letter in box.name) >= 3))]
    scan.note_fixed_text([(normalize(box.name), box.y / height) for box in candidates], button_y)
    names = [box for box in candidates if all(abs(box.y / height - y) > FIXED_TEXT_TOLERANCE for y in scan.fixed_y)]
    row_buttons = {}
    for button in buttons:
        y = button.center()[1] / height
        eligible = [i for i, box in enumerate(names) if 0 <= y - box.y / height <= ROW_SPAN]
        if eligible:
            row_buttons[max(eligible, key=lambda i: names[i].y)] = button
    rows = sorted((BossRow(box.name, box.y / height, row_buttons.get(i), '聚落' in box.name or any(
        0.03 <= y - box.y / height <= 0.10 for y in progress)) for i, box in enumerate(names)), key=lambda row: row.y)
    signature = (tuple(round(y, 2) for y in button_y), tuple(normalize(row.name) for row in rows if row.button is not None))
    return BossPage(rows, signature, max((box.y / height for box in texts), default=0.0))


def _scroll(task, scan, page, ticks):
    # The rewards strip can swallow the wheel; try the portrait column too.
    alternate = 0.42 if scan.scroll_x == 0.56 else 0.56
    for x in (scan.scroll_x, alternate):
        task.scroll_relative(x, page.scroll_y, ticks)
        task.sleep(0.6)
        moved = _read_page(task, scan)
        if moved.signature != page.signature:
            scan.scroll_x = x
            return moved
    return page


def _matching_rows(page, wanted, other_names):
    hits = []
    for row in page.rows:
        name = normalize(row.name)
        distance = _match_distance(name, wanted)
        if distance == 0 or (distance is not None and all(_edit_distance(name, other) > distance for other in other_names)):
            hits.append((distance, row))
    return sorted(hits, key=lambda hit: (hit[0], hit[1].y))


def _learn_names(category, seen):
    data = _read_learned()
    known = known_names(category)
    additions = [display_name(name) for key, (name, reads) in seen.items()
                 if reads >= 2 and all(_match_distance(key, normalize(other)) is None for other in known)]
    if additions:
        data[category] = [*known[len(SEED_NAMES[category]):], *additions]
        try:
            LEARNED_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp = LEARNED_FILE.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(LEARNED_FILE)
        except OSError as error:
            logger.warning(f'无法保存刷 4C 首领列表：{error}')
    return additions


def click_boss(task, category, name, position):
    """Click the matching row and return the name actually read from the screen."""
    scan = ListScan()
    page = _read_page(task, scan)
    wanted = normalize(name)
    others = [normalize(n) for n in known_names(category) if normalize(n) != wanted] if wanted else []
    hit = None
    blocked = False
    seen = {}

    if wanted:
        hit = next((row for _, row in _matching_rows(page, wanted, others) if row.button is not None), None)
    if hit is None:
        for _ in range(8):
            earlier = _scroll(task, scan, page, SCROLL_TICKS * 3)
            if earlier.signature == page.signature:
                break
            page = earlier

    budget = 30 * SCROLL_TICKS
    while hit is None:
        for row in page.rows:
            if row.button is None or (category == 'mengyan' and row.is_nest):
                continue
            key = normalize(row.name)
            matched = next((candidate for candidate in seen if _match_distance(key, candidate) is not None), key)
            seen_name, reads = seen.get(matched, (row.name, 0))
            seen[matched] = (seen_name, reads + 1)
        if wanted:
            matches = _matching_rows(page, wanted, others)
            hit = next((row for _, row in matches if row.button is not None), None)
            blocked |= any(row.button is None and any(other.button is not None and other.y > row.y for other in page.rows)
                           for _, row in matches)
        elif 1 <= position <= len(seen):
            selected = list(seen)[position - 1]
            hit = next((row for row in page.rows if row.button is not None and (category != 'mengyan' or not row.is_nest)
                        and _match_distance(normalize(row.name), selected) is not None), None)

        if hit is not None or budget <= 0:
            break
        ticks = min(page.scroll_ticks, budget)
        next_page = _scroll(task, scan, page, -ticks)
        if next_page.signature == page.signature:
            break
        page = next_page
        budget -= ticks

    if task.game_lang == 'zh_CN' and (added := _learn_names(category, seen)):
        task.log_info(task.tr('New bosses found: {names}. Reopen the app to select them.').format(names='、'.join(added)), notify=True)
    if hit is not None:
        task.click_box(hit.button, after_sleep=1)
        return display_name(hit.name)

    label = boss_option(category, name) if name else f'#{position}'
    if blocked:
        raise RuntimeError(task.tr('boss book: {wanted} is in the list but has no Go/Challenge button').format(wanted=label))
    names = '、'.join(boss_option(category, display_name(n)) for n, _ in seen.values())
    raise RuntimeError(task.tr('boss book: {wanted} not found, list has: {names}').format(wanted=label, names=names))
