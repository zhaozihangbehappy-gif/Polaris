# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

from __future__ import annotations

import shutil
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "polaris"
LEGACY_SALT_PATH = Path.home() / ".polaris" / "contributor_salt"
LEGACY_EXPERIENCE_SALT_PATH = Path.home() / ".polaris" / "experience" / ".contributor_salt"


def data_root() -> Path:
    return Path(user_data_dir(APP_NAME)).expanduser()


def packs_root() -> Path:
    return data_root() / "packs"


def official_packs_dir() -> Path:
    return packs_root() / "official"


def community_packs_dir() -> Path:
    return packs_root() / "community"


def candidate_packs_dir() -> Path:
    return packs_root() / "candidates"


def community_state_dir() -> Path:
    return data_root() / "community"


def validations_dir() -> Path:
    return community_state_dir() / "validations"


def rejects_dir() -> Path:
    return community_state_dir() / "rejects"


def promoted_dir() -> Path:
    return community_state_dir() / "promoted"


def inbox_dir() -> Path:
    return community_state_dir() / "inbox"


def contributor_salt_path() -> Path:
    return data_root() / "contributor_salt"


def supporter_token_path() -> Path:
    return data_root() / "supporter_token.json"


def package_packs_root() -> Path:
    return Path(__file__).resolve().parent / "packs"


def _repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "experience-packs-v4").exists() and (parent / "scripts").exists():
            return parent
    return None


def _legacy_seed_roots() -> dict[str, Path] | None:
    root = _repo_root()
    if root is None:
        return None
    mapping = {"community_state": root / "community"}
    if not mapping["community_state"].exists():
        return None
    return mapping


def _copytree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _seed_community_state(dst: Path, src: Path | None) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("inbox", "promoted", "rejects", "validations"):
        (dst / name).mkdir(parents=True, exist_ok=True)
    if src and (src / "README.md").exists() and not (dst / "README.md").exists():
        shutil.copy2(src / "README.md", dst / "README.md")
    elif not (dst / "README.md").exists():
        (dst / "README.md").write_text(
            "# Community state\n\n"
            "Local Polaris community state lives here.\n"
        )


def _migrate_salt() -> None:
    target = contributor_salt_path()
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    for legacy in (LEGACY_SALT_PATH, LEGACY_EXPERIENCE_SALT_PATH):
        if legacy.exists():
            shutil.copy2(legacy, target)
            return


def ensure_user_data() -> Path:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_seed_roots()
    seeds = package_packs_root()
    if not official_packs_dir().exists():
        _copytree(seeds / "official", official_packs_dir())
    if not community_packs_dir().exists():
        _copytree(seeds / "community", community_packs_dir())
    if not candidate_packs_dir().exists():
        _copytree(seeds / "candidates", candidate_packs_dir())
    _seed_community_state(community_state_dir(), legacy["community_state"] if legacy else None)
    _migrate_salt()
    return root


def configured_runtime_paths() -> dict[str, Path]:
    ensure_user_data()
    return {
        "root": data_root(),
        "packs": packs_root(),
        "official": official_packs_dir(),
        "community": community_packs_dir(),
        "candidates": candidate_packs_dir(),
        "community_state": community_state_dir(),
        "validations": validations_dir(),
        "rejects": rejects_dir(),
        "promoted": promoted_dir(),
        "inbox": inbox_dir(),
        "salt": contributor_salt_path(),
        "supporter_token": supporter_token_path(),
    }
