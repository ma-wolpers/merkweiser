"""Diagnosebericht: Inhalt (nur Metadaten, nie Notizinhalte) und exklusives Anlegen."""

from datetime import datetime
from pathlib import Path

from merkweiser.app.diagnostics import build_report, write_report
from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings
from tests.fakes import FakeClock

NOW = datetime(2026, 10, 21, 14, 30, 5)
SECRET = b"Geheimer Notiztext"


def opened(tmp_path: Path):
    """Synthetischer Vault mit einer Tagesdatei und einer Syncthing-Konfliktdatei."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-15.md").write_bytes(SECRET + b"\n- [ ] Aufgabe\n")
    (root / "2026-01-15.sync-conflict-20260115-120000-AAAAAAA.sync-conflict-20260116-120000-BBBBBBB.md").write_bytes(
        SECRET + b"\n- [ ] anders\n")
    settings = Settings(vault=str(root))
    service = NotesService(root, tmp_path / "app", settings, FakeClock())
    return settings, service, service.start()


def test_report_lists_state_but_no_note_content(tmp_path: Path) -> None:
    settings, service, report = opened(tmp_path)
    text = build_report(settings, service, report, [(NOW, "Fehler X")], NOW, {"flet": "0.86.5"})
    assert "install_mode=atomic" in text and "schreibgarantie=voll" in text
    assert "tagesdateien=1" in text and "konfliktdateien=1" in text
    assert "sync-conflict-20260115-120000-AAAAAAA" in text
    assert "unvollstaendige_vorgaenge=0" in text
    assert "14:30:05 Fehler X" in text and "flet=0.86.5" in text
    assert SECRET.decode() not in text and "Aufgabe" not in text


def test_report_without_open_vault_explains_why(tmp_path: Path) -> None:
    text = build_report(Settings(vault=str(tmp_path / "fehlt")), None, None, [], NOW)
    assert "nicht geöffnet (existiert=False" in text
    assert "(kein Start)" in text and "(keine)" in text
    assert "status=nicht eingestellt" in build_report(Settings(), None, None, [], NOW)


def test_write_report_never_overwrites(tmp_path: Path) -> None:
    first = write_report(tmp_path, "eins\n", NOW)
    second = write_report(tmp_path, "zwei\n", NOW)
    assert first.name == "merkweiser-diagnose-20261021-143005.txt"
    assert second.name == "merkweiser-diagnose-20261021-143005-1.txt"
    assert first.read_text(encoding="utf-8") == "eins\n" and second.read_text(encoding="utf-8") == "zwei\n"
