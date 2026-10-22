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
                           render=lambda: None, show_setup=lambda: None, day=service.clock.today())


@pytest.mark.parametrize("builder", [tabs.day_view, tabs.todos_view, tabs.search_view, conflict_view.conflicts_view,
                                     tabs.settings_view, tabs.setup_view])
def test_every_tab_builds_controls(tmp_path: Path, builder) -> None:
    """Alle Tabs liefern eine nicht leere Control-Liste."""
    controls = builder(app(tmp_path))
    assert controls and all(isinstance(c, ft.Control) for c in controls)


def test_today_shows_todo_as_checkbox(tmp_path: Path) -> None:
    """Heute: das Todo hat eine Checkbox, sein Text steht ohne Marker daneben; der Punkt hat ein „•“."""
    controls = tabs.day_view(app(tmp_path))
    found = []

    def walk(control):
        found.append(control)
        for child in getattr(control, "controls", None) or []:
            walk(child)
        content = getattr(control, "content", None)
        if isinstance(content, ft.Control):
            walk(content)

    for control in controls:
        walk(control)
    assert len([c for c in found if isinstance(c, ft.Checkbox)]) == 1
    texts = [c.value for c in found if isinstance(c, ft.Text)]
    assert "Aufgabe" in texts and "•" in texts and "Detail" in texts


def test_note_layout_topic_explanation_continuation() -> None:
    """Thema fett (nicht unterstrichen), Erläuterung deutlich schwächer darunter, Fortsetzung bündig."""
    from merkweiser.app.views import Row
    from merkweiser.mobile.ui.note_view import MARKER_WIDTH, note_row
    topic = note_row(SimpleNamespace(), Row("topic", "Elternabend", 0, None, False, (), None, ("Vorher klären",)))
    head, explanation = topic.content.controls
    from merkweiser.mobile.ui.style import EXPLANATION
    assert head.weight == ft.FontWeight.BOLD and head.style is None
    assert explanation.value == "Vorher klären" and explanation.color == EXPLANATION
    item = note_row(SimpleNamespace(), Row("item", "Liste", 1, None, False, (), None, ("weiter",)))
    first, continuation = item.content.controls
    assert first.controls[0].width == MARKER_WIDTH and first.controls[0].content.value == "•"
    assert continuation.padding.left == MARKER_WIDTH and continuation.content.value == "weiter"


def test_start_hint_reports_limited_write_guarantee() -> None:
    report = SimpleNamespace(recovery=SimpleNamespace(not_applied=[]), moves=[], automerges=[], removed_empty=[])
    assert tabs.start_hint(report, "voll") == ""
    assert "eingeschränkt" in tabs.start_hint(report, "eingeschränkt (A1–A3)")


def test_start_hint_reports_automerge() -> None:
    """Start-Hinweis nennt automatisch zusammengeführte Konflikte und entfernte leere Dateien."""
    report = SimpleNamespace(recovery=SimpleNamespace(not_applied=[]), moves=[], automerges=["x"],
                             removed_empty=["2026-01-01.md"])
    assert "automatisch zusammengeführt" in tabs.start_hint(report)
    assert "1 leere Datumsdatei(en) entfernt." in tabs.start_hint(report)


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
    dialog.content.controls[1].value = "Heute #h\n- [ ] Neu formuliert"  # [0] ist die Einfüge-Leiste
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
    dialog.content.controls[1].value = "  \n"
    dialog.content.controls[2].update = lambda: None  # ohne Seite kein Update möglich
    asyncio.run(dialog.actions[1].on_click(None))
    assert fake.page.dialogs == [dialog] and "Löschen" in dialog.content.controls[2].value
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

    from merkweiser.mobile.ui.date_pick import picked_date
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


