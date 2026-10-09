"""Integrationstests für NotesService und Settings (synthetischer Vault)."""

from datetime import date
from pathlib import Path

import pytest

from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings, load_settings, save_settings
from merkweiser.core.patch import Target
from merkweiser.core.query import Filter, StatusFilter, TextQuery
from tests.fakes import FakeClock


def service(tmp_path: Path) -> NotesService:
    """Hilfsfunktion: Service auf leerem synthetischem Vault (heute = 2026-01-15)."""
    root = tmp_path / "vault"
    root.mkdir(exist_ok=True)
    return NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())


def settle(svc: NotesService) -> None:
    """Quarantänen ablaufen lassen."""
    svc.clock.advance(121)
    svc.poll()


def test_start_auto_merges_syncthing_conflict(tmp_path: Path) -> None:
    """Start: Wiederherstellung, Scan, dann Auto-Merge des Konzeptbeispiels."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-01.md").write_bytes(b"Notiz\n- [ ] A\n- [ ] B\n")
    (root / "2026-01-01.sync-conflict-20260101-120000-ABCDEFG.md").write_bytes(b"Notiz\n- [ ] A\n- [ ] C\n")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    report = svc.start()
    settle(svc)
    assert len(report.automerges) == 1
    assert (root / "2026-01-01.md").read_bytes() == b"Notiz\n- [ ] A\n- [ ] B\n- [ ] C\n"
    assert svc.conflicts() == []


def test_append_note_creates_today_and_then_appends(tmp_path: Path) -> None:
    """Neue Notiz: Tagesdatei wird angelegt; zweite Notiz mit Trenner angehängt."""
    svc = service(tmp_path)
    svc.start()
    svc.append_note("Erste\n- [ ] a")
    settle(svc)
    svc.append_note("Zweite")
    settle(svc)
    assert (svc.root / "2026-01-15.md").read_bytes() == b"Erste\n- [ ] a\n\n---\n\nZweite\n"
    assert [f.relpath for f in svc.day(date(2026, 1, 15))] == ["2026-01-15.md"]


def test_search_and_set_done_roundtrip(tmp_path: Path) -> None:
    """Todo per Suche finden, erledigen, danach im Filter „erledigt“ wiederfinden."""
    svc = service(tmp_path)
    (svc.root / "2026-01-02.md").write_bytes(b"Uni #uni\n- [ ] Lernen\n")
    svc.start()
    [hit] = svc.search(Filter(text=TextQuery("lernen"), nur_todos=True))
    svc.set_done(Target(hit.relpath, hit.line_no, hit.text), True)
    settle(svc)
    done = svc.search(Filter(status=StatusFilter.ERLEDIGT))
    assert [h.text for h in done] == ["- [x] Lernen"] and done[0].tags == ("uni",)


def test_replace_note_text_external_change_elsewhere_is_applied(tmp_path: Path) -> None:
    """Externe Änderung an einer anderen Notiz: Rohtext-Ersatz wird trotzdem angewendet."""
    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    planned = b"A\n- x\n\n---\n\nB\n- y\n"
    path.write_bytes(planned)
    svc.start()
    path.write_bytes(b"A\n- x\n- extern\n\n---\n\nB\n- y\n")
    svc.replace_note_text("2026-01-02.md", planned, ("B", "- y"), "B neu")
    settle(svc)
    assert path.read_bytes() == b"A\n- x\n- extern\n\n---\n\nB neu\n"


def test_replace_note_text_changed_note_becomes_own_conflict(tmp_path: Path) -> None:
    """Notiz extern geändert: getippter Text geht nicht verloren → eigene Konfliktdatei mit Basis."""
    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    planned = b"A\n- x\n\n---\n\nB\n- y\n"
    path.write_bytes(planned)
    svc.start()
    path.write_bytes(b"A\n- x\n\n---\n\nB\n- y extern\n")
    result = svc.replace_note_text("2026-01-02.md", planned, ("B", "- y"), "B mein Text")
    assert result.state == "CONFLICTED"
    conflict = svc.root / result.conflicts[0]
    assert b"B mein Text" in conflict.read_bytes() and conflict.name.startswith("2026-01-02.sync-conflict-")
    assert path.read_bytes() == b"A\n- x\n\n---\n\nB\n- y extern\n"
    assert len(svc.conflicts()) == 1


def test_move_todo_via_service(tmp_path: Path) -> None:
    """Verschieben über die Fassade nutzt die Schreibziel-Regel."""
    svc = service(tmp_path)
    (svc.root / "2026-01-02.md").write_bytes(b"T #t\n- [ ] weg\n- [ ] bleibt\n")
    svc.start()
    result = svc.move_todo(Target("2026-01-02.md", 1, "- [ ] weg"), date(2026, 1, 20))
    settle(svc)
    assert result.state == "DONE"
    assert (svc.root / "2026-01-20.md").read_text(encoding="utf-8") == "Verschoben aus [[2026-01-02]]\n- [ ] weg #t\n"


def test_settings_roundtrip_and_validation(tmp_path: Path) -> None:
    """Einstellungen liegen in den App-Daten; ungültige Werte werden abgelehnt."""
    save_settings(tmp_path, Settings(vault="X", project_prefix="p", retention_days=7))
    assert load_settings(tmp_path) == Settings(vault="X", project_prefix="p", retention_days=7)
    assert load_settings(tmp_path / "leer") == Settings()
    with pytest.raises(ValueError):
        Settings(pattern="%Y.md").validated()
    with pytest.raises(ValueError):
        Settings(project_prefix="mit leer").validated()
