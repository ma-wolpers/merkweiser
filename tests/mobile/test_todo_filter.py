"""W7 Phase 5: Filter-Knopf und Dialog im Tab „Todos“."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.todo_list import DEFAULT_FILTER  # noqa: E402
from merkweiser.mobile.ui import tabs  # noqa: E402
from tests.mobile.test_ampel_ui import fake  # noqa: E402
from tests.mobile.test_mobile_tabs import FakePage, _walk_all  # noqa: E402

FILES = {"2026-01-14.md": "Gestern\n- [ ] gestern\n", "2026-01-15.md": "Heute\n- [ ] heute\n",
         "2026-01-16.md": "Morgen #x\n- [ ] morgen\n"}


def setup(tmp_path: Path):
    app = fake(tmp_path, FILES)
    app.page = FakePage()
    return app


def head_of(controls):
    row = controls[0]
    return row.controls[0], row.controls[1].value


def texts(controls) -> list[str]:
    return [c.value for c in _walk_all(controls) if isinstance(c, ft.Text) and c.value]


def test_header_sections_and_no_old_controls(tmp_path: Path) -> None:
    app = setup(tmp_path)
    controls = tabs.todos_view(app)
    button, summary = head_of(controls)
    assert button.icon == ft.Icons.FILTER_LIST and button.badge is None and summary == "offen · bis heute"
    shown = texts(controls)
    assert "Heute (1)" in shown and "Frühere Tage (1)" in shown and "morgen" not in shown
    assert not any(isinstance(c, (ft.Dropdown, ft.Switch, ft.TextField)) for c in _walk_all(controls))


def test_apply_reset_and_cancel(tmp_path: Path) -> None:
    app = setup(tmp_path)
    button, _summary = head_of(tabs.todos_view(app))
    asyncio.run(button.on_click(None))
    [dialog] = app.page.dialogs
    status, span, tags, either = [c for c in dialog.content.controls if not isinstance(c, ft.Text)]
    span.selected = ["beides"]
    tags.value = "#x"
    either.value = True
    asyncio.run(dialog.actions[2].on_click(None))  # Anwenden
    assert app.page.dialogs == [] and app._todo_filter == {"status": "offen", "zeitraum": "beides", "tags": "#x",
                                                           "oder": True}
    controls = tabs.todos_view(app)
    button, summary = head_of(controls)
    assert button.badge == "3" and summary == "offen · alle Tage · #x · ODER" and "morgen" in texts(controls)
    asyncio.run(button.on_click(None))
    [dialog] = app.page.dialogs
    dialog.content.controls[5].value = "verworfen"
    asyncio.run(dialog.actions[1].on_click(None))  # Abbrechen
    assert app._todo_filter["tags"] == "#x"
    asyncio.run(head_of(tabs.todos_view(app))[0].on_click(None))
    asyncio.run(app.page.dialogs[-1].actions[0].on_click(None))  # Zurücksetzen
    assert app._todo_filter == DEFAULT_FILTER and head_of(tabs.todos_view(app))[0].badge is None


def test_empty_list_says_so(tmp_path: Path) -> None:
    app = setup(tmp_path)
    app._todo_filter = {**DEFAULT_FILTER, "tags": "gibtsnicht"}
    assert "Keine Todos." in texts(tabs.todos_view(app))
