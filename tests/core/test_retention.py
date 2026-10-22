"""Tests für die Aufbewahrung: Schutz der Wiederaufnahme-Abhängigkeiten (PLAN-SPAETERE-SCHRITTE.md, S6)."""

from pathlib import Path

from merkweiser.core.appdata import open_vault_data
from merkweiser.core.fsops import FsOps
from merkweiser.core.ops import OpStore
from merkweiser.core.retention import prune_ops
from merkweiser.core.step_ops import child_state, child_states, pending_ops
from tests.fakes import FakeClock

DAY = 86400


class Env:
    """Op-Store mit Fake-Uhr in einem synthetischen Vault."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "vault"
        self.root.mkdir()
        self.clock = FakeClock()
        self.data = open_vault_data(tmp_path / "app", self.root)
        self.store = OpStore(self.data, self.clock, FsOps())

    def op(self, kind: str, state: str, parent: str | None = None, **plan) -> str:
        """Legt eine Op an, setzt ihren Zustand und gibt den Lock frei."""
        op = self.store.create(kind, plan, {}, parent)
        op.set_state(state)
        op.release()
        return op.id

    def prune(self) -> list[str]:
        return prune_ops(self.root, self.data, self.store, self.clock, 30)


def test_children_and_references_of_open_parent_survive(tmp_path: Path) -> None:
    """Kinder und ``ziel_op`` einer offenen Eltern-Op bleiben, auch wenn sie alt und abgeschlossen sind."""
    env = Env(tmp_path)
    target = env.op("write", "DONE", relpath="a.md")
    parent = env.op("rueckgaengig", "INCOMPLETE", ziel_op=target)
    child = env.op("write", "DONE", parent=parent, relpath="a.md")
    loose = env.op("write", "DONE", relpath="b.md")
    env.clock.advance(40 * DAY)
    assert env.prune() == [loose]
    assert set(env.store.all_ids()) == {target, parent, child}


def test_protection_ends_when_parent_is_done(tmp_path: Path) -> None:
    """Ist der Vorgang abgeschlossen, werden seine Ops beim nächsten Lauf normal gelöscht."""
    env = Env(tmp_path)
    parent_op = env.store.create("zeitbuchung", {}, {})
    parent_op.set_state("PREPARED")
    child = env.op("write", "DONE", parent=parent_op.id, relpath="a.md")
    env.clock.advance(40 * DAY)
    assert env.prune() == []
    parent_op.set_state("DONE")
    parent_op.release()
    assert sorted(env.prune()) == sorted([parent_op.id, child])


def test_child_state_uses_latest_child_and_pending_skips_final(tmp_path: Path) -> None:
    """Jüngste Kinder-Op je Datei zählt; ``pending_ops`` liefert nur offene, vorbereitete Ops."""
    env = Env(tmp_path)
    parent = env.op("duplikat", "PREPARED")
    env.op("write", "ABORTED", parent=parent, relpath="a.md")
    env.clock.advance(1)
    env.op("write", "DONE", parent=parent, relpath="a.md")
    env.op("duplikat", "INCOMPLETE")
    env.op("duplikat", "DONE")
    assert child_state(env.store, parent, "a.md") == "DONE"
    assert child_states(env.store, parent) == {"a.md": "DONE"}
    assert child_state(env.store, parent, "b.md") is None
    assert pending_ops(env.store, "duplikat") == [parent]
