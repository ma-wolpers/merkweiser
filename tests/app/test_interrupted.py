"""Tests für unterbrochene Vorgänge (Konflikte-Seite, Badge) – PLAN-SPAETERE-SCHRITTE.md, Phase 2."""

from pathlib import Path

import pytest

from merkweiser.app.interrupted import DISMISS, FORCE, RETRY, action_label, apply_action, interrupted, open_issue_count
from merkweiser.app.notes_service import NotesService, ReadOnlyVaultError
from merkweiser.app.settings import Settings
from merkweiser.core.fsops import SimulatedCrash
from merkweiser.core.move_exec import move_todo, recover_moves
from merkweiser.core.recovery import recover
from tests.core.test_move_exec import DST, SOURCE, SRC, TODO, Env
from tests.fakes import FakeClock


def incomplete_move(tmp_path: Path) -> NotesService:
    """Move bricht nach dem Ziel ab, die Quelle wird verändert → ``INCOMPLETE``; danach öffnet der Service."""
    env = Env(tmp_path, crash=("write:before_prepared", 2))
    (env.root / SRC).write_bytes(SOURCE)
    with pytest.raises(SimulatedCrash):
        move_todo(env.writer, env.store, SRC, TODO, DST, "projekt")
    env.die()
    (env.root / SRC).write_bytes(SOURCE.replace(b"Kapitel 1", b"Kapitel 1 bearbeitet"))
    fresh = Env(tmp_path)
    recover(fresh.writer)
    [result] = recover_moves(fresh.writer, fresh.store, "projekt")
    assert result.state == "INCOMPLETE"
    fresh.die()
    service = NotesService(env.root, tmp_path / "app", Settings(vault=str(env.root)), FakeClock(), fs=fresh.fs)
    service.start()
    return service


def test_incomplete_move_is_listed_with_actions_and_counted(tmp_path: Path) -> None:
    """Der unterbrochene Move erscheint mit Hinweis, Quelle → Ziel und drei Aktionen; das Badge zählt ihn."""
    service = incomplete_move(tmp_path)
    [entry] = interrupted(service.store)
    assert (entry.art, entry.label, entry.detail) == ("move", "Verschieben", f"{SRC} → {DST}")
    assert "beiden Dateien" in entry.hint
    assert entry.actions == (RETRY, FORCE, DISMISS)
    assert action_label(entry, DISMISS) == "Beide behalten"
    assert open_issue_count(service) == 1


def test_retry_keeps_it_incomplete_and_dismiss_clears_without_file_changes(tmp_path: Path) -> None:
    """„Erneut versuchen“ bleibt bei veränderter Quelle unvollständig; „Beide behalten“ quittiert ohne Dateiänderung."""
    service = incomplete_move(tmp_path)
    [entry] = interrupted(service.store)
    before = {p.name: p.read_bytes() for p in service.root.glob("*.md")}
    assert "beiden Dateien" in apply_action(service, entry.op_id, RETRY)
    assert apply_action(service, entry.op_id, DISMISS) == ""
    assert interrupted(service.store) == [] and open_issue_count(service) == 0
    assert {p.name: p.read_bytes() for p in service.root.glob("*.md")} == before


def test_retry_is_refused_read_only(tmp_path: Path) -> None:
    """Im Schreibschutz lehnt „Erneut versuchen“ ab, bevor etwas passiert."""
    service = incomplete_move(tmp_path)
    [entry] = interrupted(service.store)
    service.read_only = True
    with pytest.raises(ReadOnlyVaultError):
        apply_action(service, entry.op_id, RETRY)
    with pytest.raises(ValueError):
        apply_action(service, entry.op_id, "unbekannt")
