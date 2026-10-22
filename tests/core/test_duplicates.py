"""Tests für doppelte Notizen (W3, PLAN-SPAETERE-SCHRITTE.md S3/Y3)."""

from datetime import date
from pathlib import Path

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.duplicates import find_duplicates, keep_one, recover_duplicates, resume_duplicate
from merkweiser.core.fsops import SimulatedCrash
from merkweiser.core.recovery import recover
from tests.core.test_move_exec import Env

NOTE = b"Elternabend #schule\n- [ ] Raum buchen\n"
A, B, C = "2026-01-01.md", "2026-01-02.md", "2026-01-03.md"


def docs(env: Env, names: list[str]):
    return [(n, date.fromisoformat(n[:10]), parse_document((env.root / n).read_bytes(), "")) for n in names]


def filler(name: str) -> bytes:
    """Eindeutige Füllnotiz je Datei (sonst wäre sie selbst ein Duplikat)."""
    return f"Anderes {name}\n- x\n\n".encode()


def three(tmp_path: Path, crash=None) -> Env:
    env = Env(tmp_path, crash=crash)
    for name in (A, B, C):
        (env.root / name).write_bytes(filler(name) + NOTE)
    return env


def test_line_endings_do_not_matter_and_same_file_is_ignored(tmp_path: Path) -> None:
    """LF = CRLF; zweimal in derselben Datei wird nicht gemeldet; Fundstellen nach Datum."""
    env = Env(tmp_path)
    (env.root / B).write_bytes(NOTE.replace(b"\n", b"\r\n"))
    (env.root / A).write_bytes(NOTE)
    (env.root / C).write_bytes(b"Nur hier\n\nNur hier\n")
    [group] = find_duplicates(docs(env, [B, A, C]))
    assert [p.relpath for p in group.places] == [A, B]
    assert group.lines == ("Elternabend #schule", "- [ ] Raum buchen")
    assert find_duplicates(docs(env, [C])) == []


def test_keep_one_deletes_the_others(tmp_path: Path) -> None:
    env = three(tmp_path)
    [group] = find_duplicates(docs(env, [A, B, C]))
    assert keep_one(env.writer, env.store, group, 0) == ""
    env.settle()
    assert env.text(A) == (filler(A) + NOTE).decode()
    assert env.text(B) == f"Anderes {B}\n- x\n" and env.text(C) == f"Anderes {C}\n- x\n"


def test_crash_after_first_deletion_keeps_the_choice(tmp_path: Path) -> None:
    """A gewählt, B gelöscht, Absturz → Wiederaufnahme löscht C, A bleibt (Auswahl aus dem Manifest)."""
    env = three(tmp_path, crash=("write:before_prepared", 2))
    [group] = find_duplicates(docs(env, [A, B, C]))
    with pytest.raises(SimulatedCrash):
        keep_one(env.writer, env.store, group, 0)
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    fresh.settle()
    assert len(recover_duplicates(fresh.writer, fresh.store)) == 1
    fresh.settle()
    assert NOTE.decode() in fresh.text(A)
    assert NOTE.decode() not in fresh.text(B) and NOTE.decode() not in fresh.text(C)


def test_changed_place_is_not_deleted(tmp_path: Path) -> None:
    """C inzwischen verändert → C bleibt, Vorgang meldet es (INCOMPLETE)."""
    env = three(tmp_path)
    [group] = find_duplicates(docs(env, [A, B, C]))
    (env.root / C).write_bytes(filler(C) + NOTE + b"- [ ] neu\n")
    hint = keep_one(env.writer, env.store, group, 0)
    env.settle()
    assert C in hint
    assert "neu" in env.text(C) and NOTE.decode() not in env.text(B)


def test_missing_kept_version_deletes_nothing(tmp_path: Path) -> None:
    """Behaltene Fassung fehlt → nichts wird gelöscht; „Erneut prüfen“ bleibt sicher."""
    env = three(tmp_path)
    [group] = find_duplicates(docs(env, [A, B, C]))
    (env.root / A).write_bytes(filler(A))
    hint = keep_one(env.writer, env.store, group, 0)
    assert "Behaltene Fassung" in hint
    assert NOTE.decode() in env.text(B) and NOTE.decode() in env.text(C)
    op_id = env.store.all_ids()[-1]
    assert "Behaltene Fassung" in resume_duplicate(env.writer, env.store, op_id)


def test_two_copies_in_one_other_file_are_skipped(tmp_path: Path) -> None:
    """Steht die Notiz in einer anderen Datei doppelt, wird dort nichts gelöscht (nicht eindeutig)."""
    env = three(tmp_path)
    [group] = find_duplicates(docs(env, [A, B, C]))
    (env.root / C).write_bytes(NOTE + b"\n" + NOTE)
    hint = keep_one(env.writer, env.store, group, 0)
    env.settle()
    assert C in hint and env.text(C).count("Elternabend") == 2
