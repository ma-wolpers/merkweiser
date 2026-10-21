"""Rauchtest der Mobile-Ansichten: jeder Tab baut seine Controls ohne Gerät und Fenster.

Wird übersprungen, wenn Flet nicht installiert ist (Extra ``ui``).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.notes_service import NotesService  # noqa: E402
from merkweiser.app.settings import Settings  # noqa: E402
from merkweiser.mobile.ui import tabs  # noqa: E402
from tests.fakes import FakeClock  # noqa: E402


class FakeAccess:
    """Ordnerzugriff ohne Android."""

    async def pick_folder(self):
        return None

    def has_all_files_access(self):
        return None

    def request_all_files_access(self):
        return False


def app(tmp_path: Path) -> SimpleNamespace:
    """Minimale App-Attrappe mit echtem Service auf synthetischem Vault (heute = 2026-01-15)."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-15.md").write_bytes(b"Heute #h\n- [ ] Aufgabe\n  - Detail\n")
    (root / "2026-01-15.sync-conflict-20260115-120000-AAAAAAA.sync-conflict-20260116-120000-BBBBBBB.md").write_bytes(
        b"Heute #h\n- [ ] anders\n")
    settings = Settings(vault=str(root))
    service = NotesService(root, tmp_path / "app", settings, FakeClock())
    service.start()
    return SimpleNamespace(service=service, settings=settings, access=FakeAccess(), say=lambda _m: None,
                           render=lambda: None, show_setup=lambda: None)


@pytest.mark.parametrize("builder", [tabs.today_view, tabs.todos_view, tabs.search_view, tabs.conflicts_view,
                                     tabs.settings_view, tabs.setup_view])
def test_every_tab_builds_controls(tmp_path: Path, builder) -> None:
    """Alle Tabs liefern eine nicht leere Control-Liste."""
    controls = builder(app(tmp_path))
    assert controls and all(isinstance(c, ft.Control) for c in controls)


def test_today_shows_todo_as_checkbox(tmp_path: Path) -> None:
    """Heute: das Todo erscheint als Checkbox mit Anzeigetext ohne Marker."""
    controls = tabs.today_view(app(tmp_path))
    texts = []

    def walk(control):
        if isinstance(control, ft.Checkbox):
            texts.append(control.label)
        for child in getattr(control, "controls", None) or []:
            walk(child)
        content = getattr(control, "content", None)
        if isinstance(content, ft.Control):
            walk(content)

    for control in controls:
        walk(control)
    assert texts == ["Aufgabe"]


def test_start_hint_reports_limited_write_guarantee() -> None:
    report = SimpleNamespace(recovery=SimpleNamespace(not_applied=[]), moves=[], automerges=[])
    assert tabs.start_hint(report, "voll") == ""
    assert "eingeschränkt" in tabs.start_hint(report, "eingeschränkt (A1–A3)")


def test_start_hint_reports_automerge() -> None:
    """Start-Hinweis nennt automatisch zusammengeführte Konflikte."""
    report = SimpleNamespace(recovery=SimpleNamespace(not_applied=[]), moves=[], automerges=["x"])
    assert "automatisch zusammengeführt" in tabs.start_hint(report)
