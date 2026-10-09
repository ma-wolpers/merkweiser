"""Tests für Watcher, App-Daten-Layout und Beobachtungs-Historie."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from merkweiser.core.appdata import open_vault_data, vault_id
from merkweiser.core.history import History
from merkweiser.core.watch import observe, poll
from tests.fakes import FakeClock


def test_poll_reports_differences_only(tmp_path: Path) -> None:
    """Hinzugefügt, entfernt, geändert; versteckte und Nicht-.md-Dateien zählen nicht."""
    (tmp_path / "a.md").write_text("a")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "x.md").write_text("x")
    (tmp_path / "bild.png").write_bytes(b"\x89")
    state = observe(tmp_path)
    assert set(state) == {"a.md"}
    (tmp_path / "b.md").write_text("b")
    (tmp_path / "a.md").write_text("a2")
    os.utime(tmp_path / "a.md", ns=(1, 5_000_000_000))
    changes, state = poll(tmp_path, state)
    assert (changes.added, changes.modified, changes.removed) == ({"b.md"}, {"a.md"}, set())
    (tmp_path / "b.md").unlink()
    changes, _ = poll(tmp_path, state)
    assert changes.removed == {"b.md"} and changes.any


def test_poll_reports_only_end_state_of_multiple_changes(tmp_path: Path) -> None:
    """Zwei Änderungen zwischen zwei Polls: nur der Endstand wird gemeldet (kein Event-System)."""
    (tmp_path / "a.md").write_text("1")
    state = observe(tmp_path)
    (tmp_path / "a.md").write_text("22")
    (tmp_path / "a.md").write_text("333")
    changes, new_state = poll(tmp_path, state)
    assert changes.modified == {"a.md"} and new_state["a.md"][1] == 3


def test_vault_ids_differ_and_app_data_outside_vault(tmp_path: Path) -> None:
    """Zwei Vaults → verschiedene IDs; App-Daten im Vault sind verboten."""
    one, two, app = tmp_path / "v1", tmp_path / "v2", tmp_path / "app"
    one.mkdir(), two.mkdir()
    assert vault_id(one) != vault_id(two)
    assert open_vault_data(app, one).base != open_vault_data(app, two).base
    with pytest.raises(ValueError):
        open_vault_data(one / "daten", one)


def history(tmp_path: Path, root_name: str = "vault") -> tuple[History, FakeClock]:
    """Hilfsfunktion: Historie für einen synthetischen Vault."""
    root = tmp_path / root_name
    root.mkdir(exist_ok=True)
    clock = FakeClock()
    return History(open_vault_data(tmp_path / "app", root), clock), clock


def test_history_appends_and_never_overwrites(tmp_path: Path) -> None:
    """Neue Versionen werden angehängt, erneutes Lesen ändert nur Metadaten."""
    hist, clock = history(tmp_path)
    hist.record("a.md", b"v1")
    clock.advance(60)
    hist.record("a.md", b"v2")
    clock.advance(60)
    hist.record("a.md", b"v2")
    versions = hist.versions("a.md")
    assert len(versions) == 2
    current, old = versions
    assert current.replaced_since is None and old.replaced_since is not None
    assert hist.read("a.md", old.sha1) == b"v1"


def test_two_vaults_with_same_relpath_share_no_history(tmp_path: Path) -> None:
    """Gleicher relativer Pfad in zwei Vaults → getrennte Historien."""
    one, _ = history(tmp_path, "v1")
    two, _ = history(tmp_path, "v2")
    one.record("2026-01-01.md", b"eins")
    assert two.versions("2026-01-01.md") == []


def test_prune_counts_from_replaced_since_not_last_seen(tmp_path: Path) -> None:
    """Aufbewahrung ab „ersetzt seit“; aktuelle, neueste N und geschützte Versionen bleiben."""
    hist, clock = history(tmp_path)
    for i in range(8):
        hist.record("a.md", f"v{i}".encode())
        clock.advance(3600)
    clock.advance(31 * 24 * 3600)
    hist.record("a.md", b"v7")  # tägliches Lesen verlängert alte Versionen nicht
    protected = {v.sha1 for v in hist.versions("a.md") if hist.read("a.md", v.sha1) == b"v0"}
    removed = hist.prune("a.md", protected=protected, keep=5)
    remaining = {hist.read("a.md", v.sha1) for v in hist.versions("a.md")}
    assert len(removed) == 2
    assert remaining == {b"v0", b"v3", b"v4", b"v5", b"v6", b"v7"}


def test_deleted_file_marks_version_replaced(tmp_path: Path) -> None:
    """Eine verschwundene Datei setzt „ersetzt seit“ der letzten Version."""
    hist, _ = history(tmp_path)
    hist.record("a.md", b"v1")
    hist.record("a.md", None)
    assert hist.versions("a.md")[0].replaced_since is not None


def test_candidate_base_is_heuristic_before_stamp(tmp_path: Path) -> None:
    """Kandidat: neueste Version vor dem Zeitpunkt, die keiner Konfliktseite gleicht."""
    hist, clock = history(tmp_path)
    hist.record("a.md", b"basis")
    clock.advance(600)
    hist.record("a.md", b"seite A")
    shas = {hist.read("a.md", v.sha1): v.sha1 for v in hist.versions("a.md")}
    stamp = clock.now() + timedelta(seconds=1)
    assert hist.candidate_base("a.md", stamp, exclude={shas[b"seite A"]}) == shas[b"basis"]
    early = datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert hist.candidate_base("a.md", early, exclude=set()) is None
