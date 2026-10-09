"""Tests für die Move-Ausführung (Ziel zuerst, Quelle nur exakt, idempotent)."""

from pathlib import Path

import pytest

from merkweiser.core.appdata import open_vault_data
from merkweiser.core.fsops import FsOps, SimulatedCrash
from merkweiser.core.move_exec import find_pending_move, move_todo, recover_moves, resume_move
from merkweiser.core.ops import OpStore
from merkweiser.core.patch import Target
from merkweiser.core.recovery import recover
from merkweiser.core.safe_write import Writer
from tests.fakes import FakeClock

SRC = "2026-01-01.md"
DST = "2026-01-05.md"
SOURCE = b"Thema #uni\n- [ ] Lernen\n  - [ ] Kapitel 1\n- [ ] bleibt\n"
TODO = Target(SRC, 1, "- [ ] Lernen")


class Env:
    """Synthetischer Vault; optional Absturz bei der n-ten Ankunft an einer Grenze."""

    def __init__(self, tmp_path: Path, crash: tuple[str, int] | None = None) -> None:
        self.root = tmp_path / "vault"
        self.root.mkdir(exist_ok=True)
        self.clock = FakeClock()
        data = open_vault_data(tmp_path / "app", self.root)
        seen: dict[str, int] = {}

        def crash_at(point: str) -> None:
            seen[point] = seen.get(point, 0) + 1
            if crash and point == crash[0] and seen[point] == crash[1]:
                raise SimulatedCrash(point)

        self.fs = FsOps(crash_at=crash_at)
        self.store = OpStore(data, self.clock, self.fs)
        self.writer = Writer(self.root, data, self.store, self.fs, self.clock)
        self.created = []
        original = self.store.create

        def tracking(*args, **kwargs):
            op = original(*args, **kwargs)
            self.created.append(op)
            return op

        self.store.create = tracking

    def text(self, name: str) -> str:
        path = self.root / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def settle(self) -> None:
        self.clock.advance(121)
        self.writer.finish_due()

    def die(self) -> None:
        for op in self.created:
            op.release()
        self.writer._pending.clear()


def test_move_to_new_day_file(tmp_path: Path) -> None:
    """Todo samt Kind wandert in die neue Zieldatei, Quelle verliert genau diesen Block."""
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(SOURCE)
    result = move_todo(env.writer, env.store, SRC, TODO, DST, "projekt")
    env.settle()
    assert result.state == "DONE"
    assert env.text(SRC) == "Thema #uni\n- [ ] bleibt\n"
    assert env.text(DST) == "Verschoben aus [[2026-01-01]]\n- [ ] Lernen #uni\n  - [ ] Kapitel 1\n"


def test_move_within_same_file_is_one_patch(tmp_path: Path) -> None:
    """Gleiche Datei: Block entfernt und als „Verschoben aus“-Notiz angehängt."""
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(SOURCE)
    assert move_todo(env.writer, env.store, SRC, TODO, SRC, "projekt").state == "DONE"
    env.settle()
    text = env.text(SRC)
    assert text.count("Lernen") == 1 and "Verschoben aus [[2026-01-01]]" in text


def test_crash_after_target_written_never_appends_twice(tmp_path: Path) -> None:
    """Absturz nach dem Ziel-Write: Fortsetzung entfernt die Quelle, hängt das Ziel nicht erneut an."""
    env = Env(tmp_path, crash=("write:before_prepared", 2))  # 2. Write = Quelle
    (env.root / SRC).write_bytes(SOURCE)
    with pytest.raises(SimulatedCrash):
        move_todo(env.writer, env.store, SRC, TODO, DST, "projekt")
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    [result] = recover_moves(fresh.writer, fresh.store, "projekt")
    fresh.settle()
    assert result.state == "DONE"
    assert fresh.text(DST).count("Lernen") == 1 and "Lernen" not in fresh.text(SRC)


def test_changed_source_is_incomplete_and_retries_never_duplicate(tmp_path: Path) -> None:
    """Quelle im Block geändert → INCOMPLETE; mehrfaches Erneut-Versuchen vervielfacht das Ziel nie."""
    env = Env(tmp_path, crash=("write:before_prepared", 2))
    (env.root / SRC).write_bytes(SOURCE)
    with pytest.raises(SimulatedCrash):
        move_todo(env.writer, env.store, SRC, TODO, DST, "projekt")
    env.die()
    (env.root / SRC).write_bytes(SOURCE.replace(b"Kapitel 1", b"Kapitel 1 bearbeitet"))
    fresh = Env(tmp_path)
    recover(fresh.writer)
    [result] = recover_moves(fresh.writer, fresh.store, "projekt")
    assert result.state == "INCOMPLETE" and "beiden Dateien" in result.hint
    for _ in range(3):
        again = resume_move(fresh.writer, fresh.store, result.op_id, "projekt", force_source=True)
        assert again.state == "INCOMPLETE"
    fresh.settle()
    assert fresh.text(DST).count("Lernen") == 1
    assert "Kapitel 1 bearbeitet" in fresh.text(SRC)
    assert recover_moves(fresh.writer, fresh.store, "projekt") == []  # INCOMPLETE wartet auf Nutzer


def test_find_pending_move_for_same_block(tmp_path: Path) -> None:
    """Gleicher Quellblock mit unvollständigem Move → „vorhandenen Vorgang fortsetzen“."""
    env = Env(tmp_path, crash=("write:before_prepared", 2))
    (env.root / SRC).write_bytes(SOURCE)
    with pytest.raises(SimulatedCrash):
        move_todo(env.writer, env.store, SRC, TODO, DST, "projekt")
    env.die()
    pending = find_pending_move(env.store, SRC, ("- [ ] Lernen", "  - [ ] Kapitel 1"))
    assert pending is not None
    assert find_pending_move(env.store, SRC, ("- [ ] anderes",)) is None
