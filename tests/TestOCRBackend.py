import unittest
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from src import ocr


INTEGRATED = ocr.ov.properties.device.Type.INTEGRATED
DISCRETE = ocr.ov.properties.device.Type.DISCRETE


class Port:
    def __init__(self, name, shape):
        self.name, self.partial_shape = name, shape

    def get_any_name(self):
        return self.name


class FakeCore:
    def __init__(self, adapters=None, fail_device=None, wrong_execution=None):
        self.adapters = adapters if adapters is not None else {
            '0': ('NVIDIA GeForce RTX 5080', DISCRETE),
            '1': ('Intel(R) Graphics (iGPU)', INTEGRATED),
        }
        self.fail_device = fail_device
        self.wrong_execution = wrong_execution
        self.compiled = []

    def set_property(self, values):
        pass

    def get_property(self, device, prop):
        if device == 'GPU' and prop == 'AVAILABLE_DEVICES':
            return list(self.adapters)
        if device == 'CPU' and prop == 'FULL_DEVICE_NAME':
            return 'Intel Core Ultra 9 285K'
        name, kind = self.adapters[device.split('.', 1)[1]]
        if kind is None:
            raise RuntimeError('adapter metadata unavailable after driver update')
        return name if prop == 'FULL_DEVICE_NAME' else kind

    def read_model(self, path):
        shape = [-1, 3, 48, -1] if 'rec' in path else [-1, 3, -1, -1]
        return SimpleNamespace(inputs=[Port('input', ocr.ov.PartialShape(shape))])

    def compile_model(self, model, device, options):
        self.compiled.append((device, options))
        if device == self.fail_device:
            raise RuntimeError('GPU compilation failed')
        actual = self.wrong_execution if device.startswith('GPU.') and self.wrong_execution else device
        return SimpleNamespace(
            inputs=model.inputs, outputs=[Port('output', None)],
            get_property=lambda prop: [actual] if prop == 'EXECUTION_DEVICES' else None,
        )


@contextmanager
def fake_backend(core, smoke_effect=None):
    with patch.object(ocr.ov, 'Core', return_value=core), \
            patch.object(ocr.ov, 'AsyncInferQueue', return_value=Mock()), \
            patch.object(ocr.IntelGpuOCR, '_smoke_test', side_effect=smoke_effect) as smoke:
        yield smoke


