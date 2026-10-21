"""Selbsttest der Install-Primitive (fs_probe) und renameat2-Variante von FsOps."""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

from merkweiser.core import fs_probe
from merkweiser.core.fs_probe import GUARANTEE, VaultNotWritableError, probe_install_mode
from merkweiser.core.fsops import FsOps, renameat2_noreplace


def fake_fs(broken: set[str] = frozenset(), overwrites: set[str] = frozenset(), excl_fails: bool = False):
    """Baut eine FsOps-Klasse, deren Varianten gezielt versagen.

    Args:
        broken: Varianten, deren Umbenennen ``PermissionError`` wirft (wie
            ``os.link`` auf Android-Shared-Storage).
        overwrites: Varianten, die ein belegtes Ziel still überschreiben.
        excl_fails: ``create_exclusive`` wirft ``PermissionError`` (schreibgeschützt).
    """

    class Fake(FsOps):
        def create_exclusive(self, path: Path, data: bytes) -> None:
            if excl_fails:
                raise PermissionError(errno.EACCES, "schreibgeschützt", str(path))
            super().create_exclusive(path, data)

        def rename_no_replace(self, src: Path, dst: Path) -> None:
            if self.install_mode in broken:
                raise PermissionError(errno.EACCES, "verboten", str(src))
            if self.install_mode in overwrites:
                os.replace(src, dst)
                return
            if os.path.lexists(dst):
                raise FileExistsError(errno.EEXIST, "existiert", str(dst))
            os.rename(src, dst)

    return Fake


def leftovers(folder: Path) -> list[str]:
    """Probedateien, die nach dem Selbsttest noch herumliegen."""
    return [name for name in os.listdir(folder) if name.startswith(".mw-probe-")]


def test_real_filesystem_gets_full_guarantee(tmp_path: Path) -> None:
    mode = probe_install_mode(tmp_path)
    assert mode == "atomic"
    assert GUARANTEE[mode] == "voll"
    assert leftovers(tmp_path) == []


def test_without_hardlinks_renameat2_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fs_probe, "FsOps", fake_fs(broken={"atomic"}))
    assert probe_install_mode(tmp_path) == "noreplace"
    assert leftovers(tmp_path) == []


def test_without_atomic_primitive_falls_back_to_excl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fs_probe, "FsOps", fake_fs(broken={"atomic", "noreplace"}))
    mode = probe_install_mode(tmp_path)
    assert mode == "excl"
    assert GUARANTEE[mode].startswith("eingeschränkt")
    assert leftovers(tmp_path) == []


def test_silently_overwriting_variant_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fs_probe, "FsOps", fake_fs(overwrites={"atomic"}))
    assert probe_install_mode(tmp_path) == "noreplace"
    assert leftovers(tmp_path) == []


def test_unwritable_vault_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fs_probe, "FsOps", fake_fs(excl_fails=True))
    with pytest.raises(VaultNotWritableError):
        probe_install_mode(tmp_path)
    assert leftovers(tmp_path) == []


def test_probe_files_never_touch_user_notes(tmp_path: Path) -> None:
    note = tmp_path / "2026-01-15.md"
    note.write_bytes(b"Heute\n")
    probe_install_mode(tmp_path)
    assert sorted(os.listdir(tmp_path)) == ["2026-01-15.md"]
    assert note.read_bytes() == b"Heute\n"


@pytest.mark.skipif(sys.platform == "linux", reason="Auf Linux ist der Syscall vorhanden")
def test_renameat2_unavailable_off_linux(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"a")
    with pytest.raises(OSError) as info:
        renameat2_noreplace(tmp_path / "a", tmp_path / "b")
    assert info.value.errno == errno.ENOSYS
    assert (tmp_path / "a").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="renameat2 gibt es nur unter Linux/Android")
def test_renameat2_never_overwrites(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    FsOps("noreplace").rename_no_replace(a, c)
    assert c.read_bytes() == b"a" and not a.exists()
    with pytest.raises(FileExistsError):
        FsOps("noreplace").rename_no_replace(b, c)
    assert b.read_bytes() == b"b" and c.read_bytes() == b"a"
