"""Tests für den Backup-Browser der App-Schicht (W4, PLAN-SPAETERE-SCHRITTE.md 1.4)."""

from datetime import date
from pathlib import Path

import pytest

from merkweiser.app.backup_views import file_changes, file_entries, undo, undo_group
from merkweiser.app.notes_service import NotesService, ReadOnlyVaultError
from merkweiser.app.settings import Settings
from merkweiser.core.patch import Target
from tests.fakes import FakeClock

DAY = "2026-01-15.md"
CONFLICT = "2026-01-15.sync-conflict-20260115-120000-AAAAAAA.md"


def service(tmp_path: Path, files: dict[str, bytes]) -> NotesService:
    root = tmp_path / "vault"
    root.mkdir()
    for name, data in files.items():
        (root / name).write_bytes(data)
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    return svc


def settle(svc: NotesService) -> None:
    svc.clock.advance(121)
    svc.writer.finish_due()


def test_single_change_listed_and_undone(tmp_path: Path) -> None:
    """Abhaken erscheint als Änderung mit Vergleich; Rückgängig hebt nur diesen Haken auf."""
    svc = service(tmp_path, {DAY: b"Thema\n- [ ] a\n- x\n- [ ] b\n"})
    svc.set_done(Target(DAY, 1, "- [ ] a"), True)
    settle(svc)
    svc.set_done(Target(DAY, 3, "- [ ] b"), True)
    settle(svc)
    [entry] = file_entries(svc)
    assert (entry.relpath, entry.count) == (DAY, 2)
    newest, oldest = file_changes(svc, DAY)
    assert [r.side for r in oldest.diff if r.side in ("haupt", "konflikt")] == ["haupt", "konflikt"]
    assert undo(svc, oldest.change) == "Änderung rückgängig gemacht."
    settle(svc)
    assert (svc.root / DAY).read_bytes() == b"Thema\n- [ ] a\n- x\n- [x] b\n"
    assert any(v.undone for v in file_changes(svc, DAY))


def test_move_changes_show_group_note_and_siblings(tmp_path: Path) -> None:
    """Verschieben ändert zwei Dateien; jede Einzeländerung nennt den Zusammenhang und die andere Datei."""
    svc = service(tmp_path, {DAY: b"Thema\n- [ ] a\n- [ ] b\n"})
    svc.move_todo(Target(DAY, 1, "- [ ] a"), date(2026, 1, 16))
    settle(svc)
    [view] = file_changes(svc, DAY)
    assert view.change.label == "verschoben"
    assert "keiner Datei" in view.group_note and [s.relpath for s in view.siblings] == ["2026-01-16.md"]
    assert view.group_action == ""


def test_automerge_group_action_restores_conflict(tmp_path: Path) -> None:
    """Auto-Merge: „Zusammenführung rückgängig“ nutzt das bisherige ``undo_automerge``."""
    svc = service(tmp_path, {DAY: b"Thema\n- [ ] a\n", CONFLICT: b"Thema\n- [ ] a\n- [ ] b\n"})
    [view] = file_changes(svc, DAY)
    assert view.group_action == "Zusammenführung rückgängig" and view.siblings
    assert CONFLICT in undo_group(svc, view.change)
    assert (svc.root / CONFLICT).exists()


def test_undo_refused_read_only(tmp_path: Path) -> None:
    svc = service(tmp_path, {DAY: b"Thema\n- [ ] a\n"})
    svc.set_done(Target(DAY, 1, "- [ ] a"), True)
    settle(svc)
    [view] = file_changes(svc, DAY)
    svc.read_only = True
    with pytest.raises(ReadOnlyVaultError):
        undo(svc, view.change)