def _flow(tmp_path: Path, text: bytes, line_no: int):
    """Hilfsfunktion: Datei mit mehreren Todos anlegen und den Verschieben-Ablauf starten."""
    import asyncio

    from merkweiser.core.patch import Target
    from merkweiser.mobile.ui import tag_dialog
    fake = _dialog_app(tmp_path)
    (Path(fake.settings.vault) / "2026-01-14.md").write_bytes(text)
    fake.service.rescan()
    target = Target("2026-01-14.md", line_no, text.decode().splitlines()[line_no])
    asyncio.run(tag_dialog.show_move_flow(fake, target))
    return fake, target


def test_move_flow_skips_tag_dialog_for_a_sole_todo(tmp_path: Path) -> None:
    """Alleiniges Todo → direkt die Datumswahl (ganze Notiz wandert)."""
    fake, _target = _flow(tmp_path, b"T\n- [ ] allein\n", 1)
    [dialog] = fake.page.dialogs
    assert dialog.title == "Todo verschieben auf …"


def test_move_flow_shows_tag_dialog_and_passes_the_tag_on(tmp_path: Path) -> None:
    """Weitere Todos → Tag-Dialog; er schreibt nichts, „Mit Tag verschieben“ öffnet die Datumswahl mit Tag."""
    import asyncio

    fake, _target = _flow(tmp_path, b"T\n- [ ] eins\n- [ ] zwei\n", 1)
    [dialog] = fake.page.dialogs
    cancel, plain, with_tag = dialog.actions
    assert dialog.title == "Todo herauslösen?" and plain.content == "Einfach so verschieben" and with_tag.disabled
    field = dialog.content.controls[1]
    field.value = "#neu"
    asyncio.run(with_tag.on_click(None))
    [move] = fake.page.dialogs
    assert move.title == "Todo verschieben auf …"
    assert (Path(fake.settings.vault) / "2026-01-14.md").read_bytes() == b"T\n- [ ] eins\n- [ ] zwei\n"
    asyncio.run(move.content.controls[1].on_click(None))  # „Übermorgen“ (heute = 15.01.)
    assert (Path(fake.settings.vault) / "2026-01-17.md").read_bytes() == b"T #neu\n- [ ] eins #neu\n"


def test_tag_dialog_offers_the_shared_project(tmp_path: Path) -> None:
    """Gemeinsames Projekt von Todo und Überpunkt → „Mit bestehendem Tag verschieben“."""
    fake, _target = _flow(tmp_path, b"T #projekt/umzug\n- [ ] eins\n- [ ] zwei\n", 1)
    [dialog] = fake.page.dialogs
    assert dialog.actions[1].content == "Mit bestehendem Tag verschieben (#projekt/umzug)"


def test_editors_are_bounded_and_the_edit_dialog_scrolls(tmp_path: Path) -> None:
    """Editor ohne Titel, höchstens 9 Zeilen, Dialog scrollbar (Knöpfe bleiben mit Tastatur erreichbar)."""
    from merkweiser.app.views import note_ref
    from merkweiser.mobile.ui import note_dialogs
    fake = _dialog_app(tmp_path)
    [day] = fake.service.day(fake.service.clock.today())
    dialog = note_dialogs._edit_dialog(fake, note_ref(day.relpath, day.document, day.document.notes[0]))
    field = dialog.content.controls[1]
    assert dialog.scrollable and dialog.title is None and (field.min_lines, field.max_lines) == (3, 9)


def test_new_note_button_opens_the_shared_editor_empty(tmp_path: Path) -> None:
    """Tab „Tag“ hat kein eigenes Schreibfeld mehr; „Neue Notiz“ öffnet denselben Editor leer."""
    import asyncio
    fake = _dialog_app(tmp_path)
    controls = tabs.day_view(fake)
    assert not any(isinstance(c, ft.TextField) for c in _walk_all(controls))
    asyncio.run(controls[1].on_click(None))
    [dialog] = fake.page.dialogs
    assert dialog.title is None and dialog.content.controls[1].value == ""


