"""Tests für ``conflict_files.create_own_conflict`` (eine Quelle für eigene Konfliktdateien, W9 P1)."""

from pathlib import Path

import pytest

from merkweiser.core import conflict_files as cf
from merkweiser.core.appdata import open_vault_data
from merkweiser.core.fsops import FsOps
from merkweiser.core.ops import OpStore
from merkweiser.core.safe_write import Writer
from merkweiser.core.vault import parse_conflict_name
from tests.fakes import FakeClock

BASE, OURS = b"Thema\n- [ ] alt\n", b"Thema\n- [x] alt\n"


@pytest.fixture
def writer(tmp_path: Path) -> Writer:
    """Writer auf einem synthetischen Vault mit einer Hauptdatei."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-15.md").write_bytes(BASE)
    clock = FakeClock()
    data = open_vault_data(tmp_path / "app", root)
    fs = FsOps()
    return Writer(root, data, OpStore(data, clock, fs), fs, clock)


def test_creates_conflict_with_sidecar_base(writer: Writer) -> None:
    rel, base_id = cf.create_own_conflict(writer, "2026-01-15.md", OURS, BASE)
    assert (writer.root / rel).read_bytes() == OURS
    parsed = parse_conflict_name(Path(rel).name)
    assert parsed is not None and parsed.own and parsed.main_relpath == "2026-01-15.md"
    sidecar = cf.read_sidecar(writer.data, rel, cf.sha1(OURS))
    assert sidecar["base_op"] == base_id and sidecar["base_sha1"] == cf.sha1(BASE)
    assert "herkunft" not in sidecar
    assert writer.store.read_blob(base_id, "vorher", cf.sha1(BASE)) == BASE


def test_without_base_no_sidecar(writer: Writer) -> None:
    rel, base_id = cf.create_own_conflict(writer, "2026-01-15.md", OURS, None)
    assert base_id is None
    assert cf.read_sidecar(writer.data, rel, cf.sha1(OURS)) is None


def test_reuse_and_origin(writer: Writer) -> None:
    first, _ = cf.create_own_conflict(writer, "2026-01-15.md", OURS, BASE, cf.UNDO_ORIGIN, reuse=True)
    second, _ = cf.create_own_conflict(writer, "2026-01-15.md", OURS, BASE, cf.UNDO_ORIGIN, reuse=True)
    assert first == second
    assert cf.read_sidecar(writer.data, first, cf.sha1(OURS))["herkunft"] == cf.UNDO_ORIGIN


def test_without_reuse_creates_second_file(writer: Writer) -> None:
    first, _ = cf.create_own_conflict(writer, "2026-01-15.md", OURS, BASE)
    second, _ = cf.create_own_conflict(writer, "2026-01-15.md", OURS, BASE)
    assert first != second
