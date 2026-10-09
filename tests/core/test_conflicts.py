"""Tests für Konflikterkennung, Auto-Merge, Rückgängig und manuelle Auflösung mit Marker."""

import shutil
from pathlib import Path

import pytest

from merkweiser.core.appdata import open_vault_data
from merkweiser.core.conflicts import CaseKind, auto_merge, classify, undo_automerge
from merkweiser.core.fsops import FsOps, SimulatedCrash
from merkweiser.core.ops import OpStore
from merkweiser.core.recovery import recover
from merkweiser.core.resolve import manual_only_paths, recover_resolves, resolve
from merkweiser.core.safe_write import Writer
from merkweiser.core.vault import DayPattern, scan
from tests.fakes import FakeClock

MAIN = "2026-01-01.md"
CONF = "2026-01-01.sync-conflict-20260101-120000-ABCDEFG.md"
BASE = b"Notiz\n\n- [ ] Aufgabe A\n"


class Env:
    """Synthetischer Vault mit Writer, Store und optionalem Absturzpunkt."""

    def __init__(self, tmp_path: Path, crash: str | None = None) -> None:
        self.tmp, self.root = tmp_path, tmp_path / "vault"
        self.root.mkdir(exist_ok=True)
        self.clock = FakeClock()
        self.data = open_vault_data(tmp_path / "app", self.root)

        def crash_at(point: str) -> None:
            if point == crash:
                raise SimulatedCrash(point)

        self.fs = FsOps(crash_at=crash_at)
        self.store = OpStore(self.data, self.clock, self.fs)
        self.created = []
        original_create = self.store.create

        def tracking_create(*args, **kwargs):
            op = original_create(*args, **kwargs)
            self.created.append(op)
            return op

        self.store.create = tracking_create
        self.writer = Writer(self.root, self.data, self.store, self.fs, self.clock)

    def put(self, name: str, data: bytes) -> None:
        (self.root / name).write_bytes(data)

    def get(self, name: str) -> bytes | None:
        path = self.root / name
        return path.read_bytes() if path.exists() else None

    def cases(self):
        return classify(self.root, self.writer, scan(self.root, DayPattern()), set(), manual_only_paths(self.store))

    def die(self) -> None:
        """Simuliertes Prozessende: Das Betriebssystem gibt alle Locks dieser Instanz frei."""
        for op in self.created:
            op.release()
        self.writer._pending.clear()

    def settle(self) -> None:
        """Quarantänen abschließen."""
        self.clock.advance(121)
        self.writer.finish_due()


def test_concept_example_auto_merges_and_can_be_undone(tmp_path: Path) -> None:
    """Syncthing-Konflikt ohne Basis: automatisch „beide“, protokolliert und rückgängig zu machen."""
    env = Env(tmp_path)
    env.put(MAIN, BASE + b"- [ ] Aufgabe B\n")
    env.put(CONF, BASE + b"- [ ] Aufgabe C\n")
    [case] = env.cases()
    assert case.kind is CaseKind.AUTO
    op_id = auto_merge(env.writer, env.store, case)
    env.settle()
    assert env.get(MAIN) == BASE + b"- [ ] Aufgabe B\n- [ ] Aufgabe C\n" and env.get(CONF) is None
    undo_automerge(env.writer, env.store, op_id)
    env.settle()
    assert env.get(MAIN) == BASE + b"- [ ] Aufgabe B\n" and env.get(CONF) == BASE + b"- [ ] Aufgabe C\n"


def test_crlf_main_keeps_line_endings_after_merge(tmp_path: Path) -> None:
    """Das Ergebnis übernimmt Zeilenende-Stil und Schluss-Umbruch der Hauptdatei."""
    env = Env(tmp_path)
    env.put(MAIN, b"T\r\n- [ ] a\r\n")
    env.put(CONF, b"T\n- [ ] a\n- [ ] b\n")
    auto_merge(env.writer, env.store, env.cases()[0])
    env.settle()
    assert env.get(MAIN) == b"T\r\n- [ ] a\r\n- [ ] b\r\n"


