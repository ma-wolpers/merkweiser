"""Rauchtest der Mobile-Ansichten: jeder Tab baut seine Controls ohne Gerät und Fenster.

Wird übersprungen, wenn Flet nicht installiert ist (Extra ``ui``).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.notes_service import NotesService  # noqa: E402
from merkweiser.app.settings import Settings  # noqa: E402
from merkweiser.mobile.ui import conflict_view, tabs  # noqa: E402
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


@pytest.mark.parametrize("builder", [tabs.today_view, tabs.todos_view, tabs.search_view, conflict_view.conflicts_view,
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


class FakePage:
    """Seite ohne Fenster: merkt sich geöffnete Dialoge."""

    def __init__(self) -> None:
        self.dialogs = []

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None


def _dialog_app(tmp_path: Path):
    """App-Attrappe, deren ``act`` die Aktion direkt am echten Service ausführt."""
    base = app(tmp_path)
    base.page = FakePage()

    async def act(action):
        return action(base.service)

    base.act = act
    return base


def test_edit_dialog_replaces_note_text(tmp_path: Path) -> None:
    """„Speichern“ im Bearbeiten-Dialog ersetzt den Notiztext in der Datei."""
    import asyncio

    from merkweiser.app.views import note_ref
    from merkweiser.mobile.ui import note_dialogs
    fake = _dialog_app(tmp_path)
    [day] = fake.service.day(fake.service.clock.today())
    ref = note_ref(day.relpath, day.document, day.document.notes[0])
    dialog = note_dialogs._edit_dialog(fake, ref)
    dialog.content.controls[0].value = "Heute #h\n- [ ] Neu formuliert"
    asyncio.run(dialog.actions[1].on_click(None))
    assert (Path(fake.settings.vault) / day.relpath).read_bytes() == b"Heute #h\n- [ ] Neu formuliert\n"


def test_edit_dialog_rejects_empty_text(tmp_path: Path) -> None:
    """Leerer Text: Dialog bleibt offen, Hinweis auf „Löschen“, Datei unverändert."""
    import asyncio

    from merkweiser.app.views import note_ref
    from merkweiser.mobile.ui import note_dialogs
    fake = _dialog_app(tmp_path)
    [day] = fake.service.day(fake.service.clock.today())
    ref = note_ref(day.relpath, day.document, day.document.notes[0])
    dialog = note_dialogs._edit_dialog(fake, ref)
    fake.page.show_dialog(dialog)
    dialog.content.controls[0].value = "  \n"
    dialog.content.controls[1].update = lambda: None  # ohne Seite kein Update möglich
    asyncio.run(dialog.actions[1].on_click(None))
    assert fake.page.dialogs == [dialog] and "Löschen" in dialog.content.controls[1].value
    assert (Path(fake.settings.vault) / day.relpath).read_bytes() == ref.planned_raw


def test_delete_dialog_removes_note(tmp_path: Path) -> None:
    """„Löschen“ nach Rückfrage entfernt die Notiz."""
    import asyncio

    from merkweiser.app.views import note_ref
    from merkweiser.mobile.ui import note_dialogs
    fake = _dialog_app(tmp_path)
    [day] = fake.service.day(fake.service.clock.today())
    ref = note_ref(day.relpath, day.document, day.document.notes[0])
    asyncio.run(note_dialogs._delete_dialog(fake, ref).actions[1].on_click(None))
    assert (Path(fake.settings.vault) / day.relpath).read_bytes() == b""


def test_picked_date_handles_naive_aware_and_missing_values() -> None:
    """DatePicker-Werte: naiv → Datum direkt; UTC-behaftet → erst in lokale Zeit; None → None."""
    from datetime import date, datetime, timezone

    from merkweiser.mobile.ui.move_dialog import picked_date
    assert picked_date(datetime(2026, 10, 23)) == date(2026, 10, 23)
    aware = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    assert picked_date(aware) == aware.astimezone().date()
    assert picked_date(date(2026, 10, 23)) == date(2026, 10, 23) and picked_date(None) is None


def test_move_dialog_quick_choice_moves_todo(tmp_path: Path) -> None:
    """„Morgen“ im Verschieben-Dialog verschiebt das Todo in die Tagesdatei von morgen."""
    import asyncio

    from merkweiser.app.views import note_rows
    from merkweiser.mobile.ui import move_dialog
    fake = _dialog_app(tmp_path)
    [day] = fake.service.day(fake.service.clock.today())
    rows = [r for n in day.document.notes for r in note_rows(day.relpath, day.document, n)]
    todo = next(r for r in rows if r.kind == "todo")
    dialog = move_dialog.move_dialog(fake, todo.target)
    assert [c.content for c in dialog.content.controls][:1] == ["Morgen (Fr, 16.01.)"]
    asyncio.run(dialog.content.controls[0].on_click(None))
    vault = Path(fake.settings.vault)
    assert b"Aufgabe" in (vault / "2026-01-16.md").read_bytes()
    assert b"Aufgabe" not in (vault / "2026-01-15.md").read_bytes()


def _texts(controls) -> list[str]:
    """Alle Text-Inhalte einer Control-Liste (rekursiv über content/controls)."""
    found = []
    for control in controls:
        if isinstance(control, ft.Text):
            found.append(control.value)
        for child in getattr(control, "controls", None) or []:
            found += _texts([child])
        if isinstance(getattr(control, "content", None), ft.Control):
            found += _texts([control.content])
    return found


def test_automerge_section_offers_undo_and_then_shows_open_case(tmp_path: Path) -> None:
    """Start führt einen Syncthing-Konflikt zusammen; „Rückgängig“ macht daraus einen offenen Fall."""
    import asyncio

    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-15.md").write_bytes(b"Notiz\n- [ ] A\n")
    (root / "2026-01-15.sync-conflict-20260115-120000-ABCDEFG.md").write_bytes(b"Notiz\n- [ ] A\n- [ ] B\n")
    service = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    assert service.start().automerges
    fake = SimpleNamespace(service=service, page=FakePage(), say=lambda _m: None, render=lambda: None)

    async def act(action):
        return action(service)

    fake.act = act
    controls = conflict_view.conflicts_view(fake)
    assert "Automatisch zusammengeführt" in _texts(controls)
    undo = next(c for c in controls if isinstance(c, ft.Row) and any(
        isinstance(b, ft.Button) and b.content == "Rückgängig" for b in c.controls))
    asyncio.run(undo.controls[0].on_click(None))
    texts = _texts(conflict_view.conflicts_view(fake))
    assert "Rückgängig gemacht – die Konfliktversion steht wieder oben." in texts
    assert [c.kind.value for c in service.conflicts()] == ["manual"]


def test_hunk_controls_apply_one_choice_per_hunk() -> None:
    """Abschnitt 1 „Beide“, Abschnitt 2 „Bearbeitet“ → resolve bekommt das zusammengesetzte Ergebnis."""
    import asyncio

    from merkweiser.core.merge.diff3 import merge3
    from merkweiser.mobile.ui.hunk_view import hunk_controls
    merge = merge3(["T", "a", "m1", "m2", "m3", "z", "E"], ["T", "a A", "m1", "m2", "m3", "z A", "E"],
                   ["T", "a B", "m1", "m2", "m3", "E"])
    case = SimpleNamespace(merge=merge, main_bytes=b"T\na A\nm1\nm2\nm3\nz A\nE\n")
    calls = []
    service = SimpleNamespace(resolve=lambda c, result, decision: calls.append((result, decision)))

    async def act(action):
        return action(service)

    controls = hunk_controls(SimpleNamespace(act=act), case)
    groups = [c for c in controls if isinstance(c, ft.RadioGroup)]
    fields = [c for c in controls if isinstance(c, ft.TextField)]
    assert [len(g.content.controls) for g in groups] == [4, 3]  # „Beide“ fehlt bei Änderung gegen Löschung
    for field in fields:
        field.update = lambda: None  # ohne Seite kein Update möglich
    groups[0].on_change(SimpleNamespace(control=SimpleNamespace(value="beide")))
    groups[1].on_change(SimpleNamespace(control=SimpleNamespace(value="bearbeitet")))
    assert fields[1].visible
    fields[1].on_change(SimpleNamespace(control=SimpleNamespace(value="z neu")))
    button = next(c for c in controls if isinstance(c, ft.Button))
    asyncio.run(button.on_click(None))
    assert calls == [(b"T\na A\na B\nm1\nm2\nm3\nz neu\nE\n", "Abschnitt 1: Beide, 2: Bearbeitet")]
