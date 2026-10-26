"""Gemeinsame Todo-Reihenfolge (W7): Tab „Todos“ und Morgen-Benachrichtigung."""

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from merkweiser.app.notes_service import NotesService
from merkweiser.app.notify_content import NotifyContent, content
from merkweiser.app.notify_plan import MAX_LINES, NotifySettings, plan
from merkweiser.app.ordering import todo_groups
from merkweiser.app.settings import Settings
from merkweiser.app.views import HitRow
from merkweiser.core.inline import Urgency
from merkweiser.core.patch import Target
from tests.fakes import FakeClock

TODAY = date(2026, 1, 15)
BERLIN = ZoneInfo("Europe/Berlin")


def hit(day: str, text: str, level: int = 0, done: bool = False) -> HitRow:
    return HitRow(day, text, "", done, Urgency(level), Target(f"{day}.md", 0, text))


def texts(rows) -> list[str]:
    return [row.text for row in rows]


def test_day_boundary_and_red_block() -> None:
    rows = [hit("2026-01-14", "gestern gelb", 1), hit("2026-01-14", "gestern rot", 2),
            hit("2026-01-15", "heute normal"), hit("2026-01-15", "heute gelb", 1), hit("2026-01-15", "heute rot", 2),
            hit("2026-01-16", "morgen rot", 2), hit("2026-01-17", "übermorgen"), hit("2026-01-16", "morgen")]
    groups = todo_groups(rows, TODAY)
    assert texts(groups.red) == ["heute rot", "gestern rot", "morgen rot"]
    assert texts(groups.today) == ["heute gelb", "heute normal"]
    assert texts(groups.past) == ["gestern gelb"]          # steht unter allen heutigen
    assert texts(groups.future) == ["morgen", "übermorgen"]


def test_past_rank_then_newest_and_stable_within_a_day() -> None:
    rows = [hit("2026-01-10", "alt gelb", 1), hit("2026-01-12", "a"), hit("2026-01-12", "b"),
            hit("2026-01-14", "neu"), hit("2026-01-13", "mitte gelb", 1)]
    assert texts(todo_groups(rows, TODAY).past) == ["mitte gelb", "alt gelb", "neu", "a", "b"]


@pytest.mark.parametrize("status", ["offen", "erledigt", "alle"])
def test_every_row_exactly_once_and_done_never_pulled_forward(status: str) -> None:
    rows = [hit("2026-01-15", "offen rot", 2), hit("2026-01-15", "erledigt rot", 2, done=True),
            hit("2026-01-15", "normal"), hit("2026-01-14", "alt"), hit("2026-01-14", "erledigt gelb", 1, done=True)]
    wanted = [r for r in rows if status == "alle" or (r.done is (status == "erledigt"))]
    groups = todo_groups(wanted, TODAY)
    together = groups.red + groups.future + groups.today + groups.past
    assert sorted(texts(together)) == sorted(texts(wanted)) and len(together) == len(wanted)
    assert "erledigt rot" not in texts(groups.red)
    if status == "alle":  # erledigt gelb rückt nicht vor das offene „alt“
        assert texts(groups.past) == ["alt", "erledigt gelb"]
        assert texts(groups.today) == ["erledigt rot", "normal"]


def vault(tmp_path: Path) -> NotesService:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-10.md").write_text("Alt\n- [ ] ==🔴Alt rot==\n- [ ] ==Alt gelb==\n- [ ] alt normal\n",
                                        encoding="utf-8")
    (root / "2026-01-15.md").write_text("Heute\n- [ ] normal heute\n- [ ] ==gelb heute==\n- [x] ==🔴erledigt rot==\n"
                                        "- [ ] ==🔴rot heute==\n", encoding="utf-8")
    (root / "2026-01-20.md").write_text("Zukunft\n- [ ] ==🔴zukunft rot==\n- [ ] ==zukunft gelb==\n", encoding="utf-8")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    return svc


def test_notification_content_order_selection_and_bold(tmp_path: Path) -> None:
    found = content(vault(tmp_path), TODAY)
    assert found.lines == ("🔥 rot heute (15.01.)", "🔥 Alt rot (10.01.)", "⭐ gelb heute", "• normal heute",
                           "⭐ Alt gelb (10.01.)")  # keine normalen vergangenen, keine zukünftigen, keine erledigten
    assert (found.red, found.yellow, found.bold) == (2, 2, (0, 1, 2, 4))


def test_plan_title_channel_and_bold_indices(tmp_path: Path) -> None:
    svc = vault(tmp_path)
    now = datetime(2026, 1, 14, 21, 0, tzinfo=BERLIN)
    settings = NotifySettings(enabled=True, at=time(7, 0), horizon=2)
    first = plan(now, settings, lambda day: content(svc, day), BERLIN)[0]
    assert first.title == "Deine Todos am 15.01. · 🔥 2 · ⭐ 2" and first.level == "hoch"
    assert first.bold == (0, 1, 2, 4) and first.as_item()["bold"] == [0, 1, 2, 4]


def test_plan_without_red_is_normal_and_bold_follows_the_cut() -> None:
    lines = tuple(f"• {i}" for i in range(MAX_LINES + 2))
    found = NotifyContent(lines, red=0, yellow=3, bold=(0, MAX_LINES - 1, MAX_LINES + 1))
    first = plan(datetime(2026, 1, 14, 21, 0, tzinfo=BERLIN), NotifySettings(enabled=True, at=time(7, 0), horizon=1),
                 lambda _d: found, BERLIN)[0]
    assert first.level == "normal" and first.title == "Deine Todos am 15.01. · ⭐ 3"
    assert first.bold == (0, MAX_LINES - 1) and first.body.splitlines()[-1] == "… und 2 weitere"
    neutral = plan(datetime(2026, 1, 14, 21, 0, tzinfo=BERLIN), NotifySettings(enabled=True, at=time(7, 0), horizon=2),
                   lambda _d: NotifyContent(), BERLIN)[0]
    assert neutral.bold == () and neutral.as_item()["bold"] == []
