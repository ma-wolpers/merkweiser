"""Mobile: Einstellungsseite „Benachrichtigungen“ (W5)."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.notes_service import NotesService  # noqa: E402
from merkweiser.app.settings import Settings  # noqa: E402
from merkweiser.mobile.platform.notifications import NoNotifier  # noqa: E402
from merkweiser.mobile.ui.notify_view import NotifyController, notify_page  # noqa: E402
from tests.fakes import FakeClock  # noqa: E402


def make_app(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    saved, said = [], []
    app = SimpleNamespace(service=svc, settings=Settings(vault=str(root)), say=said.append, render=lambda: None,
                          page=SimpleNamespace(show_dialog=lambda d: None))

    async def save_settings(settings):
        saved.append(settings)
        app.settings = settings

    app.save_settings = save_settings
    app.notify = NotifyController(app)
    return app, saved, said


def test_without_extension_the_page_says_so(tmp_path: Path) -> None:
    app, _saved, _said = make_app(tmp_path)
    assert isinstance(app.notify.notifier, NoNotifier)
    [text] = notify_page(app, "")
    assert "noch nicht verfügbar" in text.value


def test_switch_asks_permission_then_saves_and_reschedules(tmp_path: Path) -> None:
    app, saved, said = make_app(tmp_path)
    asked = []

    class Fake:
        available = True

        async def request_permission(self):
            asked.append(True)
            return "denied"

        async def cancel_all(self):
            return None

        async def schedule(self, items):
            return len(items)

    app.notify.notifier = Fake()
    controls = notify_page(app, "")
    switch = next(c for c in controls if isinstance(c, ft.Switch))
    asyncio.run(switch.on_change(SimpleNamespace(control=SimpleNamespace(value=True))))
    assert asked and saved[-1].notify_enabled
    assert any("Erlaubnis" in s for s in said) and said[-1].startswith("Gespeichert; 13 Benachrichtigung")
    dropdown = next(c for c in notify_page(app, "") if isinstance(c, ft.Dropdown))
    asyncio.run(dropdown.on_select(SimpleNamespace(control=SimpleNamespace(value="7"))))
    assert saved[-1].notify_horizon == 7
