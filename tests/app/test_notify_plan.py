"""Tests für das Planen der Benachrichtigungen (W5) – rein und mit Vault-Inhalt."""

import asyncio
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from merkweiser.app.notes_service import NotesService
from merkweiser.app.notify_content import content_lines
from merkweiser.app.notify_plan import NEUTRAL, NotifySettings, plan
from merkweiser.app.settings import Settings
from tests.fakes import FakeClock

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 1, 15, 21, 0, tzinfo=BERLIN)  # Do abends: nächster Termin Fr 07:00


def settings(**kw) -> NotifySettings:
    return NotifySettings(**{"enabled": True, "at": time(7, 0), **kw})


def todos(_day: date) -> list[str]:
    return ["• Elternbrief"]


def test_first_is_content_then_escalating_neutral() -> None:
    result = plan(NOW, settings(horizon=5), todos, BERLIN)
    assert [p.at for p in result] == [datetime(2026, 1, 16 + i, 7, 0, tzinfo=BERLIN) for i in range(5)]
    assert result[0].title == "Deine Todos am 16.01." and result[0].body == "• Elternbrief"
    assert [p.level for p in result] == ["normal", "normal", "hoch", "maximal", "maximal"]
    assert result[1].body == NEUTRAL and "Seit 2 Tagen" in result[2].body


def test_no_todos_means_no_content_but_neutral_reminders() -> None:
    result = plan(NOW, settings(horizon=3), lambda _d: [], BERLIN)
    assert [p.id for p in result] == [2, 3] and all(p.title == "Merkweiser" for p in result)


def test_escalation_off_keeps_daily_normal_reminders() -> None:
    result = plan(NOW, settings(horizon=6, escalate=False), todos, BERLIN)
    assert len(result) == 6 and {p.level for p in result} == {"normal"} and {p.body for p in result[1:]} == {NEUTRAL}


def test_horizon_default_and_maximum() -> None:
    assert len(plan(NOW, settings(), todos, BERLIN)) == 14
    assert len(plan(NOW, settings(horizon=99), todos, BERLIN)) == 30
    assert plan(NOW, settings(enabled=False), todos, BERLIN) == []


def test_vacation_inclusive_pauses_counting_and_first_after_is_neutral() -> None:
    result = plan(NOW, settings(horizon=4, vacation_until=date(2026, 1, 18)), todos, BERLIN)
    assert [p.at.date() for p in result] == [date(2026, 1, 19), date(2026, 1, 20), date(2026, 1, 21)]
    assert [p.level for p in result] == ["normal", "hoch", "maximal"] and result[0].body == NEUTRAL


def test_trigger_day_is_today_before_the_time_and_content_uses_trigger_day() -> None:
    seen = []
    morning = datetime(2026, 1, 15, 6, 0, tzinfo=BERLIN)
    plan(morning, settings(horizon=1), lambda d: seen.append(d) or ["x"], BERLIN)
    plan(NOW, settings(horizon=1), lambda d: seen.append(d) or ["x"], BERLIN)
    assert seen == [date(2026, 1, 15), date(2026, 1, 16)]


def test_local_time_across_dst_and_long_lists() -> None:
    result = plan(datetime(2026, 3, 28, 20, 0, tzinfo=BERLIN), settings(horizon=2),
                  lambda _d: [f"• {i}" for i in range(12)], BERLIN)
    assert [p.at.utcoffset() for p in result] == [timedelta(hours=2), timedelta(hours=2)]  # nach der Umstellung 07:00 MESZ
    assert result[0].body.endswith("… und 4 weitere")
    assert result[0].as_item()["at"] == int(result[0].at.timestamp() * 1000)


def test_content_lines_urgent_first_and_trigger_day_only(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-10.md").write_bytes(b"Alt\n- [ ] ==Antrag==\n- [ ] alt normal\n")
    (root / "2026-01-16.md").write_bytes(b"Morgen\n- [ ] Elternbrief\n- [x] erledigt\n- [ ] ==Wichtig morgen==\n")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    assert content_lines(svc, date(2026, 1, 16)) == ["⭐ Antrag (10.01.)", "⭐ Wichtig morgen (16.01.)", "• Elternbrief"]


def test_settings_validation() -> None:
    assert Settings(notify_time="06:30").notify_at() == time(6, 30)
    with pytest.raises(ValueError):
        Settings(notify_time="7 Uhr").validated()
    with pytest.raises(ValueError):
        Settings(notify_horizon=31).validated()
    assert Settings(vacation_until="2026-08-01").vacation_date() == date(2026, 8, 1)


def test_controller_reschedules_and_tap_opens_today(tmp_path: Path) -> None:
    """Adapter-Attrappe: alles stornieren, dann planen; Payload „heute“ → Tab „Tag“ mit heute."""
    from merkweiser.mobile.ui.notify_view import NotifyController
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-16.md").write_bytes(b"T\n- [ ] a\n")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    calls, shown = [], []

    class Fake:
        available = True

        async def cancel_all(self):
            calls.append("cancel")

        async def schedule(self, items):
            calls.append(len(items))
            return len(items)

        async def launch_payload(self):
            return "heute"

    app = SimpleNamespace(service=svc, settings=Settings(vault=str(root), notify_enabled=True, notify_horizon=3),
                          show_day=shown.append)
    control = NotifyController(app)
    control.notifier = Fake()
    assert asyncio.run(control.reschedule()) == 3 and calls == ["cancel", 3]
    asyncio.run(control.check_launch())
    assert shown == [svc.clock.today()]