class TestOCRBackend(unittest.TestCase):
    def make_reshape_predictor(self):
        from openvino import opset16 as ops
        data = ops.parameter([-1], dtype=np.float32, name='data')
        shape = ops.parameter([2], dtype=np.int64, name='shape')
        model = ocr.ov.Model([ops.reshape(data, shape, False)], [data, shape])
        compiled = ocr.ov.Core().compile_model(model, 'CPU')
        predictor = ocr._DynamicPredictor.__new__(ocr._DynamicPredictor)
        predictor._async_queue = ocr.ov.AsyncInferQueue(compiled, jobs=1)
        predictor._async_submit_lock = threading.Lock()
        predictor._async_queue.set_callback(predictor._on_openvino_complete)
        return predictor

    def test_real_async_execution_error_raises_even_when_callback_is_skipped(self):
        predictor = self.make_reshape_predictor()
        with self.assertRaises(RuntimeError):
            predictor._run_openvino_async({
                'data': np.zeros(6, dtype=np.float32),
                'shape': np.array([2, 4], dtype=np.int64),
            })

    def test_real_async_execution_returns_owned_outputs(self):
        predictor = self.make_reshape_predictor()
        outputs = predictor._run_openvino_async({
            'data': np.arange(6, dtype=np.float32),
            'shape': np.array([2, 3], dtype=np.int64),
        })
        np.testing.assert_array_equal(outputs[0], np.arange(6).reshape(2, 3))

    def test_gpu_order_change_still_selects_intel_integrated_only(self):
        core, logger = FakeCore(), Mock()
        with fake_backend(core):
            engine = ocr.IntelGpuOCR(logger=logger, use_npu=True)
        self.assertEqual(engine.device, 'GPU.1')
        self.assertEqual([device for device, _ in core.compiled], ['GPU.1', 'GPU.1'])
        self.assertIsNone(engine.text_detector.force_shape)
        self.assertIsNone(engine.text_recognizer.force_shape)
        self.assertTrue(engine.text_detector.session.inputs[0].partial_shape.is_dynamic)
        self.assertTrue(engine.text_recognizer.session.inputs[0].partial_shape.is_dynamic)
        summaries = [str(call) for call in logger.info.call_args_list if 'OCR 后端已就绪' in str(call)]
        self.assertEqual(len(summaries), 1)
        self.assertIn('独立显卡=禁止', summaries[0])
        self.assertIn('输入=动态', summaries[0])

    def test_discrete_or_non_intel_integrated_adapter_is_never_compiled(self):
        for adapters in ({'0': ('NVIDIA GeForce RTX 5080', DISCRETE)},
                         {'0': ('Intel Arc discrete', DISCRETE)},
                         {'0': ('Other integrated graphics', INTEGRATED)}, {}):
            with self.subTest(adapters=adapters):
                core, logger = FakeCore(adapters), Mock()
                with fake_backend(core):
                    engine = ocr.IntelGpuOCR(logger=logger)
                self.assertEqual(engine.device, 'CPU')
                self.assertEqual([device for device, _ in core.compiled], ['CPU', 'CPU'])
                self.assertIn('未找到可用的 Intel 核显', engine.fallback_reason)
                self.assertEqual(core.compiled[0][1]['CPU_RUNTIME_CACHE_CAPACITY'], '16')
                self.assertEqual(sum('OCR 后端已就绪' in str(c) for c in logger.warning.call_args_list), 1)

    def test_unreadable_adapter_identity_is_skipped(self):
        core = FakeCore({'0': ('Unknown', None), '3': ('Intel Graphics updated name', INTEGRATED)})
        with fake_backend(core):
            engine = ocr.IntelGpuOCR(logger=Mock())
        self.assertEqual(engine.device, 'GPU.3')
        self.assertEqual([device for device, _ in core.compiled], ['GPU.3', 'GPU.3'])

    def test_gpu_compilation_failure_falls_back_to_cpu(self):
        core = FakeCore(fail_device='GPU.1')
        with fake_backend(core):
            engine = ocr.IntelGpuOCR(logger=Mock())
        self.assertEqual(engine.device, 'CPU')
        self.assertIn('GPU compilation failed', engine.fallback_reason)
        self.assertEqual([device for device, _ in core.compiled], ['GPU.1', 'CPU', 'CPU'])

    def test_execution_device_mismatch_is_rejected_before_inference(self):
        core = FakeCore(wrong_execution='GPU.0')  # GPU.0 is the NVIDIA card.
        with fake_backend(core) as smoke:
            engine = ocr.IntelGpuOCR(logger=Mock())
        self.assertEqual(engine.device, 'CPU')
        self.assertIn('OCR 执行设备不匹配', engine.fallback_reason)
        smoke.assert_called_once_with()  # Only CPU reached the inference test.

    def test_gpu_self_test_failure_rebuilds_both_models_on_cpu(self):
        core = FakeCore()
        with fake_backend(core, [RuntimeError('GPU inference failed'), None]) as smoke:
            engine = ocr.IntelGpuOCR(logger=Mock())
        self.assertEqual(engine.device, 'CPU')
        self.assertEqual(smoke.call_count, 2)
        self.assertEqual([device for device, _ in core.compiled], ['GPU.1', 'GPU.1', 'CPU', 'CPU'])

    def test_runtime_gpu_failure_switches_once_then_keeps_cpu(self):
        core, logger = FakeCore(), Mock()
        expected = [['recognized result']]
        with fake_backend(core):
            engine = ocr.IntelGpuOCR(logger=logger)
            with patch.object(ocr.ONNXPaddleOcr, 'ocr', side_effect=[RuntimeError('device lost'), expected, expected]):
                self.assertEqual(engine.ocr('image'), expected)
                self.assertEqual(engine.ocr('image'), expected)
        self.assertEqual(engine.device, 'CPU')
        self.assertEqual([device for device, _ in core.compiled], ['GPU.1', 'GPU.1', 'CPU', 'CPU'])
        self.assertEqual(sum('OCR 后端已就绪' in str(c) for c in logger.info.call_args_list), 1)
        self.assertEqual(sum('OCR 后端已切换至 CPU' in str(c) for c in logger.warning.call_args_list), 1)

    def test_cpu_runtime_error_propagates_without_repeated_fallback(self):
        core = FakeCore({})
        with fake_backend(core):
            engine = ocr.IntelGpuOCR(logger=Mock())
            with patch.object(ocr.ONNXPaddleOcr, 'ocr', side_effect=RuntimeError('bad input')):
                with self.assertRaisesRegex(RuntimeError, 'bad input'):
                    engine.ocr('image')
        self.assertEqual([device for device, _ in core.compiled], ['CPU', 'CPU'])

    def test_project_config_installs_backend_in_real_framework_factory(self):
        from config import config
        from ok.task.TaskExecutor import TaskExecutor
        core = FakeCore()
        ocr.install_ocr_backend()
        ocr.install_ocr_backend()
        self.assertIs(ocr.onnx_paddleocr.ONNXPaddleOcr, ocr.IntelGpuOCR)
        self.assertFalse(config['ocr']['params']['use_npu'])
        executor = TaskExecutor.__new__(TaskExecutor)
        executor.config = {'ocr': {'default': config['ocr']}}
        with fake_backend(core):
            engine = executor._create_ocr_lib('default')
        self.assertIsInstance(engine, ocr.IntelGpuOCR)
        self.assertEqual(engine.device, 'GPU.1')


if __name__ == '__main__':
    unittest.main()
