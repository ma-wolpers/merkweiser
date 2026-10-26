"""W7 Phase 3: ``NotesService.move_note`` und der gemeinsame Verschieben-Dialog."""

import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from merkweiser.app.notes_service import NotesService, SameDayMoveError
from merkweiser.app.settings import Settings
from merkweiser.app.views import note_ref
from merkweiser.core.note_ops import NoteNotFoundError
from tests.fakes import FakeClock


def service(tmp_path: Path, text: str) -> NotesService:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-15.md").write_text(text, encoding="utf-8")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    return svc


def ref_of(svc: NotesService, index: int = 0):
    [day] = svc.day(date(2026, 1, 15))
    return note_ref(day.relpath, day.document, day.document.notes[index])


def test_move_note_to_tomorrow_and_same_day_is_refused(tmp_path: Path) -> None:
    svc = service(tmp_path, "Elternabend #schule\n- [ ] Brief\n\nAnderes\n- [ ] bleibt\n")
    with pytest.raises(SameDayMoveError, match="Die Notiz steht schon am 15.01.2026"):
        svc.move_note(ref_of(svc), date(2026, 1, 15))
    result = svc.move_note(ref_of(svc), date(2026, 1, 16))
    svc.clock.advance(121)
    svc.writer.finish_due()
    assert result.state == "DONE"
    assert (svc.root / "2026-01-16.md").read_text(encoding="utf-8") == "Elternabend #schule\n- [ ] Brief\n"
    assert "Brief" not in (svc.root / "2026-01-15.md").read_text(encoding="utf-8")


def test_changed_note_gives_a_clear_message_and_writes_nothing(tmp_path: Path) -> None:
    svc = service(tmp_path, "Elternabend\n- [ ] Brief\n")
    ref = ref_of(svc)
    (svc.root / "2026-01-15.md").write_text("Elternabend\n- [ ] Brief!\n", encoding="utf-8")
    with pytest.raises(NoteNotFoundError, match="inzwischen geändert"):
        svc.move_note(ref, date(2026, 1, 16))
    assert not (svc.root / "2026-01-16.md").exists()


def test_note_dialog_moves_and_calls_after(tmp_path: Path) -> None:
    pytest.importorskip("flet")
    from merkweiser.mobile.ui import move_dialog
    from tests.mobile.test_mobile_tabs import FakePage
    svc = service(tmp_path, "Elternabend\n- [ ] Brief\n")
    said, closed = [], []

    async def act(action):
        return action(svc)

    app = SimpleNamespace(service=svc, page=FakePage(), act=act, say=lambda m, link=False: said.append(m))
    move_dialog.show_note_move_dialog(app, ref_of(svc), after=lambda: closed.append(True))
    [dialog] = app.page.dialogs
    assert dialog.title == "Notiz verschieben auf …"
    asyncio.run(dialog.content.controls[0].on_click(None))  # „Morgen“
    assert closed == [True] and (svc.root / "2026-01-16.md").exists() and not said
