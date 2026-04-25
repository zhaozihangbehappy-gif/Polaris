# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

from __future__ import annotations

import io
import tarfile

import pytest

from polaris.cli import _extract_packs


def test_extract_packs_rejects_parent_traversal(tmp_path):
    tarball = tmp_path / "packs.tar.gz"
    target = tmp_path / "target"
    escaped = tmp_path / "evil"

    with tarfile.open(tarball, "w:gz") as archive:
        payload = b"owned"
        member = tarfile.TarInfo("../evil")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with pytest.raises((tarfile.AbsolutePathError, ValueError)):
        _extract_packs(tarball, target)

    assert not escaped.exists()
