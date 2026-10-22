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
    """Todo samt Kind wandert mit seinem Thema in die neue Zieldatei, Quelle verliert genau diesen Block."""
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(SOURCE)
    result = move_todo(env.writer, env.store, SRC, TODO, DST, "projekt")
    env.settle()
    assert result.state == "DONE"
    assert env.text(SRC) == "Thema #uni\n- [ ] bleibt\n"
    assert env.text(DST) == "Thema #uni\n- [ ] Lernen\n  - [ ] Kapitel 1\n"


def test_legacy_op_without_mode_finishes_without_header(tmp_path: Path) -> None:
    """Alt-Op (vor 2026-10-22, ohne ``mode``, gleiche Datei) läuft zu Ende: B' als eigene Notiz, keine Kopfzeile."""
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(SOURCE)
    op = env.store.create("move", {"src": SRC, "dst": SRC, "block": ["- [ ] Lernen", "  - [ ] Kapitel 1"],
                                   "block_first": 1, "moved": ["- [ ] Lernen #uni", "  - [ ] Kapitel 1"],
                                   "source_stem": "2026-01-01"}, {})
    op.release()
    assert resume_move(env.writer, env.store, op.id, "projekt").state == "DONE"
    env.settle()
    assert env.text(SRC) == "Thema #uni\n- [ ] bleibt\n\n- [ ] Lernen #uni\n  - [ ] Kapitel 1\n"


def test_whole_note_is_merged_into_target_and_removed_from_source(tmp_path: Path) -> None:
    """Alleiniges Todo: ganze Notiz wandert, Zusammenführen mit gleichem Thema, Quelle samt Lücke weg."""
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(b"A\n- x\n\nThema #uni\nInfo\n- [ ] Lernen\n\nB\n")
    (env.root / DST).write_bytes(b"Thema #uni\n- [ ] alt\n")
    result = move_todo(env.writer, env.store, SRC, Target(SRC, 5, "- [ ] Lernen"), DST, "projekt")
    env.settle()
    assert result.state == "DONE"
    assert env.text(SRC) == "A\n- x\n\nB\n"
    assert env.text(DST) == "Thema #uni\nInfo\n- [ ] alt\n- [ ] Lernen\n"


def crashed_move(tmp_path: Path, target_bytes: bytes) -> None:
    """Hilfsfunktion: Move mit Absturz vor dem Ziel-Write (Zielwahl ist da schon gespeichert)."""
    env = Env(tmp_path, crash=("write:before_prepared", 1))
    (env.root / SRC).write_bytes(SOURCE)
    (env.root / DST).write_bytes(target_bytes)
    with pytest.raises(SimulatedCrash):
        move_todo(env.writer, env.store, SRC, TODO, DST, "projekt")
    env.die()


def resumed(tmp_path: Path):
    """Hilfsfunktion: neue Instanz, Wiederherstellung, Move-Fortsetzung."""
    fresh = Env(tmp_path)
    recover(fresh.writer)
    [result] = recover_moves(fresh.writer, fresh.store, "projekt")
    fresh.settle()
    return fresh, result


def test_stored_target_choice_survives_a_new_duplicate_topic(tmp_path: Path) -> None:
    """Eine nach dem Absturz neu entstandene zweite Notiz mit gleichem Thema ändert die gespeicherte Wahl nicht."""
    crashed_move(tmp_path, b"Thema #uni\n- [ ] alt\n")
    (tmp_path / "vault" / DST).write_bytes(b"Thema #uni\n- [ ] alt\n\nThema #uni\n- [ ] zweite\n")
    fresh, result = resumed(tmp_path)
    assert result.state == "DONE"
    assert fresh.text(DST) == "Thema #uni\n- [ ] alt\n- [ ] Lernen\n  - [ ] Kapitel 1\n\nThema #uni\n- [ ] zweite\n"


def test_changed_target_note_is_incomplete_without_touching_the_source(tmp_path: Path) -> None:
    """Gespeicherte Zielnotiz verändert → INCOMPLETE, keine neue Suche, Quelle unverändert."""
    crashed_move(tmp_path, b"Thema #uni\n- [ ] alt\n")
    (tmp_path / "vault" / DST).write_bytes(b"Thema #uni\n- [ ] alt geaendert\n")
    fresh, result = resumed(tmp_path)
    assert result.state == "INCOMPLETE" and "Zielnotiz" in result.hint
    assert fresh.text(SRC) == SOURCE.decode() and fresh.text(DST) == "Thema #uni\n- [ ] alt geaendert\n"


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


CRASH_POINTS = [("move:prepared", 1), ("write:before_prepared", 1), ("write:tmp_ready", 1), ("write:displaced", 1),
                ("write:installed", 1), ("write:before_prepared", 2), ("write:displaced", 2), ("write:installed", 2)]


@pytest.mark.parametrize("whole", [False, True], ids=["todo", "notiz"])
@pytest.mark.parametrize("crash", CRASH_POINTS, ids=[f"{p}#{n}" for p, n in CRASH_POINTS])
def test_no_content_lost_at_any_crash_point(tmp_path: Path, crash: tuple[str, int], whole: bool) -> None:
    """Datenverlust-Invariante: Absturz an jeder Grenze → nie Verlust; nach der Wiederaufnahme ist jedes
    Inhaltselement genau einmal da; eine zweite Wiederaufnahme dupliziert nichts.

    Abgedeckt sind u. a. „Ziel geschrieben, Quelle noch vorhanden“ (``write:*#1`` danach) und „ganze Notiz
    entfernt“ (``write:installed#2`` im Fall ``notiz``).
    """
    source = b"Thema #uni\nInfo\n- [ ] Lernen\n  - [ ] Kapitel 1\n" + (b"" if whole else b"- [ ] bleibt\n")
    elements = ("Lernen", "Kapitel 1", "alt", "Info") if whole else ("Lernen", "Kapitel 1", "alt", "bleibt")
    env = Env(tmp_path, crash=crash)
    (env.root / SRC).write_bytes(source)
    (env.root / DST).write_bytes(b"Thema #uni\n- [ ] alt\n")
    with pytest.raises(SimulatedCrash):
        move_todo(env.writer, env.store, SRC, Target(SRC, 2, "- [ ] Lernen"), DST, "projekt")
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    on_disk = fresh.text(SRC) + fresh.text(DST)
    assert all(element in on_disk for element in elements)  # vorübergehende Duplikate erlaubt, Verlust nie
    results = recover_moves(fresh.writer, fresh.store, "projekt")
    fresh.settle()
    assert all(r.state == "DONE" for r in results)
    on_disk = fresh.text(SRC) + fresh.text(DST)
    assert all(on_disk.count(element) == 1 for element in elements), on_disk
    if results:  # Op war angelegt → abgeschlossen, Todo steht im Ziel
        assert "Lernen" in fresh.text(DST) and "Lernen" not in fresh.text(SRC)
    again = Env(tmp_path)
    recover(again.writer)
    assert recover_moves(again.writer, again.store, "projekt") == []
    again.settle()
    assert (again.text(SRC) + again.text(DST)).count("Lernen") == 1
