"""Check actual OCR startup and CPU recovery using saved images, without a game."""

import json
import logging
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2

from config import config
from ok.task.TaskExecutor import TaskExecutor
from src import ocr


# Human-read targets, fixed before testing. Selected-text recall is not full
# character accuracy; graphics/icons can still produce additional OCR results.
CASES = [
    ('cooldowns', 'all_cd_1080p.png', (.80, .855, .98, .93), ['13.6', '18.4', '22.6']),
    ('quest', 'all_cd_1080p.png', (.03, .24, .32, .49),
     ['我们的故事才刚刚开始', '前往攻略', '12754米']),
    ('echo_stats', 'echo_enhance.png', (.68, .38, .96, .48), ['攻击', '生命', '3.6%', '456']),
    ('echo_skill', 'echo_enhance.png', (.675, .50, .96, .71),
     ['声骸技能', '合鸣效果', '长路启航之星', '热熔伤害提升']),
    ('echo_button', 'echo_enhance.png', (.82, .86, .97, .96), ['培养']),
    ('map_currency', 'teleport_boss.png', (.47, .025, .86, .09), ['0/6000', '246', '60/240']),
    ('map_button', 'teleport_boss.png', (.76, .90, .91, .96), ['切换地图']),
    ('map_full', 'teleport_boss.png', (0, 0, 1, 1), ['天槎空间站', '切换地图', '0/6000', '246', '60/240']),
    ('echo_full', 'echo_enhance.png', (0, 0, 1, 1), ['声骸', '2295/3000', '攻击', '生命', '3.6%', '456', '培养']),
]


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def load_cases():
    cases = []
    for name, filename, region, expected in CASES:
        image = cv2.imread(str(ROOT / 'tests' / 'images' / filename))
        assert image is not None, filename
        h, w = image.shape[:2]
        x1, y1, x2, y2 = [int(value * (w if index % 2 == 0 else h))
                          for index, value in enumerate(region)]
        cases.append((name, image[y1:y2, x1:x2].copy(), expected))
    return cases


def startup(expected, capture):
    capture.messages.clear()
    executor = TaskExecutor(SimpleNamespace(), exit_event=threading.Event(),
                            global_config=SimpleNamespace(get_config=lambda name: {}),
                            config={'ocr': {'lib': config['ocr']['lib'],
                                            'params': dict(config['ocr']['params'])}})
    executor._ocr_init_thread.join(45)
    assert not executor._ocr_init_thread.is_alive(), 'OCR startup did not finish'
    assert 'default' in executor._ocr_lib, 'OCR startup failed; see preceding logs'
    engine = executor.ocr_lib()
    assert engine.device == expected, engine.device
    for component in [engine.text_detector, engine.text_recognizer]:
        actual = component.session.get_property('EXECUTION_DEVICES')
        actual = [actual] if isinstance(actual, str) else list(actual)
        assert actual == [expected], actual
        assert component.session.inputs[0].partial_shape.is_dynamic
        assert component.force_shape is None
    summaries = [message for message in capture.messages if 'OCR 后端已就绪' in message]
    assert len(summaries) == 1, summaries
    return engine, summaries[0]


def clean(text):
    return ''.join(text.split()).replace('％', '%').replace('／', '/')


def check_images(engine, cases):
    report = []
    for name, image, expected in cases:
        result = engine.ocr(image)
        rows = [text for _, (text, _) in result[0]]
        texts = clean(''.join(rows))
        missing = [target for target in expected if clean(target) not in texts]
        assert not missing, (name, missing, rows)
        report.append(dict(name=name, hits=len(expected), texts=rows))
    assert sum(case['hits'] for case in report) == 31
    return report


def main():
    capture = Capture()
    logger = logging.getLogger('ok')
    logger.addHandler(capture)
    try:
        report, cases = {}, load_cases()
        selected, selected_name = ocr.select_intel_igpu(ocr.ov.Core())
        engine, summary = startup(selected, capture)
        assert 'intel' in selected_name.casefold()
        report['normal_startup'] = dict(device=engine.device, summary=summary, cases=check_images(engine, cases))

        # Only inject the GPU error. Recovery compiles and runs real CPU models.
        with patch.object(engine.text_detector, '_run_openvino_async', side_effect=RuntimeError('validation: GPU device lost')):
            runtime_cases = check_images(engine, cases)
        assert engine.device == 'CPU'
        assert sum('OCR 后端已就绪' in message for message in capture.messages) == 1
        assert sum('OCR 后端已切换至 CPU' in message for message in capture.messages) == 1
        report['runtime_gpu_failure'] = dict(device=engine.device, reason=engine.fallback_reason, cases=runtime_cases)

        with patch('src.ocr.select_intel_igpu', side_effect=RuntimeError('validation: integrated adapter unavailable')):
            fallback, summary = startup('CPU', capture)
        report['gpu_unavailable_startup'] = dict(device=fallback.device, summary=summary, cases=check_images(fallback, cases))

        output = ROOT / 'cache' / 'ocr-validation' / 'installed-backend-validation.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('通过：Intel 核显使用动态输入的检测和识别模型，仅输出一条启动摘要，命中 31/31 项。')
        print('通过：模拟 GPU 设备丢失后，使用 CPU 模型恢复识别，命中 31/31 项，仅输出一条切换日志。')
        print('通过：核显不可用时，启动时回退至 CPU 并记录原因，命中 31/31 项。')
        print(f'验证结果已写入 {output}')
    finally:
        logger.removeHandler(capture)


if __name__ == '__main__':
    main()
