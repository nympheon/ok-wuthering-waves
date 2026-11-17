# Stable dependency and Python upgrade

Goal: use the latest stable dependencies that preserve EchoDesk's behavior, then switch to Python 3.14.10 after validation. Initially keep changes local; the user approved pushing to origin/master after manual acceptance on 2026-11-18.

Approach: retain the upstream ok-script wheel and declare the project's explicit pycaw/pywin32 overrides. Use one reproducible uv installation workflow for local setup and CI. Preserve the original Python 3.12 environment until the candidate environment passes.

Constraints: preserve pre-existing src/identity.py and scripts changes; no TDD requirement; no unrelated gameplay changes; hardware target is this PC; use administrator rights for real audio/capture validation as needed.

- [x] Record installed baseline and run every existing test module on Python 3.12: 57 modules, 538 tests passed.
- [x] Pin stable framework release, add reviewed dependency overrides, regenerate runtime and development locks, and make installer/CI/update paths consume the same policy.
- [x] Install project-local CPython 3.14.10 and a separate candidate virtual environment with all latest stable dependencies.
- [x] Run the complete existing suite: 58 modules / 543 tests passed. Administrator validation passed for real GUI startup, 12 registered tasks, MCP skill/task tools, NPU detection and recognition, audio enumeration and unchanged-mute writes, WGC/BitBlt capture and PostMessage typing/clicks on owned test widgets. No running game was available for combat validation.
- [x] Switch .venv only after the candidate passes; original environment retained at cache/dependency-upgrade/venv312-backup. Final launcher and policy verification follow.
- [x] Independent review completed; both findings fixed and verified. Final installation is idempotent, all 61 locked dependencies pass policy checks, all 20 upgraded packages match the audited latest stable versions, desktop startup preflight passes, and updater PowerShell parses. No commit or remote push was performed.

Verification focus: framework's original metadata exclusions, MFC dependency for pywin32 312, Pillow 13 image operations, Python 3.14 native extensions and OCR shutdown, updater/CI dependency reproducibility.

Progress: first candidate run completed 58 modules / 543 tests with one failure. The failing switch-selection test assigned equal 13-second buff lifetimes using separate real-clock calls; Python 3.14 consistently exposed the ambiguous ordering. Make its intended lowest-buff comparison distinct (12 vs 13 seconds), preserving production combat behavior. Sandbox NPU-driver enumeration warnings also occur in the baseline; validate NPU under administrator rights.

Review: independent review identified two validation gaps. Installer/checker now reject a Python version different from .python-version before dependency changes; checker propagates transitive extras before validating metadata. All 11 focused installer/policy tests pass. Per the user's follow-up, avoid further low-risk package tests and redundant full-suite runs.

Final environment: .venv uses Python 3.14.10 from the persistent ignored python/cpython-3.14.10-windows-x86_64-none directory, so ordinary cache cleanup does not remove its interpreter. Dependency installation, policy validation, pip/uv entry points and the existing desktop launcher's CheckOnly mode all pass after the move. Existing user changes remain intact; working branch is codex/dependency-upgrade-python314. Live game combat remains unverified because the game was not running.

Acceptance: the user subsequently enabled Script/Templates by default, requested manual game launch only, and enabled automatic game-window resizing in their local settings. The user confirmed their manual checks passed and authorized pushing all related changes to their repository's master branch. Local account/configuration files and interpreter/cache directories remain untracked.
