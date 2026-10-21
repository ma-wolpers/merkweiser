"""Aufräumen beim Start: leere Tagesdateien (nur Leerraum und ``---``) werden sicher entfernt."""

from pathlib import Path

import pytest

from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings
from merkweiser.core.cleanup import is_empty_day_text
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
