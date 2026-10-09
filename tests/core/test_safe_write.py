"""Tests für das Tausch-Protokoll: fremde Schreiber an jeder kritischen Stelle."""

import sys
from pathlib import Path

import pytest

from merkweiser.core.appdata import open_vault_data
from merkweiser.core.fsops import FileBusyError, FsOps
from merkweiser.core.ops import OpStore
from merkweiser.core.safe_write import ChangedBeforeWriteError, Writer, side_paths
from tests.fakes import FakeClock

E, N, X = b"Thema\n- [ ] alt\n", b"Thema\n- [x] alt\n", b"Thema\n- [ ] fremd\n"


class Env:
    """Synthetischer Vault mit Writer; ``on`` setzt Aktionen an Protokollgrenzen."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "vault"
        self.root.mkdir()
        self.clock = FakeClock()
        self.actions: dict[str, callable] = {}
        data = open_vault_data(tmp_path / "app", self.root)
        self.fs = FsOps(crash_at=lambda point: self.actions.pop(point, lambda: None)())
        self.writer = Writer(self.root, data, OpStore(data, self.clock, self.fs), self.fs, self.clock)
        self.ops = data.ops_dir

    def on(self, point: str, action) -> None:
        """Registriert eine einmalige Aktion an einer Protokollgrenze."""
        self.actions[point] = action

    def files(self) -> dict[str, bytes]:
        """Alle sichtbaren und versteckten Dateien im Vault."""
        return {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}

    def conflicts(self) -> list[bytes]:
        """Inhalte aller Konfliktdateien."""
        return [p.read_bytes() for p in self.root.iterdir() if ".sync-conflict-" in p.name]

    def finish(self) -> list:
        """Quarantäne ablaufen lassen und abschließen."""
        self.clock.advance(121)
        return self.writer.finish_due()


@pytest.fixture
def env(tmp_path: Path) -> Env:
    """Frische Testumgebung mit Datei ``2026-01-01.md`` = E."""
    environment = Env(tmp_path)
    (environment.root / "2026-01-01.md").write_bytes(E)
    return environment


def test_happy_path_replaces_and_cleans_up(env: Env) -> None:
    """Normalfall: N installiert, nach der Quarantäne keine Hilfsdateien, E im Backup."""
    result = env.writer.write("2026-01-01.md", E, N)
    assert result.state == "QUARANTINE" and (env.root / "2026-01-01.md").read_bytes() == N
    assert [r.state for r in env.finish()] == ["DONE"]
    assert env.files() == {"2026-01-01.md": N}
    backup = next(env.ops.iterdir())
    assert any(p.read_bytes() == E for p in backup.iterdir() if p.name.startswith("vorher-"))


def test_changed_before_write_creates_nothing(env: Env) -> None:
    """Weicht die Datei vorher ab, wird nichts verändert und keine Op angelegt."""
    with pytest.raises(ChangedBeforeWriteError):
        env.writer.write("2026-01-01.md", X, N)
    assert env.files() == {"2026-01-01.md": E} and not list(env.ops.iterdir())


def test_external_write_before_displace_keeps_foreign_version(env: Env) -> None:
    """Fremde Änderung zwischen Prüfung und Wegbenennen: X bleibt Hauptdatei, N wird Konfliktdatei."""
    env.on("write:tmp_ready", lambda: (env.root / "2026-01-01.md").write_bytes(X))
    result = env.writer.write("2026-01-01.md", E, N)
    assert result.state == "CONFLICTED"
    assert (env.root / "2026-01-01.md").read_bytes() == X and env.conflicts() == [N]


def test_external_create_while_path_missing(env: Env) -> None:
    """P während des Tauschs extern neu angelegt: nie überschreiben, N als Konfliktdatei."""
    env.on("write:displaced", lambda: (env.root / "2026-01-01.md").write_bytes(X))
    env.writer.write("2026-01-01.md", E, N)
    env.finish()
    assert (env.root / "2026-01-01.md").read_bytes() == X and env.conflicts() == [N]
    assert not any(".mw-" in name for name in env.files())


def test_external_replace_during_quarantine_makes_n_visible(env: Env) -> None:
    """P wird in der Quarantäne extern ersetzt: X bleibt, N wird sichtbar, D=E wird gelöscht."""
    env.writer.write("2026-01-01.md", E, N)
    (env.root / "2026-01-01.md").write_bytes(X)
    results = env.finish()
    assert results[0].state == "CONFLICTED"
    assert (env.root / "2026-01-01.md").read_bytes() == X and env.conflicts() == [N]
    assert not any(".mw-" in name for name in env.files())


def test_late_write_into_displaced_file_is_rescued(env: Env) -> None:
    """Schreibt jemand in der Quarantäne in D (offenes Handle), wird D zur Konfliktdatei."""
    result = env.writer.write("2026-01-01.md", E, N)
    _tmp, old = side_paths(env.root / "2026-01-01.md", result.op_id)
    old.write_bytes(X)
    env.finish()
    assert (env.root / "2026-01-01.md").read_bytes() == N and env.conflicts() == [X]


def test_quarantine_uses_monotonic_time(env: Env) -> None:
    """Ein Sprung der Wanduhr beendet die Quarantäne nicht vorzeitig."""
    env.writer.write("2026-01-01.md", E, N)
    env.clock.jump_wall(10_000)
    assert env.writer.finish_due() == []
    env.clock.advance(121)
    assert len(env.writer.finish_due()) == 1


def test_create_only_never_overwrites_foreign_file(env: Env) -> None:
    """Neue Datei, die zwischendurch extern entsteht: fremde bleibt, N wird Konfliktdatei."""
    env.on("write:tmp_ready", lambda: (env.root / "2026-01-02.md").write_bytes(X))
    result = env.writer.write("2026-01-02.md", None, N)
    assert result.state == "CONFLICTED"
    assert (env.root / "2026-01-02.md").read_bytes() == X and env.conflicts() == [N]


def test_create_only_happy_path(env: Env) -> None:
    """Neue Tagesdatei wird angelegt und nach der Quarantäne abgeschlossen."""
    assert env.writer.write("2026-01-02.md", None, N).state == "QUARANTINE"
    assert [r.state for r in env.finish()] == ["DONE"]
    assert (env.root / "2026-01-02.md").read_bytes() == N


def test_remove_only_unchanged_and_never_blind(env: Env) -> None:
    """Entfernen nur bei unverändertem Inhalt; Änderung während des Tauschs → zurück, nichts verloren."""
    (env.root / "c.md").write_bytes(X)
    with pytest.raises(ChangedBeforeWriteError):
        env.writer.remove("c.md", E)
    env.writer.remove("c.md", X)
    env.finish()
    assert "c.md" not in env.files()
    (env.root / "d.md").write_bytes(X)
    blocked: list[bool] = []

    def foreign_write_into_displaced() -> None:
        try:
            next(env.root.glob(".d.md.mw-*.old")).write_bytes(E)
            blocked.append(False)
        except PermissionError:  # Windows: Schreibsperre des Protokolls greift
            blocked.append(True)

    env.on("remove:displaced", foreign_write_into_displaced)
    state = env.writer.remove("d.md", X).state
    if sys.platform == "win32":
        assert blocked == [True] and state == "QUARANTINE"
    else:
        assert blocked == [False] and state == "CONFLICTED"
        assert (env.root / "d.md").read_bytes() == E


@pytest.mark.skipif(sys.platform != "win32", reason="Schreibsperre nur unter Windows")
def test_windows_busy_file_aborts_without_change(env: Env) -> None:
    """Hält ein anderer Prozess die Datei zum Schreiben offen, bricht das Protokoll ohne Änderung ab."""
    with open(env.root / "2026-01-01.md", "r+b"):
        with pytest.raises(FileBusyError):
            env.writer.write("2026-01-01.md", E, N)
    assert env.files() == {"2026-01-01.md": E}
