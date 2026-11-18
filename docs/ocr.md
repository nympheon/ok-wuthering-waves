# 本机 OCR 配置与维护

## 当前策略

OCR 固定优先使用 **Intel 核显＋动态输入**，核显不可用、初始化自检失败或推理抛出 `RuntimeError` 时，整体切换为 **CPU＋动态输入**。运行中发生错误后只重试当前请求一次，随后保持 CPU，重启程序才重新尝试核显。

**禁止 OCR 使用 NVIDIA 独显，也不回退 NPU。** 本机 CPU 对照组更快，且 CPU 可以保留动态输入；NPU 原路径需要固定尺寸和逐条识别。

选择核显时，每次启动重新查询 OpenVINO GPU 列表，仅接受 `DEVICE_TYPE=INTEGRATED` 且 `FULL_DEVICE_NAME` 包含 Intel 的设备。不要固定 `GPU.0`：显卡驱动升级后编号可能变化。本次验证核显为 `GPU.0`，RTX 5080 为 `GPU.1`，这些编号只是当前观测值。

编译时传入核验后的明确设备 ID 或 `CPU`，不使用 `GPU`、`AUTO`、`MULTI`、`HETERO`。检测、识别模型的 `EXECUTION_DEVICES` 必须与选择一致，自检通过后才报告就绪。驱动查询或设备身份读取失败时使用 CPU，不猜测其他显卡。

## 代码入口与依赖边界

- [`config.py`](../config.py)：导入并安装本地 OCR 后端，保留 `use_openvino=True`，设置 `use_npu=False`。
- [`src/ocr.py`](../src/ocr.py)：`select_intel_igpu()` 选择设备；`IntelGpuOCR` 管理初始化、回退与状态日志；`_DynamicPredictor` 编译动态模型并处理异步结果。
- [`tests/TestOCRBackend.py`](../tests/TestOCRBackend.py)：显卡编号变化、独显拒绝、初始化及运行失败、异步原生错误和日志次数的回归测试。
- [`scripts/validate_ocr_backend.py`](../scripts/validate_ocr_backend.py)：不启动游戏，验证真实框架后台初始化、真实模型识别与 CPU 回退。

本地类替换 `onnxocr.onnx_paddleocr.ONNXPaddleOcr`，供 `TaskExecutor._create_ocr_lib()` 的正常导入使用。模型和算法仍来自安装的 onnxocr 包，**没有修改 site-packages**。`_Detector`、`_Recognizer` 的继承顺序使库构造函数的 `super()` 进入本地编译策略，预处理、裁剪、解码仍复用库实现。

开发时的依赖为 Python 3.14.10、ok-script 3.0.5、onnxocr-ppocrv6 0.0.1、OpenVINO 2026.4.1；安装版本以项目锁文件为准。升级依赖时，重点检查以下接口是否仍兼容：

1. `TaskExecutor._create_ocr_lib()` 是否仍从上述模块导入 OCR 类。
2. `ONNXPaddleOcr._initialize_models()`、`TextDetector`／`TextRecognizer` 构造参数及 `PredictBase.run()` 的接口。
3. OpenVINO 的设备属性、`EXECUTION_DEVICES` 返回值及 `AsyncInferQueue` 的错误行为。

不要把本地 `_run_openvino_async()` 改回只等待 Python 回调事件。OpenVINO 原生异步推理失败时可能不调用 Python 回调，必须用 `wait_all()` 暴露错误，否则会卡住并阻止 CPU 回退。测试中的真实 CPU reshape 错误覆盖了这条路径。

检测输入保留 `[?,3,?,?]`，识别输入保留 `[?,3,48,?]`，不添加 NPU 的固定尺寸适配。每个组件使用一个异步请求；CPU 动态形状运行缓存上限保留为 16。编译缓存位于 `cache/openvino/ocr-intel/`，兼容性检查交给 OpenVINO，不硬编码驱动版本。

## 启动检查与故障定位

正常启动在 `logs/echodesk.log` 搜索 `OCR 后端已就绪`。测试运行器通常写 `logs/ok-script.log`。

```text
OCR 后端已就绪 | 设备=GPU.0 | 名称=Intel(R) Graphics (iGPU) | 输入=动态 (det=[?,3,?,?], rec=[?,3,48,?]) | 回退设备=CPU | 独立显卡=禁止 | NPU=禁用 | 自检=通过 | ... | 回退原因=无
```

每个 OCR 实例启动只输出一次这条摘要。若启动时已回退，摘要是 WARNING，`设备=CPU`，`回退原因` 给出原因。运行中回退则另外输出一次 `OCR 后端已切换至 CPU`。

更新驱动后，先确认摘要中的设备全名和 `输入=动态`；编号变化本身不是故障。若回退，检查 `回退原因` 中的驱动、设备、模型编译或自检错误。没有 Intel 核显可用时，CPU 是预期结果，不能通过移除集成显卡检查或改为泛指 `GPU` 来恢复。

## 复现验证

从仓库根目录使用本地虚拟环境运行，不需要启动游戏：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p TestOCRBackend.py -v
.\.venv\Scripts\python.exe -X utf8 scripts/validate_ocr_backend.py
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -X utf8 run_test.py tests/TestCD.py
```

第一条是后端回归测试，不要求存在可用核显。第二条要求本机 Intel 核显可用，测试真实 GPU 路径，以及注入“核显不可用”和“GPU 设备丢失”后使用真实 CPU 模型恢复。只模拟故障入口，不模拟识别结果。它复用仓库中 3 张截图、9 个场景的 31 个预先标注关键文本，报告写入被 Git 忽略的 `cache/ocr-validation/`。关键文本全命中不等同于完整字符准确率。

2026-11-18 提交前运行 `run_tests.ps1`：59 个测试模块、556 项测试全部通过；上述独立验证脚本的正常核显、运行中回退 CPU、启动回退 CPU 三条路径均命中 31/31 个关键文本。

## 2026-11-18 本机离线对照

硬件：Core Ultra 9 285K（24 核）、Intel Graphics 核显、RTX 5080。测试使用同一 PP-OCRv6 small 模型、相同 9 个场景；预热后每组连续识别约 15 秒，以 0.2 秒间隔采样独立 OCR 进程的资源，GPU 计数器按实际进程 PID 和 Intel 适配器 LUID 过滤。

| 指标 | 核显动态输入 | CPU 动态输入 |
| --- | ---: | ---: |
| 平均 OCR 耗时 | 105.8 ms | 59.3 ms |
| 整机 CPU 平均／峰值 | 12.7%／18.3% | 47.0%／83.0% |
| 每次 OCR 累计 CPU 时间 | 322 ms | 669 ms |
| 进程工作集平均／峰值 | 1.42／1.48 GiB | 0.60／0.65 GiB |
| 核显 Compute 引擎平均／峰值 | 87.5%／100% | 0% |
| 核显共享显存平均／峰值 | 596／615 MiB | 0 |
| 关键文本命中 | 31/31 | 31/31 |

CPU 百分比以 24 个逻辑处理器总算力为 100%；持续跑满时两组吞吐不同，比较相同识别次数的 CPU 开销应看累计 CPU 时间。共享显存来自系统内存，不能与进程工作集简单相加。停止识别后观察 5 秒，末尾两组 CPU／GPU 活动均接近 0，模型缓存仍保留。

这些数据是选择核显以保留游戏 CPU 余量的依据，不是功耗或游戏帧率测量。测试没有启动游戏，也没有验证长时间内存增长。数据在切换为当前项目后端前取得；修改等待方式、依赖或驱动后应重新测量，不能当作性能保证。
