"""Local OCR policy: Intel integrated graphics with dynamic inputs, then CPU."""

import threading
from pathlib import Path

import cv2
import openvino as ov
from onnxocr import onnx_paddleocr
from onnxocr.onnx_paddleocr import ONNXPaddleOcr
from onnxocr.predict_base import PredictBase
from onnxocr.predict_det import TextDetector
from onnxocr.predict_rec import TextRecognizer


def select_intel_igpu(core):
    """GPU ordinals can change after a driver update; check adapter identity."""
    rejected = []
    for index in core.get_property('GPU', 'AVAILABLE_DEVICES'):
        device = f'GPU.{index}'
        try:
            name = core.get_property(device, 'FULL_DEVICE_NAME')
            kind = core.get_property(device, 'DEVICE_TYPE')
        except RuntimeError as error:
            rejected.append(f'{device}: {error}')
            continue
        if kind == ov.properties.device.Type.INTEGRATED and 'intel' in name.casefold():
            return device, name
        rejected.append(f'{device}: {name}, {kind}')
    raise RuntimeError('；'.join(['未找到可用的 Intel 核显', *rejected]))


class _DynamicPredictor(PredictBase):
    def __init__(self, model_dir, use_openvino=True, use_npu=False, logger=None,
                 force_static_shape=False, openvino_num_requests=1,
                 openvino_cpu_cache_capacity=16):
        # Keep the library's asynchronous run/decoding path, replacing only its
        # NPU/CPU-only compilation policy. Never pass GPU/AUTO/MULTI/HETERO.
        self.is_openvino = True
        self.is_npu = False
        self.force_shape = None
        self.model_dir = str(model_dir)
        self.logger = logger
        model = self._core.read_model(self.model_dir)
        if not model.inputs[0].partial_shape.is_dynamic:
            raise RuntimeError(f'OCR 模型必须支持动态输入：{model_dir}')
        options = {'PERFORMANCE_HINT': 'LATENCY'}
        if self._device == 'CPU':
            options['CPU_RUNTIME_CACHE_CAPACITY'] = str(openvino_cpu_cache_capacity)
        self.session = self._core.compile_model(model, self._device, options)
        actual = self.session.get_property('EXECUTION_DEVICES')
        actual = [actual] if isinstance(actual, str) else list(actual)
        if actual != [self._device]:
            raise RuntimeError(f'OCR 执行设备不匹配，指定设备 {self._device}，实际设备 {actual}')
        self._async_queue = ov.AsyncInferQueue(self.session, jobs=openvino_num_requests)
        self._async_submit_lock = threading.Lock()
        self._async_queue.set_callback(self._on_openvino_complete)

    def _run_openvino_async(self, input_feed):
        job = {'done': threading.Event(), 'outputs': None, 'error': None}
        with self._async_submit_lock:
            self._async_queue.start_async(input_feed, userdata=job, share_inputs=False)
            # A failed native inference skips the Python callback. Waiting on
            # its Event would hang forever; wait_all surfaces the native error.
            self._async_queue.wait_all()
        if job['error'] is not None:
            raise RuntimeError('读取 OpenVINO OCR 输出失败') from job['error']
        return job['outputs']


# The library constructors' super() calls reach our compilation policy, while
# their preprocessing and recognition implementations stay unchanged.
class _Detector(TextDetector, _DynamicPredictor):
    def __init__(self, args, core, device):
        self._core, self._device = core, device
        super().__init__(args)


class _Recognizer(TextRecognizer, _DynamicPredictor):
    def __init__(self, args, core, device):
        self._core, self._device = core, device
        super().__init__(args)


class IntelGpuOCR(ONNXPaddleOcr):
    def __init__(self, logger=None, **kwargs):
        self._backend_lock = threading.RLock()
        self.fallback_reason = 'none'
        kwargs.update(use_openvino=True, use_npu=False, use_angle_cls=False)
        super().__init__(logger=logger, **kwargs)
        self._log_backend('OCR 后端已就绪')

    def _initialize_models(self, params):
        self.args = params
        self.use_angle_cls = False
        self.drop_score = params.drop_score
        self.crop_image_res_index = 0
        self._core = ov.Core()
        cache = Path.cwd() / 'cache' / 'openvino' / 'ocr-intel'
        cache.mkdir(parents=True, exist_ok=True)
        # OpenVINO owns compiled-cache compatibility checks, including drivers.
        self._core.set_property({'CACHE_DIR': str(cache)})
        try:
            device, name = select_intel_igpu(self._core)
            self._load_models(device, name)
            self._smoke_test()
        except RuntimeError as error:
            self.fallback_reason = ' '.join(str(error).split())
            self._load_cpu()

    def _load_models(self, device, name):
        detector = _Detector(self.args, self._core, device)
        recognizer = _Recognizer(self.args, self._core, device)
        self.text_detector, self.text_recognizer = detector, recognizer
        self.device, self.device_name = device, name

    def _load_cpu(self):
        self._load_models('CPU', self._core.get_property('CPU', 'FULL_DEVICE_NAME'))
        self._smoke_test()

    def _smoke_test(self):
        frame = self._npu_test_frame()
        for image in (frame, cv2.resize(frame, (320, 80))):
            result = ONNXPaddleOcr.ocr(self, image)
            texts = ''.join(text for _, (text, _) in result[0]).casefold()
            if 'okscript' not in texts:
                raise RuntimeError(f'OCR 后端自检失败：{texts!r}')

    def _log_backend(self, event):
        shapes = ', '.join(
            f'{label}={component.session.inputs[0].partial_shape}'
            for label, component in (('det', self.text_detector), ('rec', self.text_recognizer))
        )
        is_fallback = self.fallback_reason != 'none'
        level = self.logger.warning if is_fallback else self.logger.info
        reason = self.fallback_reason if is_fallback else '无'
        level(f'{event} | 设备={self.device} | 名称={self.device_name} | 输入=动态 '
              f'({shapes}) | 回退设备=CPU | 独立显卡=禁止 | NPU=禁用 '
              f'| 自检=通过 | OpenVINO={ov.__version__} | 回退原因={reason}')

    def ocr(self, *args, **kwargs):
        # Notification and task callers may overlap; switch both models together
        # and retry only once after a GPU inference failure.
        with self._backend_lock:
            try:
                return super().ocr(*args, **kwargs)
            except RuntimeError as error:
                if self.device == 'CPU':
                    raise
                self.fallback_reason = ' '.join(str(error).split())
                self._load_cpu()
                self._log_backend('OCR 后端已切换至 CPU')
                return super().ocr(*args, **kwargs)


def install_ocr_backend():
    """Use the normal framework factory without editing installed packages."""
    onnx_paddleocr.ONNXPaddleOcr = IntelGpuOCR
