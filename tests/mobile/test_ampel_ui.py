"""Mobile: Ampel-Stern, farbige Leiste und Tagesgrenze im Tab „Todos“ (W7 Phase 1)."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.notes_service import NotesService  # noqa: E402
from merkweiser.app.settings import Settings  # noqa: E402
from merkweiser.mobile.ui import tabs  # noqa: E402
from merkweiser.mobile.ui.style import URGENCY_STYLE  # noqa: E402
from tests.fakes import FakeClock  # noqa: E402
from tests.mobile.test_mobile_tabs import _walk_all  # noqa: E402


def fake(tmp_path: Path, files: dict[str, str]) -> SimpleNamespace:
    root = tmp_path / "vault"
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    service = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    service.start()

    async def act(action):
        return action(service)

    return SimpleNamespace(service=service, settings=service.settings, act=act, say=lambda _m: None,
                           render=lambda: None, day=service.clock.today())


def star(controls) -> ft.IconButton:
    return next(c for c in _walk_all(controls) if isinstance(c, ft.IconButton) and c.icon in (
        ft.Icons.STAR, ft.Icons.STAR_BORDER))


def test_star_cycles_none_yellow_red_none_and_bar_only_when_open(tmp_path: Path) -> None:
    app = fake(tmp_path, {"2026-01-15.md": "Heute\n- [ ] Antrag #amt\n"})
    path = app.service.root / "2026-01-15.md"
    expected = ["- [ ] ==Antrag== #amt", "- [ ] ==🔴Antrag== #amt", "- [ ] Antrag #amt"]
    for level, line in enumerate(expected, start=1):
        button = star(tabs.day_view(app))
        assert button.tooltip == URGENCY_STYLE[(level - 1) % 3][2]
        asyncio.run(button.on_click(None))
        assert path.read_text(encoding="utf-8").splitlines()[1] == line
    path.write_text("Heute\n- [ ] ==🔴offen==\n- [x] ==🔴erledigt==\n", encoding="utf-8")
    app.service.cache.forget("2026-01-15.md")
    bars = [c for c in _walk_all(tabs.day_view(app)) if isinstance(c, ft.Container) and c.border is not None]
    assert len(bars) == 1 and bars[0].border.left.color == URGENCY_STYLE[2][1]
    texts = [c.value for c in _walk_all(tabs.day_view(app)) if isinstance(c, ft.Text) and c.value]
    assert "offen" in texts and not any("==" in t or "🔴" in t for t in texts)  # Anzeige ohne Markierung


def test_todos_tab_keeps_the_day_boundary_and_hides_the_future(tmp_path: Path) -> None:
    app = fake(tmp_path, {"2026-01-14.md": "Gestern\n- [ ] ==gestern gelb==\n- [ ] ==🔴gestern rot==\n",
                          "2026-01-15.md": "Heute\n- [ ] heute normal\n",
                          "2026-01-16.md": "Morgen\n- [ ] morgen\n"})
    texts = [c.value for c in _walk_all(tabs.todos_view(app)) if isinstance(c, ft.Text) and c.value
             and not c.value.startswith("20")]
    order = [t for t in texts if t in ("gestern rot", "heute normal", "gestern gelb", "morgen")]
    assert order == ["gestern rot", "heute normal", "gestern gelb"]


def missed_button(controls) -> ft.IconButton:
    """Der ⊘-Knopf der ersten Todo-Zeile (W9)."""
    return next(c for c in _walk_all(controls) if isinstance(c, ft.IconButton) and c.icon == ft.Icons.BLOCK)


def test_missed_button_toggles_open_and_missed_and_strikes_through(tmp_path: Path) -> None:
    """W9: ⊘ schaltet offen ↔ verpasst; verpasst ist durchgestrichen, blass und ohne Ampel-Leiste."""
    from merkweiser.mobile.ui.style import EXPLANATION, MISSED_STYLE, MISSED_TEXT
    app = fake(tmp_path, {"2026-01-15.md": "Heute\n- [ ] ==🔴Antrag== #amt\n"})
    path = app.service.root / "2026-01-15.md"
    button = missed_button(tabs.day_view(app))
    assert button.tooltip == MISSED_STYLE[False][2]
    asyncio.run(button.on_click(None))
    assert path.read_text(encoding="utf-8").splitlines()[1] == "- [-] ==🔴Antrag== #amt"
    controls = tabs.day_view(app)
    assert missed_button(controls).tooltip == MISSED_STYLE[True][2]
    assert missed_button(controls).icon_color == MISSED_STYLE[True][1]
    struck = [c for c in _walk_all(controls) if isinstance(c, ft.Text) and c.style is MISSED_TEXT]
    assert len(struck) == 1 and struck[0].color == EXPLANATION
    assert not [c for c in _walk_all(controls) if isinstance(c, ft.Container) and c.border is not None]
    checkbox = next(c for c in _walk_all(controls) if isinstance(c, ft.Checkbox))
    assert checkbox.value is False
    asyncio.run(missed_button(controls).on_click(None))
    assert path.read_text(encoding="utf-8").splitlines()[1] == "- [ ] ==🔴Antrag== #amt"


def test_tap_on_missed_text_marks_done(tmp_path: Path) -> None:
    """Tipp auf den Text eines verpassten Todos erledigt es (wie bei offenen)."""
    app = fake(tmp_path, {"2026-01-15.md": "Heute\n- [-] spät\n"})
    path = app.service.root / "2026-01-15.md"
    tap = next(c for c in _walk_all(tabs.day_view(app)) if isinstance(c, ft.GestureDetector))
    asyncio.run(tap.on_tap(None))
    assert path.read_text(encoding="utf-8").splitlines()[1] == "- [x] spät"


def test_preview_line_is_marked_and_checks_early(tmp_path: Path) -> None:
    """W9: Vorschauzeile mit 🔁, ohne Stern-/⊘-/Verschieben-Knöpfe; Häkchen schreibt ``[x]`` in die Datei des Tages."""
    from merkweiser.app.todo_list import DEFAULT_FILTER
    from merkweiser.mobile.ui.routine_view import ROUTINE_MARK
    app = fake(tmp_path, {"Routinen.md": "## wöchentlich Fr\n- [ ] ==Einkauf==\n"})
    app._todo_filter = {**DEFAULT_FILTER, "zeitraum": "zukünftig"}
    controls = tabs.todos_view(app)
    texts = [c.value or "".join(s.text for s in c.spans or []) for c in _walk_all(controls) if isinstance(c, ft.Text)]
    assert f"{ROUTINE_MARK} 2026-01-16 · wöchentlich Fr" in texts and "Einkauf #wdh" in texts  # Tag als Span
    assert not [c for c in _walk_all(controls) if isinstance(c, ft.IconButton)
                and c.icon in (ft.Icons.BLOCK, ft.Icons.EVENT, ft.Icons.STAR, ft.Icons.STAR_BORDER)]
    checkbox = next(c for c in _walk_all(controls) if isinstance(c, ft.Checkbox))
    checkbox.value = True
    asyncio.run(checkbox.on_change(SimpleNamespace(control=checkbox)))
    assert (app.service.root / "2026-01-16.md").read_bytes().decode() == "wöchentlich Fr\n- [x] ==Einkauf== #wdh\n"
