"""Saved versions of a team's code, stored beside the live custom teams."""

import json
import re
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from ok.util.config import Config
from src.char.CustomCharLoader import (
    TEAM_CODE_MODE_IMPORT, TEAM_IMPORT_SUFFIX, TEAM_MANIFEST_FILE, clear_team_char_cache,
    get_custom_team_folder, get_team_key, import_custom_team, normalize_team,
)


def _variant_root(team):
    return Path(Config.config_folder) / "custom_team_variants" / get_team_key(team)


def _variant_path(team, variant_id):
    if not isinstance(variant_id, str) or not re.fullmatch(r"[0-9a-f]{32}", variant_id):
        raise ValueError("Invalid team version")
    return _variant_root(team) / variant_id


def _read_manifest(folder):
    try:
        manifest = json.loads((folder / TEAM_MANIFEST_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeError, json.JSONDecodeError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def list_team_variants(team):
    """Return IDs and manifests for saved versions. The live directory is the active version."""
    team = normalize_team(team)
    root = _variant_root(team)
    if not root.is_dir():
        return []
    variants = [
        (folder.name, _read_manifest(folder))
        for folder in root.iterdir()
        if re.fullmatch(r"[0-9a-f]{32}", folder.name) and folder.is_dir()
        and all((folder / f"{name}.py").is_file() for name in team)
    ]
    return sorted(variants, key=lambda variant: (
        str(variant[1].get("name") or "").casefold(),
        str(variant[1].get("version") or "").casefold(),
        str(variant[1].get("author") or "").casefold(),
        variant[0],
    ))


def _matches_archive(folder, info, require_import_mode=False):
    manifest = _read_manifest(folder)
    code_mode = manifest.pop("code_mode", None)
    archive_manifest = {key: value for key, value in info["manifest"].items() if key != "code_mode"}
    if manifest != archive_manifest or (require_import_mode and code_mode != TEAM_CODE_MODE_IMPORT):
        return False
    for name, code in info["codes"].items():
        current = folder / f"{name}.py"
        imported = folder / f"{name}{TEAM_IMPORT_SUFFIX}"
        original = imported if imported.is_file() else current
        try:
            if original.read_text(encoding="utf-8") != code:
                return False
            if require_import_mode and (original == current or current.read_text(encoding="utf-8") != code):
                return False
        except (FileNotFoundError, UnicodeError):
            return False
    return True


def _write_archive_variant(team, info):
    # The archive's manifest and source files have been validated by inspect_team_archive.
    root = _variant_root(team)
    root.mkdir(parents=True, exist_ok=True)
    variant_id = uuid4().hex
    with tempfile.TemporaryDirectory(prefix=".write-", dir=root) as temp:
        folder = Path(temp) / "team"
        folder.mkdir()
        manifest = {**info["manifest"], "code_mode": TEAM_CODE_MODE_IMPORT}
        (folder / TEAM_MANIFEST_FILE).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        for name in team:
            code = info["codes"][name]
            (folder / f"{name}.py").write_text(code, encoding="utf-8")
            (folder / f"{name}{TEAM_IMPORT_SUFFIX}").write_text(code, encoding="utf-8")
        folder.rename(root / variant_id)
    return variant_id


def store_team_variant(info):
    """Save an inspected archive for later use. Return whether a copy was added."""
    team = normalize_team(info["team"])
    if _matches_archive(get_custom_team_folder(team), info):
        return False
    for variant_id, _manifest in list_team_variants(team):
        if _matches_archive(_variant_path(team, variant_id), info):
            return False
    _write_archive_variant(team, info)
    return True


def activate_team_variant(team, variant_id):
    """Exchange the live directory for a saved version, keeping the previous team."""
    team = normalize_team(team)
    source = _variant_path(team, variant_id)
    if not source.is_dir():
        raise ValueError("Team version no longer exists")
    live = get_custom_team_folder(team)
    previous = source.with_name(uuid4().hex)
    live.rename(previous)
    try:
        source.rename(live)
    except OSError:
        previous.rename(live)
        raise
    finally:
        clear_team_char_cache(team)


def import_active_team_variant(info):
    """Import an inspected archive and preserve any version it replaces."""
    team = normalize_team(info["team"])
    live = get_custom_team_folder(team)
    if not live.is_dir():
        import_custom_team(info)
        return False
    if _matches_archive(live, info, require_import_mode=True):
        return False
    for variant_id, _manifest in list_team_variants(team):
        if _matches_archive(_variant_path(team, variant_id), info, require_import_mode=True):
            break
    else:
        variant_id = _write_archive_variant(team, info)
    activate_team_variant(team, variant_id)
    return True


def delete_team_variant(team, variant_id):
    shutil.rmtree(_variant_path(team, variant_id))
