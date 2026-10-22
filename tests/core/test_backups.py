"""Tests für Backup-Browser und Rückgängig einzelner Änderungen (PLAN-SPAETERE-SCHRITTE.md S4, Y6, Y9)."""

from pathlib import Path

import pytest

from merkweiser.core import conflict_files as cf
from merkweiser.core.backups import changes, changes_by_file, change_key, recover_undos, undo_change, undone_ops
from merkweiser.core.conflicts import CaseKind, auto_merge
from merkweiser.core.fsops import SimulatedCrash
from merkweiser.core.merge.diff3 import merge3
from merkweiser.core.recovery import recover
from merkweiser.core.resolve import resolve
from merkweiser.core.undo_merge import merge_is_safe, plan_undo
from tests.core.test_conflicts import CONF, MAIN, Env


# --- rein: Rückwärts-diff3 und Existenz (Y6) --------------------------------------------


def test_undo_keeps_later_changes() -> None:
    """Nur die eine Änderung wird zurückgenommen; eine spätere Zeile bleibt."""
    plan = plan_undo(b"a\nb\nc\nd\n", b"a\nB\nc\nd\n", b"a\nB\nc\nd\ne\n")
    assert (plan.action, plan.data) == ("schreiben", b"a\nb\nc\nd\ne\n")


def test_undo_of_a_check_keeps_other_todos() -> None:
    plan = plan_undo(b"- [ ] a\n- x\n", b"- [x] a\n- x\n", b"- [x] a\n- x\n- [ ] b\n")
    assert plan.data == b"- [ ] a\n- x\n- [ ] b\n"


def test_adjacent_later_change_is_a_conflict_grenze() -> None:
    """GRENZE: direkt benachbarte spätere Änderung → Konfliktdatei (wie beim Sync-Merge)."""
    assert plan_undo(b"- [ ] a\n", b"- [x] a\n", b"- [x] a\n- [ ] b\n").action == "konflikt"


def test_same_line_changed_later_is_a_conflict() -> None:
    assert plan_undo(b"a\nb\n", b"a\nB\n", b"a\nBB\n").action == "konflikt"


def test_undo_of_creation_removes_the_file_only_if_nothing_else_is_in_it() -> None:
    """Neuanlage: unverändert → entfernen; später ergänzt → Konfliktdatei statt Inhalt löschen."""
    assert plan_undo(None, b"x\n", b"x\n").action == "entfernen"
    assert plan_undo(None, b"x\n", b"x\ny\n").action == "konflikt"
    assert plan_undo(None, b"x\n", None).action == "nichts"


def test_undo_of_deletion_restores_the_file() -> None:
    plan = plan_undo(b"x\n", None, None)
    assert (plan.action, plan.data) == ("schreiben", b"x\n")


def test_truly_empty_file_stays_an_empty_file() -> None:
    """Vorher existierte die Datei leer → Rückgängig schreibt eine leere Datei, löscht sie nicht."""
    assert plan_undo(b"", b"x\n", b"x\n") == plan_undo(b"", b"x\n", b"x\n").__class__("schreiben", b"")


def test_externally_removed_file_becomes_conflict_not_silent_recreation() -> None:
    assert plan_undo(b"a\n", b"a\nb\n", None).action == "konflikt"


def test_merge_is_safe_both_ways() -> None:
    """Y9: sauber und ohne Verstöße → sicher; Hunk → nicht sicher."""
    clean = merge3(["a", "b", "c"], ["a", "b", "c", "d"], ["A", "b", "c"])
    assert clean.clean and merge_is_safe(clean, ["a", "b", "c", "d"], ["A", "b", "c"], ["a", "b", "c"])
    hunk = merge3(["a"], ["x"], ["y"])
    assert not merge_is_safe(hunk, ["x"], ["y"], ["a"])


# --- mit Dateien ---------------------------------------------------------------------


def edited(tmp_path: Path) -> tuple[Env, str]:
    """``MAIN`` wird von a/b/c/d auf a/B/c/d geändert, danach von außen um e ergänzt."""
    env = Env(tmp_path)
    env.put(MAIN, b"a\nb\nc\nd\n")
    env.writer.write(MAIN, b"a\nb\nc\nd\n", b"a\nB\nc\nd\n")
    env.settle()
    env.put(MAIN, b"a\nB\nc\nd\ne\n")
    [change] = [c for c in changes(env.store) if c.relpath == MAIN]
    return env, change


