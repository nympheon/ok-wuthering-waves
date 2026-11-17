# Intel integrated GPU OCR implementation plan

> **For agentic workers:** Implement this small change inline; review the completed implementation before finishing. No TDD is required by this project's AGENTS.md.

**Goal:** Use only the local Intel integrated GPU for dynamic-shape OCR, falling back directly to dynamic-shape CPU, and log the actual backend at startup.

**Architecture:** Add a project-owned ONNXPaddleOcr subclass, preserving the installed detector/recognizer preprocessing, asynchronous inference, and decoding. Install it through the existing onnxocr factory import when project config loads; do not edit site-packages. Discover the Intel integrated adapter by properties on every startup rather than persisting a GPU index or driver version.

**Tech Stack:** Python 3.14, onnxocr-ppocrv6 0.0.1, OpenVINO 2026.4.1, project-local .venv.

**Spec:** The user's current request: fixed integrated GPU (never discrete), dynamic inputs, builder-selected fallback, and one clear startup status log; frequent driver upgrades must be supported.

## Constraints and decisions

- Only GPU devices whose type is INTEGRATED and whose full name identifies Intel are eligible. Never compile OCR for a generic GPU alias, AUTO, MULTI, HETERO, NVIDIA, or NPU.
- Use CPU fallback: this machine's offline tests found it faster than NPU and it preserves dynamic inputs and batch recognition.
- Verify both compiled execution devices before inference. Smoke-test initialization; on GPU initialization or inference RuntimeError, rebuild both models on CPU and report why.
- Keep library model cache handling, one asynchronous request per component, and the CPU runtime shape cache limit of 16. Do not pin GPU driver versions or GPU ordinal IDs.
- Do not launch the game. No application restart is needed to validate offline; the next normal application startup loads the new backend.
- Work in the authorized local checkout to keep this machine's .venv, model files, and startup path together; do not change git integration state.

## Implementation and checks

- [x] Add src/ocr.py: integrated-adapter selection, dynamic detector/recognizer construction, GPU-to-CPU recovery, one startup summary, and idempotent factory installation.
- [x] Wire installation and disable NPU in config.py.
- [x] Add meaningful regression checks for adapter order changes, all-discrete/absent GPU, compile/self-test failure, actual execution device mismatch, runtime recovery, and once-only startup summary.
- [x] Run those checks with .venv, then exercise the real TaskExecutor OCR factory against the existing nine saved-image scenarios, confirming actual integrated GPU execution, dynamic shapes, and startup log output.
- [x] Exercise real CPU fallback with the adapter unavailable to the selector, preserving real CPU inference and existing saved-image targets.
- [x] Run affected existing screenshot/config/startup checks, inspect the diff, and record results.

## Review focus

Driver-updated GPU numbering must not select the discrete card. Unsupported adapter metadata must skip that candidate. GPU fallback must replace both models together, serialize recovery with OCR calls, preserve the original error in logs, and never report GPU success after switching to CPU.

## Validation results

- `python -X utf8 -m unittest discover -s tests -p TestOCRBackend.py -v`: 11 tests passed, including real OpenVINO asynchronous success/error tests. No game or app launch.
- `scripts/validate_ocr_backend.py` (initially exercised from local cache): real background TaskExecutor startup used GPU.0 Intel Graphics, detector [?,3,?,?] and recognizer [?,3,48,?]. Normal startup, injected GPU runtime failure with real CPU recovery, and unavailable-adapter startup with real CPU fallback each recognized all 31 selected targets across nine saved-image cases. Startup status was emitted once per engine; runtime recovery emitted one transition warning.
- Existing tests: TestConfig (5), TestSourceStartup (3), and TestCD (1 test with four saved screenshots) all passed.
- Independent review found the inherited callback-only wait would hang on native asynchronous errors. The project override now calls AsyncInferQueue.wait_all(), surfacing those errors without waiting on a skipped Python callback. Real CPU reshape-error regression verified the fix; reviewer reran all 11 tests and reported no remaining actionable findings.
- Installed package source was unchanged. The next normal application startup loads this project-owned backend; no game was started during validation.
- Durable policy, compatibility notes, benchmark context, and reproduction commands are in `docs/ocr.md`.
- Pre-push verification: `run_tests.ps1` passed all 556 tests across 59 modules. The tracked `scripts/validate_ocr_backend.py` also passed all three real-inference paths with 31/31 selected targets each.
