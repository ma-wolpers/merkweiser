"""Absturz an jeder Protokollgrenze, danach Wiederherstellung durch eine neue Instanz."""

from pathlib import Path

import pytest

from merkweiser.core.appdata import open_vault_data
from merkweiser.core.fsops import FsOps, SimulatedCrash
from merkweiser.core.ops import OpStore
from merkweiser.core.recovery import recover
from merkweiser.core.safe_write import Writer
from tests.fakes import FakeClock

E, N = b"Thema\n- [ ] alt\n", b"Thema\n- [x] alt\n"
NAME = "2026-01-01.md"


class TrackingStore(OpStore):
    """Merkt sich alle Ops, um ihre Locks beim simulierten Prozessende freizugeben."""

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.created = []

    def create(self, *args, **kwargs):
        op = super().create(*args, **kwargs)
        self.created.append(op)
        return op


def instance(tmp_path: Path, crash_point: str | None = None) -> tuple[Writer, TrackingStore]:
    """Neue „Prozessinstanz“ auf demselben Vault; optional Absturz an einer Grenze."""
    root = tmp_path / "vault"
    root.mkdir(exist_ok=True)
    clock = FakeClock()

    def crash(point: str) -> None:
        if point == crash_point:
            raise SimulatedCrash(point)

    data = open_vault_data(tmp_path / "app", root)
    fs = FsOps(crash_at=crash)
    store = TrackingStore(data, clock, fs)
    return Writer(root, data, store, fs, clock), store


def die(store: TrackingStore) -> None:
    """Simuliertes Prozessende: Das Betriebssystem gibt alle Locks frei."""
    for op in store.created:
        op.release()


def vault_files(tmp_path: Path) -> dict[str, bytes]:
    """Alle Dateien im Vault (auch versteckte)."""
    return {p.name: p.read_bytes() for p in (tmp_path / "vault").iterdir() if p.is_file()}


def recover_and_finish(tmp_path: Path):
    """Neue Instanz: Wiederherstellung, dann Quarantänen abschließen."""
    writer, _store = instance(tmp_path)
    report = recover(writer)
    writer.clock.advance(121)
    writer.finish_due()
    return report


WRITE_POINTS = ["write:before_prepared", "write:prepared", "write:tmp_ready", "write:displaced",
                "write:installed", "write:d_saved", "write:finished", None]


@pytest.mark.parametrize("point", WRITE_POINTS)
def test_crash_during_replace_never_loses_a_version(tmp_path: Path, point: str | None) -> None:
    """Ersetzen: nach Absturz + Wiederherstellung steht N oder (nicht ausgeführt) E, nie nichts."""
    writer, store = instance(tmp_path, point)
    (tmp_path / "vault" / NAME).write_bytes(E)
    try:
        writer.write(NAME, E, N)
    except SimulatedCrash:
        pass
    die(store)
    report = recover_and_finish(tmp_path)
    files = vault_files(tmp_path)
    assert set(files) == {NAME}, files  # keine Hilfs- oder Konfliktdateien übrig
    if files[NAME] == E:
        assert report.not_applied, "nicht ausgeführte Änderung muss gemeldet werden"
    else:
        assert files[NAME] == N
    ops = list((tmp_path / "app").rglob("vorher-*"))
    assert point in ("write:before_prepared",) or any(p.read_bytes() == E for p in ops)


@pytest.mark.parametrize("point", ["write:prepared", "write:tmp_ready", "write:installed", None])
def test_crash_during_create_only(tmp_path: Path, point: str | None) -> None:
    """Neue Datei: danach existiert sie mit N oder die Änderung ist als nicht ausgeführt gemeldet."""
    writer, store = instance(tmp_path, point)
    try:
        writer.write(NAME, None, N)
    except SimulatedCrash:
        pass
    die(store)
    report = recover_and_finish(tmp_path)
    files = vault_files(tmp_path)
    assert files == {NAME: N} or (files == {} and report.not_applied)


@pytest.mark.parametrize("point", ["remove:prepared", "remove:displaced", "remove:d_saved", None])
def test_crash_during_remove_never_loses_conflict_file(tmp_path: Path, point: str | None) -> None:
    """Entfernen: Datei ist danach weg (Bytes im Backup) oder unverändert da."""
    writer, store = instance(tmp_path, point)
    (tmp_path / "vault" / "k.md").write_bytes(E)
    try:
        writer.remove("k.md", E)
    except SimulatedCrash:
        pass
    die(store)
    recover_and_finish(tmp_path)
    files = vault_files(tmp_path)
    assert files in ({}, {"k.md": E})
    if not files:
        assert any(p.read_bytes() == E for p in (tmp_path / "app").rglob("vorher-*"))


def test_recovery_is_idempotent_and_survives_its_own_crash(tmp_path: Path) -> None:
    """Abbruch während der Wiederherstellung → erneuter Start führt zum selben Endzustand."""
    writer, store = instance(tmp_path, "write:displaced")
    (tmp_path / "vault" / NAME).write_bytes(E)
    with pytest.raises(SimulatedCrash):
        writer.write(NAME, E, N)
    die(store)
    second, second_store = instance(tmp_path, "write:d_saved")
    with pytest.raises(SimulatedCrash):
        recover(second)
    for op in [*second_store.created]:
        op.release()
    second._pending.clear()
    import gc

    gc.collect()
    recover_and_finish(tmp_path)
    recover_and_finish(tmp_path)
    assert vault_files(tmp_path) == {NAME: N}


def test_missing_main_with_displaced_file_is_restored_not_deleted(tmp_path: Path) -> None:
    """Hauptdatei fehlt, D existiert: wird wiederhergestellt, nie als Löschung gewertet."""
    writer, store = instance(tmp_path, "write:displaced")
    (tmp_path / "vault" / NAME).write_bytes(E)
    with pytest.raises(SimulatedCrash):
        writer.write(NAME, E, N)
    die(store)
    assert NAME not in vault_files(tmp_path)  # Zustand nach dem Absturz
    recover_and_finish(tmp_path)
    assert vault_files(tmp_path)[NAME] == N


def test_busy_op_of_other_instance_is_not_taken_over(tmp_path: Path) -> None:
    """Hält eine (auch suspendierte) Instanz den Lock, übernimmt die Wiederherstellung nicht."""
    writer, store = instance(tmp_path, "write:displaced")
    (tmp_path / "vault" / NAME).write_bytes(E)
    with pytest.raises(SimulatedCrash):
        writer.write(NAME, E, N)  # Lock bleibt gehalten: „suspendierte“ Instanz
    other, _ = instance(tmp_path)
    report = recover(other)
    assert report.busy_paths == {NAME} and report.results == []
    die(store)


def test_orphan_side_files_become_conflicts_never_deleted(tmp_path: Path) -> None:
    """Verwaiste Hilfsdateien ohne Op werden zu Konfliktdateien (Inhalt bleibt sichtbar)."""
    writer, _ = instance(tmp_path)
    (tmp_path / "vault" / ".x.md.mw-20260101-000000-ABCDEFGH.old").write_bytes(E)
    report = recover(writer)
    assert len(report.orphans) == 1
    files = vault_files(tmp_path)
    assert [v for k, v in files.items() if ".sync-conflict-" in k] == [E]