def _toolbar(text: str):
    """Hilfsfunktion: Feld mit Leiste, ohne Seite (``update``/``focus`` als Attrappen)."""
    from merkweiser.mobile.ui.note_editor import editor_toolbar
    field = ft.TextField(value=text, multiline=True)
    bar = editor_toolbar(field)
    field.update = lambda: None

    async def focus() -> None:
        return None

    field.focus = focus
    return field, bar


def test_toolbar_uses_the_remembered_utf16_selection(tmp_path: Path) -> None:
    """Checkbox-Knopf: gemerkte Auswahl (UTF-16, Emoji vor dem Caret) → Todo, Caret danach passend gesetzt."""
    import asyncio
    field, bar = _toolbar("😀 x")
    asyncio.run(field.on_selection_change(SimpleNamespace(selection=ft.TextSelection(4, 4), selected_text="")))
    asyncio.run(bar.controls[0].on_click(None))
    assert field.value == "- [ ] 😀 x"
    assert (field.selection.start, field.selection.end) == (10, 10)  # Index 9 → 10 UTF-16-Einheiten


def test_toolbar_does_nothing_without_known_position(tmp_path: Path) -> None:
    """Ohne gemerkte Position verändert kein Knopf den Text."""
    import asyncio
    field, bar = _toolbar("a\nb")
    for button in bar.controls:
        asyncio.run(button.on_click(None))
    assert field.value == "a\nb" and field.selection is None


def test_day_view_navigates_and_saves_for_the_chosen_day(tmp_path: Path) -> None:
    """◀ wechselt den Tag, „Heute“ erscheint nur an anderen Tagen, Speichern legt die Datei dieses Tages an."""
    import asyncio
    from datetime import date
    fake = _dialog_app(tmp_path)
    header = tabs.day_view(fake)[0]
    assert [c.content for c in header.controls if isinstance(c, ft.TextButton)] == ["Heute · Do, 15.01.2026"]
    asyncio.run(header.controls[0].on_click(None))
    assert fake.day == date(2026, 1, 14)
    controls = tabs.day_view(fake)
    assert "Heute" in [c.content for c in controls[0].controls if isinstance(c, ft.TextButton)]
    assert "Noch keine Notizen am 14.01.2026." in _texts(controls)
    assert not (Path(fake.settings.vault) / "2026-01-14.md").exists()
    asyncio.run(controls[1].on_click(None))  # „Neue Notiz“
    [editor] = fake.page.dialogs
    editor.content.controls[1].value = "Neu"
    asyncio.run(editor.actions[1].on_click(None))
    assert (Path(fake.settings.vault) / "2026-01-14.md").read_bytes() == b"Neu\n"


def test_opening_the_vault_always_selects_today(tmp_path: Path) -> None:
    """``open_vault`` setzt den gewählten Tag auf heute (laut Service-Uhr), auch wenn vorher ein anderer gewählt war."""
    import asyncio
    from datetime import date

    from merkweiser.mobile.ui.app import MobileApp
    root = tmp_path / "vault"
    root.mkdir()
    page = SimpleNamespace(update=lambda: None)
    mobile = MobileApp(page, SimpleNamespace(data_dir=tmp_path / "app"), FakeAccess())
    mobile.settings = Settings(vault=str(root))
    mobile.day = date(2000, 1, 1)
    asyncio.run(mobile.open_vault())
    assert mobile.day == mobile.service.clock.today() == date.today()
    mobile.show_day(date(2026, 1, 3))
    assert (mobile.day, mobile.tab, mobile.nav.selected_index) == (date(2026, 1, 3), 0, 0)


def _search(fake, text: str) -> list:
    """Hilfsfunktion: Suche mit gesetztem Suchtext rendern."""
    fake._search = {"text": text, "regex": False}
    return tabs.search_view(fake)


