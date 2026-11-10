"""Aufräumen beim Start: leere Tagesdateien (nur Leerraum und ``---``) werden sicher entfernt."""

from pathlib import Path

import pytest

from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings
from merkweiser.core.backups import changes
from merkweiser.core.cleanup import empty_deleted_versions, is_empty_day_text, is_empty_version
from merkweiser.core.conflicts import CaseKind, ConflictCase
from merkweiser.core.vault import parse_conflict_name
from tests.fakes import FakeClock


@pytest.mark.parametrize("raw, empty", [
    (b"", True),
    (b"\n\n  \t\r\n", True),
    (b"\n---\n\n---\n", True),
    (b"  ---  \r\n", True),
    (b"\xef\xbb\xbf\n", False),          # BOM: vorsichtshalber behalten
    (b"---\ntags: [a]\n---\n", False),   # Frontmatter ist Inhalt
    (b"\n.\n", False),
    (b"--\n", False),
    (b"\xff\xfe", False),                # kein UTF-8
])
def test_is_empty_day_text(raw: bytes, empty: bool) -> None:
    """Nur Leerraum und Trennzeilen gelten als leer; BOM, Frontmatter, Text, fremdes Encoding nicht."""
    assert is_empty_day_text(raw) is empty


def test_start_removes_only_safe_empty_day_files(tmp_path: Path) -> None:
    """Start entfernt leere Tagesdateien, behält gefüllte, BOM-Dateien, Dateien mit Konflikt und Nicht-Tagesdateien."""
    root = tmp_path / "vault"
    root.mkdir()
    files = {
        "2026-01-10.md": b"\n\n",
        "2026-01-11.md": b"\n---\n\n",
        "2026-01-12.md": b"Notiz\n",
        "2026-01-13.md": b"\xef\xbb\xbf\n",
        "2026-01-14.md": b"\n",
        "2026-01-14.sync-conflict-20260114-120000-ABCDEFG.md": b"Notiz\n",
        "Einkauf.md": b"\n",
    }
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    clock = FakeClock()
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), clock)
    report = svc.start()
    assert sorted(report.removed_empty) == ["2026-01-10.md", "2026-01-11.md"]
    clock.advance(30)
    svc.poll()
    remaining = sorted(p.name for p in root.iterdir())
    assert remaining == ["2026-01-12.md", "2026-01-13.md", "2026-01-14.md", "Einkauf.md"]
    # Die leere Datei mit Konflikt blieb stehen; danach hat der Auto-Merge den Konflikt hineingeführt.
    assert b"Notiz" in (root / "2026-01-14.md").read_bytes()


@pytest.mark.parametrize("raw, empty", [
    (b"", True),
    (b"\xef\xbb\xbf", True),
    (b"\xef\xbb\xbf\r\n\r\n", True),
    (b"---\n\n", True),
    (b"Notiz\n", False),
    (b"\xef\xbb\xbfNotiz\n", False),
    (b"\xff\xfe", False),
])
def test_is_empty_version(raw: bytes, empty: bool) -> None:
    """Konfliktversionen: wie leere Tagesdateien, aber eine BOM zählt nicht als Inhalt."""
    assert is_empty_version(raw) is empty


def _case(relpath: str, raw: bytes, kind: CaseKind = CaseKind.MAIN_DELETED) -> ConflictCase:
    """Konfliktfall ohne Vault (nur für die Auswahl)."""
    return ConflictCase(kind, parse_conflict_name(relpath), None, raw, None, "")


def test_empty_deleted_versions_skips_busy_decided_manual_and_content() -> None:
    """Nur leere, unmarkierte, freie MAIN_DELETED-Versionen werden zum Verwerfen ausgewählt."""
    plain = _case("a.sync-conflict-20260101-120000-AAAAAAA.md", b"")
    cases = [
        plain,
        _case("b.sync-conflict-20260101-120000-AAAAAAA.md", b"x\n"),
        _case("c.sync-conflict-20260101-120000-AAAAAAAMWENTSCHIEDEN.md", b""),
        _case("d.sync-conflict-20260101-120000-AAAAAAA.md", b""),
        _case("e.sync-conflict-20260101-120000-AAAAAAA.md", b""),
        _case("f.sync-conflict-20260101-120000-AAAAAAA.md", b"", CaseKind.MANUAL),
    ]
    chosen = empty_deleted_versions(cases, busy={"d.md"}, manual={"e.sync-conflict-20260101-120000-AAAAAAA.md"})
    assert chosen == [plain]


def test_start_discards_empty_versions_of_missing_main(tmp_path: Path) -> None:
    """Start: leere Versionen fehlender Hauptdateien sind verworfen (mit Backup), gefüllte bleiben als Fall."""
    root = tmp_path / "vault"
    root.mkdir()
    files = {
        "2026-01-01.sync-conflict-20260101-120000-ABCDEFG.md": b"",
        "2026-01-02.sync-conflict-20260102-120000-ABCDEFG.md": b"\xef\xbb\xbf",
        "2026-01-03.sync-conflict-20260103-120000-ABCDEFG.md": b"Notiz\n",
    }
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    clock = FakeClock()
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), clock)
    report = svc.start()
    assert sorted(report.discarded_empty) == sorted(list(files)[:2])
    clock.advance(30)
    svc.poll()
    assert sorted(p.name for p in root.iterdir()) == [list(files)[2]]
    [case] = svc.conflicts()
    assert case.kind is CaseKind.MAIN_DELETED and case.conflict_bytes == b"Notiz\n"
    assert {c.relpath for c in changes(svc.store) if c.kind == "gelöscht"} >= {
        name[: -len(".md")] + "MWENTSCHIEDEN.md" for name in list(files)[:2]}