def test_nested_decided_and_deleted_main_are_manual(tmp_path: Path) -> None:
    """Verschachtelt, entschieden (Marker) und fehlende Hauptdatei → nie automatisch."""
    env = Env(tmp_path)
    env.put("a.md", b"x\n")
    env.put("a.sync-conflict-20260101-120000-AAAAAAA.sync-conflict-20260102-120000-BBBBBBB.md", b"y\n")
    env.put("b.md", b"x\n")
    env.put("b.sync-conflict-20260101-120000-ABCDEFGMWENTSCHIEDEN.md", b"y\n")
    env.put("c.sync-conflict-20260101-120000-ABCDEFG.md", b"y\n")
    kinds = {case.conflict.main_relpath: case.kind for case in env.cases()}
    assert kinds == {"a.md": CaseKind.MANUAL, "b.md": CaseKind.MANUAL, "c.md": CaseKind.MAIN_DELETED}


def test_own_conflict_with_sidecar_uses_reliable_base(tmp_path: Path) -> None:
    """Eigene Konfliktdatei mit Sidecar-Basis: diff3 (Löschung auf einer Seite bleibt gelöscht)."""
    env = Env(tmp_path)
    e = b"T\n- [ ] a\nMitte\n- [ ] b\n"
    env.put(MAIN, e)
    env.writer.write(MAIN, e, b"T\n- [x] a\nMitte\n- [ ] b\n")
    env.put(MAIN, b"T\n- [ ] a\nMitte\n")  # extern: b gelöscht (in Quarantäne)
    env.settle()  # N wird eigene Konfliktdatei mit Basis E
    [case] = env.cases()
    assert case.conflict.own and case.kind is CaseKind.AUTO
    auto_merge(env.writer, env.store, case)
    env.settle()
    assert env.get(MAIN) == b"T\n- [x] a\nMitte\n"  # Abhaken übernommen, Löschung von b bleibt


def test_adjacent_changes_on_both_sides_are_manual_grenze(tmp_path: Path) -> None:
    """GRENZE: Änderungen beider Seiten an benachbarten Zeilen (kein Anker dazwischen) → Konflikt."""
    env = Env(tmp_path)
    e = b"T\n- [ ] a\n- [ ] b\n"
    env.put(MAIN, e)
    env.writer.write(MAIN, e, b"T\n- [x] a\n- [ ] b\n")
    env.put(MAIN, b"T\n- [ ] a\n")
    env.settle()
    [case] = env.cases()
    assert case.kind is CaseKind.MANUAL and case.merge is not None and case.merge.hunks


def test_manual_resolution_with_marker_completes(tmp_path: Path) -> None:
    """Manuelle Wahl: Marker, Hauptdatei = Ergebnis, Konfliktdatei entfernt."""
    env = Env(tmp_path)
    env.put(MAIN, b"A\n")
    env.put(CONF, b"B\n")
    outcome = resolve(env.writer, env.store, MAIN, b"A\n", CONF, b"B\n", b"A\n", "A behalten")
    env.settle()
    assert outcome.state == "DONE" and env.get(MAIN) == b"A\n"
    assert [p.name for p in env.root.iterdir()] == [MAIN]


@pytest.mark.parametrize("point", ["resolve:prepared", "resolve:marked", "resolve:main_written"])
def test_crash_during_resolution_never_undoes_choice(tmp_path: Path, point: str) -> None:
    """Wahl „nur A“, Absturz → Wiederherstellung setzt fort; B wird nie wieder eingefügt."""
    env = Env(tmp_path, crash=point)
    env.put(MAIN, BASE)
    env.put(CONF, BASE + b"- [ ] B\n")
    with pytest.raises(SimulatedCrash):
        resolve(env.writer, env.store, MAIN, BASE, CONF, BASE + b"- [ ] B\n", BASE + b"- [ ] neu\n", "bearbeitet")
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    recover_resolves(fresh.writer, fresh.store)
    fresh.settle()
    assert fresh.get(MAIN) == BASE + b"- [ ] neu\n"
    assert [p.name for p in fresh.root.iterdir()] == [MAIN]