def test_search_shows_whole_note_cards_and_jumps_to_the_day(tmp_path: Path) -> None:
    """Treffer → ganze Notiz mit Aktionsleiste; der Datumsknopf öffnet den Tab „Tag“ mit diesem Datum."""
    import asyncio
    from datetime import date
    fake = _dialog_app(tmp_path)
    shown = []
    fake.show_day = shown.append
    controls = _search(fake, "detail")
    [card] = [c for c in controls if isinstance(c, ft.Container)]
    texts = _texts([card])
    assert "Heute #h" in texts and "Aufgabe" in texts and "Detail" in texts  # ganze Notiz, nicht nur der Treffer
    head = card.content.controls[0]
    assert head.content == "Heute · Do, 15.01.2026"
    asyncio.run(head.on_click(None))
    assert shown == [date(2026, 1, 15)]


def test_search_refreshes_after_actions(tmp_path: Path) -> None:
    """Nach einer Änderung wird neu gesucht: Abhaken trifft die richtige Zeile; nicht mehr passende Karten verschwinden."""
    import asyncio
    fake = _dialog_app(tmp_path)
    vault = Path(fake.settings.vault)
    (vault / "2026-01-15.md").write_bytes(b"Neu oben\n\nHeute #h\n- [ ] Aufgabe\n  - Detail\n")
    fake.service.rescan()
    [card] = [c for c in _search(fake, "aufgabe") if isinstance(c, ft.Container)]
    checkbox = next(c for c in _walk(card) if isinstance(c, ft.Checkbox))
    asyncio.run(checkbox.on_change(SimpleNamespace(control=SimpleNamespace(value=True))))
    assert b"- [x] Aufgabe" in (vault / "2026-01-15.md").read_bytes()
    (vault / "2026-01-15.md").write_bytes(b"Heute #h\n- [x] Erledigt\n")
    fake.service.cache.forget("2026-01-15.md")
    assert "Nichts gefunden." in _texts(_search(fake, "aufgabe"))


def _walk(control) -> list:
    """Alle Controls rekursiv (über content/controls)."""
    found = [control]
    for child in getattr(control, "controls", None) or []:
        found += _walk(child)
    if isinstance(getattr(control, "content", None), ft.Control):
        found += _walk(control.content)
    return found


def _walk_all(controls) -> list:
    """Alle Controls einer Liste rekursiv."""
    return [found for control in controls for found in _walk(control)]


def test_enter_in_a_todo_continues_the_list(tmp_path: Path) -> None:
    """Enter (on_change mit genau einem ``\n`` mehr) in einem Todo → neues leeres Todo, Caret dahinter."""
    import asyncio
    field, _bar = _toolbar("- [ ] a")
    asyncio.run(field.on_selection_change(SimpleNamespace(selection=ft.TextSelection(7, 7), selected_text="")))
    field.value = "- [ ] a\n"
    asyncio.run(field.on_change(None))
    assert field.value == "- [ ] a\n- [ ] "
    assert (field.selection.start, field.selection.end) == (14, 14)
    field.value = "- [ ] a\n- [ ] \n"  # Enter im leeren Todo → wird Text
    asyncio.run(field.on_change(None))
    assert field.value == "- [ ] a\n"


def test_list_button_and_indent_width(tmp_path: Path) -> None:
    """Listen-Knopf macht aus dem Todo einen Punkt; Einrücken nutzt die eingestellte Breite."""
    import asyncio

    from merkweiser.mobile.ui.note_editor import editor_toolbar
    field = ft.TextField(value="- a\n- [ ] b", multiline=True)
    bar = editor_toolbar(field, 2)
    field.update = lambda: None

    async def focus() -> None:
        return None

    field.focus = focus
    asyncio.run(field.on_selection_change(SimpleNamespace(selection=ft.TextSelection(11, 11), selected_text="")))
    asyncio.run(bar.controls[1].on_click(None))
    assert field.value == "- a\n- b"
    asyncio.run(bar.controls[2].on_click(None))
    assert field.value == "- a\n  - b"
