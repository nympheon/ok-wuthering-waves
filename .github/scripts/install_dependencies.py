"""Install the locked source-app environment with its reviewed overrides."""

from importlib import metadata
from pathlib import Path
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def pip_install(arguments, attempts=10, retry_delay=30):
    command = [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *arguments]
    for attempt in range(1, attempts + 1):
        result = subprocess.run(command)
        if result.returncode == 0:
            return 0
        if attempt == attempts:
            return result.returncode
        print(f'Dependency installation failed (attempt {attempt}/{attempts}); '
              f'retrying in {retry_delay}s without the pip cache.', flush=True)
        time.sleep(retry_delay)


def main():
    expected_python = (ROOT / '.python-version').read_text(encoding='utf-8').strip()
    if '.'.join(map(str, sys.version_info[:3])) != expected_python:
        print(f'Expected Python {expected_python}; dependency installation was not started.')
        return 1
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    uv_requirement = next(value for value in project['optional-dependencies']['dev'] if value.startswith('uv=='))
    try:
        current_uv = metadata.version('uv')
    except metadata.PackageNotFoundError:
        current_uv = None
    if current_uv != uv_requirement.split('==')[1]:
        result = pip_install([uv_requirement])
        if result:
            return result
    result = subprocess.run([
        sys.executable, '-m', 'uv', 'pip', 'install', '--python', sys.executable,
        '--cache-dir', str(ROOT / 'cache/uv'),
        '--overrides', str(ROOT / 'dependency-overrides.txt'),
        '-r', str(ROOT / 'requirements-dev.txt'),
    ])
    if result.returncode:
        return result.returncode
    return subprocess.run([sys.executable, str(ROOT / 'scripts/check_dependencies.py')]).returncode


if __name__ == '__main__':
    sys.exit(main())
