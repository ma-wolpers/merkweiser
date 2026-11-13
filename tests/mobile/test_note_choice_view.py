"""Mobile: notizweise Konfliktauswahl (W8) – ohne Fenster, mit echtem Service auf synthetischem Vault."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.notes_service import NotesService  # noqa: E402
from merkweiser.app.settings import Settings  # noqa: E402
from merkweiser.mobile.ui import conflict_view  # noqa: E402
from tests.fakes import FakeClock  # noqa: E402
from tests.mobile.test_frontmatter_choices import walk  # noqa: E402
from tests.mobile.test_mobile_tabs import FakePage  # noqa: E402

MAIN = "2026-01-15.md"
NESTED = "2026-01-15.sync-conflict-20260115-120000-AAAAAAA.sync-conflict-20260116-120000-BBBBBBB.md"
CONF = "2026-01-15.sync-conflict-20260115-120000-AAAAAAA.md"


def setup(tmp_path: Path, files: dict[str, bytes], after_start: dict[str, bytes] | None = None):
    """Vault anlegen, Service starten, App-Attrappe mit direktem ``act``."""
    root = tmp_path / "vault"
    root.mkdir()
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    service = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    service.start()
    for name, raw in (after_start or {}).items():
        (root / name).write_bytes(raw)
    service.rescan()
    said: list[str] = []

    async def act(action):
        try:
            return action(service)
        except Exception as exc:  # wie MobileApp.act
            said.append(str(exc))

    app = SimpleNamespace(service=service, act=act, say=said.append, render=lambda: None, page=FakePage())
    return root, service, app, said


def view(app) -> list:
    """Alle Controls der Konfliktseite (nach jeder Wahl neu gebaut, wie ``app.render``)."""
    return list(walk(conflict_view.conflicts_view(app)))


def texts(controls) -> str:
    """Alle Textwerte, durch Zeilenumbrüche getrennt."""
    return "\n".join(c.value for c in controls if isinstance(c, ft.Text) and isinstance(c.value, str))


def button(controls, label: str, kind=ft.Button):
    return next(c for c in controls if isinstance(c, kind) and c.content == label)


def choose(group, value: str) -> None:
    group.on_change(SimpleNamespace(control=SimpleNamespace(value=value)))


def test_todo_and_note_choices_then_apply(tmp_path: Path) -> None:
    """Todo ohne Vorauswahl, geänderte Notiz „Beide“ → erst dann aktiv; Ergebnis landet in der Hauptdatei."""
    root, service, app, said = setup(tmp_path, {MAIN: b"Einkauf\n- [ ] Milch\n\nArbeit\n- alt\n",
                                                NESTED: b"Einkauf\n- [x] Milch\n\nArbeit\n- neu\n"})
    controls = view(app)
    assert button(controls, "Auswahl übernehmen").disabled
    assert "Todo „- [ ] Milch“ – Hauptdatei: offen · Konfliktversion: erledigt" in texts(controls)
    todo = next(c for c in controls if isinstance(c, ft.RadioGroup) and c.content.controls[0].value == "erledigt")
    assert todo.value is None  # keine Vorauswahl
    choose(todo, "erledigt")
    note = next(c for c in view(app) if isinstance(c, ft.RadioGroup) and c.content.controls[0].value == "haupt")
    choose(note, "beide")
    controls = view(app)
    assert "Alles entschieden." in texts(controls)
    asyncio.run(button(controls, "Auswahl übernehmen").on_click(None))
    assert not said and service.conflicts() == []
    assert (root / MAIN).read_bytes() == b"Einkauf\n- [x] Milch\n\nArbeit\n- alt\n- neu\n"


def test_quick_select_only_sets_choices(tmp_path: Path) -> None:
    """Schnellwahl schreibt nichts; erst „Auswahl übernehmen“ wendet an."""
    root, service, app, _said = setup(tmp_path, {MAIN: b"A\n- [ ] a\n", NESTED: b"A\n- [x] a\n- b\n"})
    button(view(app), "Konfliktversion übernehmen", ft.OutlinedButton).on_click(None)
    assert (root / MAIN).read_bytes() == b"A\n- [ ] a\n" and len(service.conflicts()) == 1
    asyncio.run(button(view(app), "Auswahl übernehmen").on_click(None))
    assert (root / MAIN).read_bytes() == b"A\n- [x] a\n- b\n"


def test_edit_field_appears_for_bearbeitet_with_prefill(tmp_path: Path) -> None:
    _root, _service, app, _said = setup(tmp_path, {MAIN: b"A\n- x\n", NESTED: b"A\n- y\n"})
    choose(next(c for c in view(app) if isinstance(c, ft.RadioGroup)), "bearbeitet")
    [field] = [c for c in view(app) if isinstance(c, ft.TextField)]
    assert field.value == "A\n- x\n- y"


def test_main_deleted_header_and_discard_with_confirmation(tmp_path: Path) -> None:
    """Fehlende Hauptdatei: keine doppelte Kopfzeile, kein „inhaltlich gleich“, Verwerfen nach Bestätigung."""
    root, service, app, said = setup(tmp_path, {CONF: b"Notiz\n- [ ] a\n"})
    controls = view(app)
    shown = texts(controls)
    assert "Hauptdatei fehlt: Hauptdatei fehlt" not in shown and "inhaltlich gleich" not in shown
    assert conflict_view.MAIN_DELETED_HINT in shown
    button(controls, "Version verwerfen", ft.TextButton).on_click(None)
    [dialog] = app.page.dialogs
    asyncio.run(next(a for a in dialog.actions if a.content == "Verwerfen").on_click(None))
    service.clock.advance(121)  # Quarantäne des Löschprotokolls ablaufen lassen
    service.poll()
    assert not said and service.conflicts() == [] and list(root.iterdir()) == []


def test_main_deleted_restore_one_note(tmp_path: Path) -> None:
    root, _service, app, _said = setup(tmp_path, {CONF: b"A\n\nB\n"})
    groups = [c for c in view(app) if isinstance(c, ft.RadioGroup)]
    assert [g.value for g in groups] == [None, None]
    choose(groups[0], "haupt")  # „Weglassen“
    choose(groups[1], "konflikt")  # „Wiederherstellen“
    asyncio.run(button(view(app), "Auswahl übernehmen").on_click(None))
    assert (root / MAIN).read_bytes() == b"B\n"


def test_empty_version_is_named_and_offers_only_discard(tmp_path: Path) -> None:
    """Leere Version (nach dem Start entstanden): klarer Hinweis, kein Wiederherstellen, Verwerfen möglich."""
    _root, _service, app, _said = setup(tmp_path, {}, after_start={CONF: b""})
    controls = view(app)
    shown = texts(controls)
    assert "Diese Konfliktversion ist leer." in shown and "inhaltlich gleich" not in shown
    assert not any(isinstance(c, ft.Button) and c.content == "Alle Notizen wiederherstellen" for c in controls)
    assert button(controls, "Auswahl übernehmen").disabled
    assert any(isinstance(c, ft.TextButton) and c.content == "Version verwerfen" for c in controls)