def test_changes_are_grouped_by_file_and_undo_is_recorded(tmp_path: Path) -> None:
    env, change = edited(tmp_path)
    assert (change.kind, change.label) == ("bearbeitet", "bearbeitet")
    assert [rel for rel, _ in changes_by_file(env.store)] == [MAIN]
    result = undo_change(env.writer, env.store, change)
    env.settle()
    assert result.action == "schreiben" and env.get(MAIN) == b"a\nb\nc\nd\ne\n"
    assert change_key(change) in undone_ops(env.store)
    newest = changes(env.store)[0]
    assert newest.label == "rückgängig gemacht" and newest.group_art == "rueckgaengig"


def test_ambiguous_undo_creates_own_conflict_file_with_base(tmp_path: Path) -> None:
    """Nicht eindeutig → ``before`` als eigene Konfliktdatei; Sidecar-Basis = ``after`` (diff3 im Dialog)."""
    env, change = edited(tmp_path)
    env.put(MAIN, b"a\nBB\nc\nd\n")
    assert undo_change(env.writer, env.store, change).action == "konflikt"
    assert env.get(MAIN) == b"a\nBB\nc\nd\n"
    [case] = env.cases()
    assert case.conflict_bytes == b"a\nb\nc\nd\n" and case.kind is CaseKind.MANUAL
    sidecar = cf.read_sidecar(env.data, case.conflict.relpath, cf.sha1(b"a\nb\nc\nd\n"))
    assert sidecar and sidecar["base_sha1"] == cf.sha1(b"a\nB\nc\nd\n")


def test_restored_sync_conflict_file_stays_manual(tmp_path: Path) -> None:
    """Rückgängig des Entfernens einer Sync-Konfliktdatei (Auto-Merge) → sie bleibt manuell."""
    env = Env(tmp_path)
    env.put(MAIN, b"Notiz\n- [ ] A\n")
    env.put(CONF, b"Notiz\n- [ ] A\n- [ ] B\n")
    [case] = env.cases()
    auto_merge(env.writer, env.store, case)
    env.settle()
    removal = next(c for c in changes(env.store) if c.relpath == CONF)
    assert removal.kind == "gelöscht" and removal.label == "automatisch zusammengeführt"
    undo_change(env.writer, env.store, removal)
    env.settle()
    assert env.get(CONF) == b"Notiz\n- [ ] A\n- [ ] B\n"
    [again] = env.cases()
    assert again.kind is not CaseKind.AUTO


def test_resolve_marker_is_restored_under_original_conflict_name(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.put(MAIN, b"x\n")
    env.put(CONF, b"y\n")
    [case] = env.cases()
    resolve(env.writer, env.store, MAIN, b"x\n", CONF, b"y\n", b"x\n", "haupt")
    env.settle()
    removal = next(c for c in changes(env.store) if c.kind == "gelöscht")
    assert "MWENTSCHIEDEN" in removal.relpath
    undo_change(env.writer, env.store, removal)
    env.settle()
    assert env.get(CONF) == b"y\n" and env.get(removal.relpath) is None
    assert case.conflict.relpath == CONF


@pytest.mark.parametrize("point", ["write:tmp_ready", "write:installed"])
def test_crash_during_undo_resumes_exactly_once(tmp_path: Path, point: str) -> None:
    """Absturz im Schreibschritt → Wiederaufnahme beim Start, Ergebnis genau einmal, Vorgang abgeschlossen."""
    env, change = edited(tmp_path)
    crashing = Env(tmp_path, crash=point)
    with pytest.raises(SimulatedCrash):
        undo_change(crashing.writer, crashing.store, change)
    crashing.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    fresh.settle()
    recover_undos(fresh.writer, fresh.store)
    fresh.settle()
    assert fresh.get(MAIN) == b"a\nb\nc\nd\ne\n"
    assert change_key(change) in undone_ops(fresh.store)
    assert recover_undos(fresh.writer, fresh.store) == []
