"""Persistent source settings for the built-in character workshop."""

import json
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from ok.util.config import Config

logger = logging.getLogger(__name__)
DEFAULT_BASE_URL = 'https://eeeeeeeedison.github.io/wwlibrary'
SETTINGS_FILE = 'code_fetch.json'
DEFAULT_ARCHIVE_HOSTS = {'github.com', 'raw.githubusercontent.com'}
LEGACY_HOSTS = {'okwwcharcode.ok-script.com', 'cfokwwchar.ok-script.com'}


def normalize_base_url(value):
    if not isinstance(value, str):
        raise ValueError('工坊地址必须是 HTTPS 网址。')
    parsed = urlparse(value.strip())
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError('请输入不带账号、查询参数或片段的 HTTPS 工坊地址。')
    try:
        parsed.port
    except ValueError as error:
        raise ValueError('工坊地址的端口无效。') from error
    return urlunparse(parsed._replace(path=parsed.path.rstrip('/')))


def load_settings():
    path = Path(Config.config_folder) / SETTINGS_FILE
    try:
        raw = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(raw, dict):
            raise ValueError('工坊设置应为 JSON 对象')
    except FileNotFoundError:
        raw = {}
    except (OSError, UnicodeError, ValueError) as error:
        logger.warning('无法读取角色代码工坊设置 %s：%s', path, error)
        raw = {}
    settings = dict(raw)
    try:
        settings['base_url'] = normalize_base_url(raw.get('base_url', DEFAULT_BASE_URL))
    except ValueError:
        settings['base_url'] = DEFAULT_BASE_URL
    hosts = raw.get('extra_archive_hosts', [])
    settings['extra_archive_hosts'] = [
        host.strip().lower() for host in hosts if isinstance(host, str) and host.strip()
    ] if isinstance(hosts, list) else []
    return settings


def save_settings(settings):
    payload = dict(settings)
    payload['base_url'] = normalize_base_url(payload.get('base_url'))
    folder = Path(Config.config_folder)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder,
                                         prefix='.code_fetch-', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write('\n')
        os.replace(temporary, folder / SETTINGS_FILE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return payload


def index_url(path='teams.json', settings=None):
    settings = settings if settings is not None else load_settings()
    return urljoin(normalize_base_url(settings['base_url']) + '/', path)


def archive_url(value, settings=None):
    settings = settings if settings is not None else load_settings()
    if not isinstance(value, str) or not value.strip():
        raise ValueError('工坊下载地址为空。')
    base = normalize_base_url(settings['base_url'])
    url = urljoin(base + '/', value.strip())
    parsed = urlparse(url)
    if parsed.hostname in LEGACY_HOSTS:
        url = urljoin(base + '/', parsed.path.lstrip('/'))
        parsed = urlparse(url)
    hosts = {urlparse(base).hostname, *DEFAULT_ARCHIVE_HOSTS,
             *settings.get('extra_archive_hosts', [])}
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password:
        raise ValueError('工坊下载地址不在允许的 HTTPS 主机内。')
    return url


def repository_url():
    base = load_settings()['base_url']
    parsed = urlparse(base)
    if parsed.hostname.endswith('.github.io') and parsed.path.strip('/'):
        owner = parsed.hostname.removesuffix('.github.io')
        project = parsed.path.strip('/').split('/')[0]
        return f'https://github.com/{owner}/{project}'
    return base
