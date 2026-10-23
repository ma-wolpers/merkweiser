"""Mobile: Kopf-Entscheidungen im Konfliktdialog (W6, Y5)."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.notes_service import NotesService  # noqa: E402
from merkweiser.app.settings import Settings  # noqa: E402
from merkweiser.mobile.ui import conflict_view  # noqa: E402
from tests.fakes import FakeClock  # noqa: E402

MAIN = "2026-01-15.md"
CONF = "2026-01-15.sync-conflict-20260115-120000-AAAAAAA.md"
STAMP = b"messung_start: 2026-01-15T08:00:00+01:00\nmessung_taetigkeit: Orga\n"


def walk(controls):
    for control in controls:
        yield control
        yield from walk(getattr(control, "controls", None) or [])
        content = getattr(control, "content", None)
        if isinstance(content, ft.Control):
            yield from walk([content])


def test_stamp_decision_then_merge_writes_one_clean_head(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / MAIN).write_bytes(b"---\nzeit_Orga: 10\n" + STAMP + b"---\nThema\n- [ ] a\n")
    (root / CONF).write_bytes(b"---\nzeit_Orga: 40\n---\nThema\n- [ ] a\n- [ ] b\n")
    service = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    service.start()
    said = []

    async def act(action):
        try:
            return action(service)
        except Exception as exc:  # wie MobileApp.act: Fehler anzeigen
            said.append(str(exc))

    app = SimpleNamespace(service=service, act=act, say=said.append, render=lambda: None)
    controls = conflict_view.conflicts_view(app)
    [group] = [c for c in walk(controls) if isinstance(c, ft.RadioGroup) and c.content.controls[0].value == "weiter"]
    merge = next(c for c in walk(controls) if isinstance(c, ft.Button) and c.content == "Zusammenführen")
    asyncio.run(merge.on_click(None))
    assert said and "Entscheidung" in said[0]  # ohne Wahl: Hinweis, nichts geschrieben
    group.on_change(SimpleNamespace(control=SimpleNamespace(value="verwerfen")))
    asyncio.run(merge.on_click(None))
    assert (root / MAIN).read_bytes() == b"---\nzeit_Orga: 40\n---\nThema\n- [ ] a\n- [ ] b\n"
