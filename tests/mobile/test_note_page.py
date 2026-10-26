"""W7 Phase 4: Notiz-Unterseite aus dem Tab „Todos“ und Knopf am Todo."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.nav import PageRef, note_arg, parse_note_arg  # noqa: E402
from merkweiser.app.settings import Settings  # noqa: E402
from merkweiser.core.patch import Target  # noqa: E402
from merkweiser.mobile.ui import pages, tabs  # noqa: E402
from merkweiser.mobile.ui.app import MobileApp  # noqa: E402
from tests.mobile.test_ampel_ui import fake  # noqa: E402
from tests.mobile.test_mobile_tabs import FakeAccess, FakePage, _walk_all  # noqa: E402

NOTE = "Elternabend #schule\nEinladung bis Freitag\n- [ ] Brief\n- [ ] Raum\n\nAnderes\n- [ ] bleibt\n"


def buttons(controls, tooltip: str) -> list:
    return [c for c in _walk_all(controls) if isinstance(c, ft.IconButton) and c.tooltip == tooltip]


def texts(controls) -> list[str]:
    return [c.value for c in _walk_all(controls) if isinstance(c, ft.Text) and c.value]


def test_note_arg_roundtrip_and_invalid() -> None:
    target = Target("2026-01-15.md", 3, '- [ ] „Zitat“ mit "Anführung" und\ttab')
    assert parse_note_arg(note_arg(target)) == target
    for bad in ("", "kein json", "[1, 2, 3]", '["a", -1, "x"]', '["a", "1", "x"]', "{}"):
        assert parse_note_arg(bad) is None


def test_open_button_only_in_todos_tab(tmp_path: Path) -> None:
    app = fake(tmp_path, {"2026-01-15.md": NOTE})
    app.open_page = lambda page: setattr(app, "opened", page)
    [first, *_rest] = buttons(tabs.todos_view(app), "Notiz öffnen")
    first.on_click(None)
    assert app.opened.kind == "notiz" and parse_note_arg(app.opened.arg).expected_text == "- [ ] Brief"
    assert buttons(tabs.day_view(app), "Notiz öffnen") == []


def test_page_shows_whole_note_with_move_button_only_there(tmp_path: Path) -> None:
    app = fake(tmp_path, {"2026-01-15.md": NOTE})
    app.page = FakePage()
    controls = pages.note_page(app, note_arg(Target("2026-01-15.md", 3, "- [ ] Raum")))
    shown = texts(controls)
    spans = [s.text for c in _walk_all(controls) if isinstance(c, ft.Text) for s in (c.spans or [])]
    assert {"Einladung bis Freitag", "Brief", "Raum"} <= set(shown) and "bleibt" not in shown
    assert "Elternabend " in spans and "#schule" in spans  # Thema mit antippbarem Tag
    assert len(buttons(controls, "Notiz verschieben")) == 1
    assert buttons(tabs.day_view(app), "Notiz verschieben") == []


def test_shifted_line_still_finds_the_right_note_duplicate_and_invalid_give_a_hint(tmp_path: Path) -> None:
    app = fake(tmp_path, {"2026-01-15.md": NOTE})
    arg = note_arg(Target("2026-01-15.md", 3, "- [ ] Raum"))
    (app.service.root / "2026-01-15.md").write_text("Neu oben\n- [ ] x\n\n" + NOTE, encoding="utf-8")
    assert "Einladung bis Freitag" in texts(pages.note_page(app, arg))
    (app.service.root / "2026-01-15.md").write_text(NOTE + "\nNochmal\n- [ ] Raum\n", encoding="utf-8")
    hint = texts(pages.note_page(app, note_arg(Target("2026-01-15.md", 99, "- [ ] Raum"))))
    assert any("nicht mehr eindeutig" in t for t in hint) and "Einladung bis Freitag" not in hint
    assert any("nicht mehr eindeutig" in t for t in texts(pages.note_page(app, "kaputt")))


def test_move_from_page_goes_back(tmp_path: Path) -> None:
    app = fake(tmp_path, {"2026-01-15.md": NOTE})
    app.page = FakePage()
    went_back = []
    app.go_back = lambda: went_back.append(True)
    [move] = buttons(pages.note_page(app, note_arg(Target("2026-01-15.md", 2, "- [ ] Brief"))), "Notiz verschieben")
    asyncio.run(move.on_click(None))
    [dialog] = app.page.dialogs
    assert dialog.title == "Notiz verschieben auf …"
    asyncio.run(dialog.content.controls[0].on_click(None))  # „Morgen“
    assert went_back == [True] and "Brief" in (app.service.root / "2026-01-16.md").read_text(encoding="utf-8")


def test_filter_survives_the_round_trip_to_the_page(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-15.md").write_text(NOTE, encoding="utf-8")
    page = SimpleNamespace(update=lambda: None, run_task=lambda _t: None, show_dialog=lambda _d: None)
    mobile = MobileApp(page, SimpleNamespace(data_dir=tmp_path / "app"), FakeAccess())
    mobile.settings = Settings(vault=str(root))
    asyncio.run(mobile.open_vault())
    asyncio.run(mobile._on_tab(SimpleNamespace(control=SimpleNamespace(selected_index=1))))
    chosen = {"status": "alle", "zeitraum": "beides", "tags": "schule", "oder": True}
    mobile._todo_filter = dict(chosen)
    mobile.open_page(PageRef("notiz", note_arg(Target("2026-01-15.md", 2, "- [ ] Brief"))))
    assert mobile.pages.top().kind == "notiz"
    assert mobile.go_back() and mobile.pages.top() is None and mobile.pages.current == 1
    assert mobile._todo_filter == chosen
