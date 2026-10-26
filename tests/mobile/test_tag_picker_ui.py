"""W7 Phase 6: #-Knopf öffnet den Tag-Picker über dem Editor."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.mobile.ui import note_dialogs  # noqa: E402
from merkweiser.mobile.ui.tag_picker import new_name, show_tag_picker  # noqa: E402
from tests.mobile.test_ampel_ui import fake  # noqa: E402
from tests.mobile.test_mobile_tabs import FakePage  # noqa: E402


def setup(tmp_path: Path):
    app = fake(tmp_path, {"2026-01-15.md": "Heute #schule\n- [ ] a #raum\n"})
    app.page = FakePage()
    return app


def test_hash_button_opens_picker_on_top_and_inserts(tmp_path: Path) -> None:
    app = setup(tmp_path)
    saved = []

    async def on_save(text: str) -> None:
        saved.append(text)

    editor = note_dialogs.editor_dialog(app, "- [ ] Brief", on_save, "leer")
    app.page.show_dialog(editor)
    bar, field = editor.content.controls[0], editor.content.controls[1]
    field.update = lambda: None

    async def focus() -> None:
        return None

    field.focus = focus
    asyncio.run(field.on_selection_change(SimpleNamespace(selection=ft.TextSelection(3, 3), selected_text="")))
    asyncio.run(bar.controls[-1].on_click(None))
    assert len(app.page.dialogs) == 2 and app.page.dialogs[-1].title == "Tag einfügen"  # über dem Editor
    picker = app.page.dialogs[-1]
    tiles = picker.content.controls[2].controls
    assert [t.title.value for t in tiles] == ["#schule", "#raum"]
    asyncio.run(tiles[1].on_click(None))
    assert app.page.dialogs == [editor] and field.value == "- [ ] Brief #raum"  # nur das Popup ist zu


def test_search_filters_offers_new_name_and_reports_invalid(tmp_path: Path) -> None:
    app = setup(tmp_path)
    picked = []

    async def pick(name: str) -> None:
        picked.append(name)

    dialog = show_tag_picker(app, "sch", pick, refresh=lambda _c: None)
    search, hint, listing = dialog.content.controls
    assert [t.title.value for t in listing.controls] == ["#sch neu verwenden", "#schule"]
    search.value = "("
    asyncio.run(search.on_change(None))
    assert hint.value and listing.controls[0].value == "Keine passenden Tags."
    search.value = "raum"
    asyncio.run(search.on_change(None))
    asyncio.run(listing.controls[-1].on_click(None))
    assert picked == ["raum"] and app.page.dialogs == []


def test_new_name_rules() -> None:
    assert new_name("#neu", {"schule"}, "projekt") == "neu"
    assert new_name("Schule", {"schule"}, "projekt") is None
    assert new_name("123", set(), "projekt") is None and new_name("zwei wörter", set(), "projekt") is None