def test_lost_app_data_after_marker_asks_again(tmp_path: Path) -> None:
    """Fall k: App-Daten weg, Marker im Vault → kein Auto-Merge, erneute Rückfrage."""
    env = Env(tmp_path, crash="resolve:marked")
    env.put(MAIN, BASE)
    env.put(CONF, BASE + b"- [ ] B\n")
    with pytest.raises(SimulatedCrash):
        resolve(env.writer, env.store, MAIN, BASE, CONF, BASE + b"- [ ] B\n", BASE, "A behalten")
    env.die()
    shutil.rmtree(tmp_path / "app", ignore_errors=True)
    fresh = Env(tmp_path)
    [case] = fresh.cases()
    assert case.kind is CaseKind.MANUAL and case.conflict.decided
    assert fresh.get(MAIN) == BASE


def test_conflict_changed_after_decision_is_never_deleted(tmp_path: Path) -> None:
    """Fall f: Konfliktdatei nach der Entscheidung geändert → bleibt, nur manuell."""
    env = Env(tmp_path, crash="resolve:main_written")
    env.put(MAIN, b"A\n")
    env.put(CONF, b"B\n")
    with pytest.raises(SimulatedCrash):
        resolve(env.writer, env.store, MAIN, b"A\n", CONF, b"B\n", b"A\n", "A behalten")
    env.die()
    marked = next(p for p in env.root.iterdir() if "MWENTSCHIEDEN" in p.name)
    marked.write_bytes(b"B neu\n")
    fresh = Env(tmp_path)
    recover(fresh.writer)
    [outcome] = recover_resolves(fresh.writer, fresh.store)
    assert outcome.state == "DONE" and outcome.hint
    assert marked.read_bytes() == b"B neu\n"
    assert all(case.kind is CaseKind.MANUAL for case in fresh.cases())


def test_externally_removed_conflict_before_apply_is_reported(tmp_path: Path) -> None:
    """Fall i: Konfliktdatei extern entfernt, bevor die Wahl angewendet war → Hinweis, nichts automatisch."""
    env = Env(tmp_path, crash="resolve:prepared")
    env.put(MAIN, b"A\n")
    env.put(CONF, b"B\n")
    with pytest.raises(SimulatedCrash):
        resolve(env.writer, env.store, MAIN, b"A\n", CONF, b"B\n", b"B\n", "B übernehmen")
    env.die()
    (env.root / CONF).unlink()
    fresh = Env(tmp_path)
    [outcome] = recover_resolves(fresh.writer, fresh.store)
    assert outcome.state == "INTERRUPTED" and "extern entfernt" in outcome.hint
    assert fresh.get(MAIN) == b"A\n"


def test_main_deleted_restore_one_version_rest_manual(tmp_path: Path) -> None:
    """MAIN_DELETED: genau eine Version wiederherstellen, übrige nur manuell."""
    env = Env(tmp_path)
    other = "2026-01-01.sync-conflict-20260102-120000-BBBBBBB.md"
    env.put(CONF, b"Version A\n")
    env.put(other, b"Version B\n")
    assert {c.kind for c in env.cases()} == {CaseKind.MAIN_DELETED}
    resolve(env.writer, env.store, MAIN, None, CONF, b"Version A\n", b"Version A\n", "A wiederherstellen",
            manual_only=(other,))
    env.settle()
    assert env.get(MAIN) == b"Version A\n"
    [case] = env.cases()
    assert case.conflict.relpath == other and case.kind is CaseKind.MANUAL
