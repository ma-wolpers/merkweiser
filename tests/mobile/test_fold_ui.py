"""Mobile: einklappbare Todos und ↳ für Unter-Todos (W10)."""

import asyncio
from pathlib import Path

import pytest

ft = pytest.importorskip("flet")

from merkweiser.mobile.ui import tabs  # noqa: E402
from merkweiser.mobile.ui.note_view import FOLD_CLOSED, FOLD_OPEN, SUB_MARK  # noqa: E402
from tests.mobile.test_ampel_ui import fake  # noqa: E402

DAY = ("Heute\n- [ ] Eltern\n  - [ ] offen\n  - [x] erledigt\n  - [-] verpasst\n  - Punkt\n"
       "- [ ] allein\n- Liste\n  - [x] unter Punkt\n")


def visible(control) -> list:
    """Sichtbare Controls rekursiv (unsichtbare samt Inhalt entfallen)."""
    if control.visible is False:
        return []
    found = [control]
    for child in getattr(control, "controls", None) or []:
        found += visible(child)
    if isinstance(getattr(control, "content", None), ft.Control):
        found += visible(control.content)
    return found


def texts(controls) -> list[str]:
    return [c.value for root in controls for c in visible(root) if isinstance(c, ft.Text) and c.value]


def switch(controls, label: str):
    return next(c for root in controls for c in visible(root) if isinstance(c, ft.Container)
                and isinstance(c.content, ft.Text) and c.content.value == label)


def test_collapsed_by_default_only_open_sub_todos_show(tmp_path: Path) -> None:
    app = fake(tmp_path, {"2026-01-15.md": DAY})
    shown = texts(tabs.day_view(app))
    assert "offen" in shown and FOLD_CLOSED.format(3) in shown
    assert not {"erledigt", "verpasst", "Punkt"} & set(shown)
    assert "unter Punkt" in shown  # Kinder von Punkten klappen nicht ein
    assert shown.count(SUB_MARK) == 1  # nur das offene Unter-Todo ist sichtbar und gekennzeichnet


def test_switch_expands_in_place_and_state_survives_render(tmp_path: Path) -> None:
    app = fake(tmp_path, {"2026-01-15.md": DAY})
    controls = tabs.day_view(app)
    button = switch(controls, FOLD_CLOSED.format(3))
    box = next(c for root in controls for c in visible(root) if isinstance(c, ft.Column) and button in c.controls)
    box.update = lambda: None  # ohne Seite kein Update möglich
    asyncio.run(button.on_click(None))
    shown = texts(controls)
    assert {"erledigt", "verpasst", "Punkt", FOLD_OPEN} <= set(shown) and shown.count(SUB_MARK) == 3
    assert {"erledigt", "Punkt", FOLD_OPEN} <= set(texts(tabs.day_view(app)))  # nach dem Neuzeichnen
    again = tabs.day_view(app)
    box = next(c for root in again for c in visible(root) if isinstance(c, ft.Column)
               and switch(again, FOLD_OPEN) in c.controls)
    box.update = lambda: None
    asyncio.run(switch(again, FOLD_OPEN).on_click(None))
    assert "erledigt" not in texts(again)


def test_ticking_a_sub_todo_keeps_the_fold_state(tmp_path: Path) -> None:
    """Abhaken ändert den Schlüssel nicht; das abgehakte Unter-Todo wandert in den eingeklappten Teil."""
    app = fake(tmp_path, {"2026-01-15.md": DAY})
    from merkweiser.core.inline import TodoStatus
    from merkweiser.core.patch import Target
    app.service.set_status(Target("2026-01-15.md", 2, "  - [ ] offen"), TodoStatus.DONE)
    shown = texts(tabs.day_view(app))
    assert "offen" not in shown and FOLD_CLOSED.format(4) in shown and SUB_MARK not in shown
