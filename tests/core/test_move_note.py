"""W7 Phase 3: ganze Notiz verschieben (gleiches Move-Protokoll wie beim Todo)."""

from pathlib import Path

import pytest

from merkweiser.core.fsops import SimulatedCrash
from merkweiser.core.move_exec import move_note, move_todo, recover_moves, resume_move
from merkweiser.core.note_ops import NoteNotFoundError
from merkweiser.core.patch import Target
from merkweiser.core.recovery import recover
from tests.core.test_move_exec import CRASH_POINTS, DST, SRC, Env

NOTE = ("Elternabend #schule", "Einladung bis Freitag", "- [ ] Brief schreiben", "- [ ] Raum buchen")
SOURCE = ("\n".join(NOTE) + "\n\nAnderes\n- [ ] bleibt\n").encode()


def test_new_note_when_no_topic_matches(tmp_path: Path) -> None:
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(SOURCE)
    (env.root / DST).write_bytes(b"Sport\n- [ ] laufen\n")
    result = move_note(env.writer, env.store, SRC, NOTE, DST, "projekt")
    env.settle()
    assert result.state == "DONE"
    assert env.text(DST) == "Sport\n- [ ] laufen\n\n" + "\n".join(NOTE) + "\n"
    assert env.text(SRC) == "Anderes\n- [ ] bleibt\n"


def test_merges_into_exactly_one_matching_topic_note(tmp_path: Path) -> None:
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(SOURCE)
    (env.root / DST).write_bytes(b"Elternabend #schule\n- [ ] Stuehle\n")
    assert move_note(env.writer, env.store, SRC, NOTE, DST, "projekt").state == "DONE"
    env.settle()
    assert env.text(DST) == ("Elternabend #schule\nEinladung bis Freitag\n- [ ] Stuehle\n- [ ] Brief schreiben\n"
                             "- [ ] Raum buchen\n")


def test_two_matching_topic_notes_give_a_new_note(tmp_path: Path) -> None:
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(SOURCE)
    target = b"Elternabend #schule\n- [ ] a\n\nElternabend #schule\n- [ ] b\n"
    (env.root / DST).write_bytes(target)
    assert move_note(env.writer, env.store, SRC, NOTE, DST, "projekt").state == "DONE"
    env.settle()
    assert env.text(DST) == target.decode() + "\n" + "\n".join(NOTE) + "\n"


def test_duplicate_or_changed_note_writes_nothing(tmp_path: Path) -> None:
    env = Env(tmp_path)
    doubled = ("\n".join(NOTE) + "\n\n" + "\n".join(NOTE) + "\n").encode()
    (env.root / SRC).write_bytes(doubled)
    with pytest.raises(NoteNotFoundError):
        move_note(env.writer, env.store, SRC, NOTE, DST, "projekt")
    (env.root / SRC).write_bytes(SOURCE.replace(b"Raum buchen", b"Raum buchen!"))
    with pytest.raises(NoteNotFoundError):
        move_note(env.writer, env.store, SRC, NOTE, DST, "projekt")
    assert not (env.root / DST).exists() and env.created == []


def test_crash_after_target_then_recovery_removes_source_exactly_once(tmp_path: Path) -> None:
    env = Env(tmp_path, crash=("write:before_prepared", 2))  # 2. Write = Quelle
    (env.root / SRC).write_bytes(SOURCE)
    with pytest.raises(SimulatedCrash):
        move_note(env.writer, env.store, SRC, NOTE, DST, "projekt")
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    [result] = recover_moves(fresh.writer, fresh.store, "projekt")
    fresh.settle()
    assert result.state == "DONE"
    assert fresh.text(DST).count("Brief schreiben") == 1 and "Brief schreiben" not in fresh.text(SRC)
    assert recover_moves(fresh.writer, fresh.store, "projekt") == []


def test_source_changed_after_op_is_incomplete_without_loss(tmp_path: Path) -> None:
    env = Env(tmp_path, crash=("write:before_prepared", 2))
    (env.root / SRC).write_bytes(SOURCE)
    with pytest.raises(SimulatedCrash):
        move_note(env.writer, env.store, SRC, NOTE, DST, "projekt")
    env.die()
    (env.root / SRC).write_bytes(SOURCE.replace(b"Raum buchen", b"Raum buchen (B12)"))
    fresh = Env(tmp_path)
    recover(fresh.writer)
    [result] = recover_moves(fresh.writer, fresh.store, "projekt")
    assert result.state == "INCOMPLETE" and result.hint.startswith("Notiz steht jetzt in beiden Dateien")
    again = resume_move(fresh.writer, fresh.store, result.op_id, "projekt", force_source=True)
    fresh.settle()
    assert again.state == "INCOMPLETE"
    assert fresh.text(DST).count("Brief schreiben") == 1 and "Raum buchen (B12)" in fresh.text(SRC)


@pytest.mark.parametrize("crash", CRASH_POINTS, ids=[f"{p}#{n}" for p, n in CRASH_POINTS])
def test_no_content_lost_at_any_crash_point(tmp_path: Path, crash: tuple[str, int]) -> None:
    env = Env(tmp_path, crash=crash)
    (env.root / SRC).write_bytes(SOURCE)
    (env.root / DST).write_bytes(b"Elternabend #schule\n- [ ] alt\n")
    with pytest.raises(SimulatedCrash):
        move_note(env.writer, env.store, SRC, NOTE, DST, "projekt")
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    elements = ("Einladung bis Freitag", "Brief schreiben", "Raum buchen", "alt", "bleibt")
    assert all(e in fresh.text(SRC) + fresh.text(DST) for e in elements)
    results = recover_moves(fresh.writer, fresh.store, "projekt")
    fresh.settle()
    assert all(r.state == "DONE" for r in results)
    assert all((fresh.text(SRC) + fresh.text(DST)).count(e) == 1 for e in elements)


def test_todo_move_still_uses_the_same_protocol(tmp_path: Path) -> None:
    """Gemeinsamer ``_start``: ein Todo-Move legt dasselbe Manifest an wie bisher."""
    env = Env(tmp_path)
    (env.root / SRC).write_bytes(SOURCE)
    move_todo(env.writer, env.store, SRC, Target(SRC, 2, "- [ ] Brief schreiben"), DST, "projekt")
    env.settle()
    manifest = env.created[0].manifest
    assert manifest["mode"] == "todo" and set(manifest) >= {"src", "dst", "block", "block_first", "moved", "ziel"}
