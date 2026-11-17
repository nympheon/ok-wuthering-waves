"""Check installed requirements, honoring only the project's explicit overrides."""
from importlib import metadata
from pathlib import Path
import sys
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def read_requirements(path):
    return [Requirement(line.strip()) for line in path.read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def check_dependencies(distributions, locked, overrides):
    installed = {canonicalize_name(dist.metadata['Name']): dist for dist in distributions}
    replacements = {canonicalize_name(req.name): req for req in overrides}
    extras = {}
    for req in locked:
        extras.setdefault(canonicalize_name(req.name), set()).update(req.extras)
    changed = True
    while changed:
        changed = False
        for name, dist in installed.items():
            contexts = ('', *extras.get(name, ()))
            for value in dist.requires or ():
                req = Requirement(value)
                if req.marker and not any(req.marker.evaluate({'extra': extra}) for extra in contexts):
                    continue
                requested = extras.setdefault(canonicalize_name(req.name), set())
                additional = req.extras - requested
                if additional:
                    requested.update(additional)
                    changed = True
    errors = []

    def check(requirement, source, contexts=('',), allow_override=True):
        if requirement.marker and not any(requirement.marker.evaluate({'extra': extra}) for extra in contexts):
            return
        name = canonicalize_name(requirement.name)
        expected = replacements.get(name, requirement) if allow_override else requirement
        dist = installed.get(name)
        if dist is None:
            errors.append(f'{source}: missing {expected}')
        elif not expected.specifier.contains(dist.version):
            errors.append(f'{source}: requires {expected}, installed {dist.version}')

    for req in locked:
        check(req, 'lockfile', allow_override=False)
    for name, dist in installed.items():
        for value in dist.requires or ():
            check(Requirement(value), dist.metadata['Name'], ('', *extras.get(name, ())))
    return errors


def main():
    expected_python = (ROOT / '.python-version').read_text(encoding='utf-8').strip()
    if '.'.join(map(str, sys.version_info[:3])) != expected_python:
        print(f'Expected Python {expected_python}; dependency check failed.')
        return 1
    locked = read_requirements(ROOT / 'requirements-dev.txt')
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    declared = [Requirement(value) for value in project['dependencies']
                + project['optional-dependencies']['dev']]
    overrides = read_requirements(ROOT / 'dependency-overrides.txt')
    errors = check_dependencies(list(metadata.distributions()), locked + declared, overrides)
    if errors:
        print('\n'.join(errors))
        return 1
    print(f'Dependency check passed: {len(locked)} locked packages; '
          f'project overrides: {", ".join(str(req) for req in overrides)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
