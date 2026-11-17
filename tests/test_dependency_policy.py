import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

from packaging.requirements import Requirement

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_dependencies.py'
spec = importlib.util.spec_from_file_location('check_dependencies', SCRIPT)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def distribution(name, version, requires=()):
    return SimpleNamespace(metadata={'Name': name}, version=version, requires=requires)


class TestDependencyPolicy(unittest.TestCase):
    def test_reviewed_override_replaces_upstream_pin(self):
        installed = [distribution('framework', '1', ['pycaw==20240210']),
                     distribution('pycaw', '20260927')]
        self.assertEqual([], policy.check_dependencies(
            installed, [Requirement('pycaw==20260927')], [Requirement('pycaw==20260927')]))

    def test_override_does_not_hide_unrelated_conflict(self):
        installed = [distribution('framework', '1', ['numpy<2']), distribution('numpy', '2.5.5')]
        errors = policy.check_dependencies(installed, [], [Requirement('pycaw==20260927')])
        self.assertEqual(len(errors), 1)
        self.assertIn('requires numpy<2', errors[0])

    def test_override_does_not_hide_lockfile_mismatch(self):
        errors = policy.check_dependencies(
            [distribution('pycaw', '20240210')],
            [Requirement('pycaw==20260927')], [Requirement('pycaw==20260927')])
        self.assertTrue(any('lockfile' in error for error in errors))

    def test_transitive_extra_requires_its_optional_dependency(self):
        installed = [distribution('app', '1', ['lib[crypto]>=1']),
                     distribution('lib', '1', ['cryptography>=50; extra == "crypto"'])]
        errors = policy.check_dependencies(installed, [Requirement('app==1')], [])
        self.assertEqual(errors, ['lib: missing cryptography>=50; extra == "crypto"'])

    def test_optional_and_platform_requirements(self):
        installed = [distribution('framework', '1', [
            'missing; extra == "ocr"', 'unix-only; sys_platform == "linux"',
        ])]
        self.assertEqual([], policy.check_dependencies(installed, [Requirement('framework==1')], []))
        errors = policy.check_dependencies(installed, [Requirement('framework[ocr]==1')], [])
        self.assertEqual(errors, ['framework: missing missing; extra == "ocr"'])


if __name__ == '__main__':
    unittest.main()
