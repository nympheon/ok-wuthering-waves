import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch


SCRIPT = Path(__file__).resolve().parents[1] / '.github/scripts/install_dependencies.py'
spec = importlib.util.spec_from_file_location('install_dependencies', SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class TestInstallDependencies(unittest.TestCase):
    def setUp(self):
        self.python_version = patch.object(installer.sys, 'version_info', (3, 14, 10))
        self.python_version.start()
        self.addCleanup(self.python_version.stop)

    def test_wrong_python_does_not_change_dependencies(self):
        with patch.object(installer.sys, 'version_info', (3, 12, 6)), \
                patch.object(installer, 'pip_install') as install, \
                patch.object(installer.subprocess, 'run') as run:
            self.assertEqual(1, installer.main())
        install.assert_not_called()
        run.assert_not_called()

    def test_retries_transient_index_failure_without_cache(self):
        with patch.object(installer.subprocess, 'run', side_effect=[
            subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0),
        ]) as run, patch.object(installer.time, 'sleep') as sleep:
            self.assertEqual(0, installer.pip_install(['ok-script==3.0.0'], attempts=3))
        command = [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', 'ok-script==3.0.0']
        self.assertEqual([call(command), call(command)], run.call_args_list)
        sleep.assert_called_once_with(30)

    def test_returns_failure_after_bounded_attempts(self):
        with patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)) as run, \
                patch.object(installer.time, 'sleep') as sleep:
            self.assertEqual(7, installer.pip_install(['missing-package'], attempts=3))
        self.assertEqual(3, run.call_count)
        self.assertEqual(2, sleep.call_count)

    def test_does_not_continue_after_bootstrap_fails(self):
        with patch.object(installer.metadata, 'version', side_effect=installer.metadata.PackageNotFoundError), \
                patch.object(installer, 'pip_install', return_value=1) as install, \
                patch.object(installer.subprocess, 'run') as run:
            self.assertEqual(1, installer.main())
        install.assert_called_once_with(['uv==0.13.9'])
        run.assert_not_called()

    def test_does_not_check_after_dependency_install_fails(self):
        with patch.object(installer.metadata, 'version', return_value='0.13.9'), \
                patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2)) as run:
            self.assertEqual(2, installer.main())
        self.assertEqual(1, run.call_count)

    def test_installation_honors_overrides_and_checks_result(self):
        with patch.object(installer.metadata, 'version', return_value='0.13.9'), \
                patch.object(installer.subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 3),
                ]) as run:
            self.assertEqual(3, installer.main())
        install_command = run.call_args_list[0].args[0]
        self.assertIn(str(installer.ROOT / 'dependency-overrides.txt'), install_command)
        self.assertIn(str(installer.ROOT / 'requirements-dev.txt'), install_command)
        self.assertEqual(run.call_args_list[1], call([
            sys.executable, str(installer.ROOT / 'scripts/check_dependencies.py'),
        ]))


if __name__ == '__main__':
    unittest.main()
