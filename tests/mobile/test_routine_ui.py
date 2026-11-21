"""Tests der Routinen-Oberfläche (W9 P6): Seite, Dialog, Kopf-Knopf, Tipp auf Vorschauzeile. Ohne Fenster."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.todo_list import DEFAULT_FILTER  # noqa: E402
from merkweiser.mobile.ui import pages, routine_dialog, routine_view, tabs  # noqa: E402
from tests.mobile.test_ampel_ui import fake  # noqa: E402
from tests.mobile.test_mobile_tabs import _walk_all  # noqa: E402

RULES = "## täglich\n- [ ] Mails\n- [x] Alt\n\n## stündlich\n- [ ] kaputt\n\n## Pausen\n- 21.12.2026 bis 04.01.2027\n"


class Page:
    """Seite ohne Fenster: Dialoge als Stapel, ``update`` zählt nur."""

    def __init__(self) -> None:
        self.dialogs, self.updates = [], 0

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def update(self) -> None:
        self.updates += 1


def ui(tmp_path: Path, files: dict[str, str]) -> SimpleNamespace:
    """App-Attrappe mit echtem Service, Dialog-Seite und gemerkten Meldungen/Seiten."""
    app = fake(tmp_path, files)
    app.page, app.messages, app.opened = Page(), [], []
    app.say = app.messages.append
    app.open_page = app.opened.append
    app.go_back = lambda: None
    return app


def texts(controls) -> list[str]:
    """Alle Texte (auch aus Spans)."""
    return [c.value or "".join(s.text for s in c.spans or []) for c in _walk_all(controls) if isinstance(c, ft.Text)]


def test_page_lists_sections_errors_pauses_and_setting(tmp_path: Path) -> None:
    """Seite: Kopf, Karten je Rhythmus (pausierte markiert), nicht lesbare Zeilen, Pausen, Vorschau-Länge."""
    app = ui(tmp_path, {"Routinen.md": RULES})
    controls = pages.build_page(app, pages.PageRef("routinen"))
    shown = texts(controls)
    assert "Routinen" in shown and "täglich" in shown and "Mails" in shown and "Alt (pausiert)" in shown
    assert any(t.startswith("Zeile ") and "## stündlich" in t for t in shown) and "21.12.2026 bis 04.01.2027" in shown
    assert any(isinstance(c, ft.Dropdown) and c.value == "7" for c in _walk_all(controls))


def test_new_rule_dialog_adapts_fields_and_saves(tmp_path: Path) -> None:
    """Neue Routine: Felder je Rhythmus-Art, ungültig → Hinweis im Dialog, gültig → Datei geschrieben."""
    app = ui(tmp_path, {})
    routine_dialog.show_rule_dialog(app)
    [dialog] = app.page.dialogs
    controls = list(_walk_all([dialog.content]))
    body = next(c for c in controls if isinstance(c, ft.TextField) and c.label == "Todo")
    kind = next(c for c in controls if isinstance(c, ft.Dropdown))
    weekdays = next(c for c in controls if isinstance(c, ft.SegmentedButton))
    assert not weekdays.visible
    kind.value = "wöchentlich"
    weekdays.selected = []
    kind.on_select(None)  # synchroner Handler (Flet erlaubt beides)
    assert weekdays.visible
    save = dialog.actions[-1]
    asyncio.run(save.on_click(None))
    hint = dialog.content.controls[-1]
    assert app.page.dialogs and hint.value == "Wochentag fehlt, z. B. „wöchentlich Mo“"
    body.value, weekdays.selected = "Wochenplan", ["0", "4"]
    asyncio.run(save.on_click(None))
    assert not app.page.dialogs
    assert (app.service.root / "Routinen.md").read_bytes().decode().endswith("\n## wöchentlich Mo, Fr\n- [ ] Wochenplan\n")


def test_header_button_and_preview_tap(tmp_path: Path) -> None:
    """🔁 im Todos-Kopf öffnet die Seite; Tipp auf eine Vorschauzeile öffnet den Dialog der Regel."""
    app = ui(tmp_path, {"Routinen.md": "## wöchentlich Fr\n- [ ] Einkauf\n"})
    app._todo_filter = {**DEFAULT_FILTER, "zeitraum": "zukünftig"}
    controls = tabs.todos_view(app)
    button = next(c for c in _walk_all(controls) if isinstance(c, ft.IconButton) and c.icon == ft.Icons.REPEAT)
    button.on_click(None)
    assert app.opened == [pages.PageRef("routinen")]
    tap = next(c for c in _walk_all(controls) if isinstance(c, ft.GestureDetector))
    tap.on_tap(None)
    [dialog] = app.page.dialogs
    body = next(c for c in _walk_all([dialog.content]) if isinstance(c, ft.TextField) and c.label == "Todo")
    assert body.value == "Einkauf" and dialog.title == "Routine bearbeiten"
    assert routine_view.ROUTINE_MARK == "🔁"
