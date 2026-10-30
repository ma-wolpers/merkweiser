"""Mobile: Tab „Zeit“, Dialoge und Ticker (W6, Y12)."""

import asyncio
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from merkweiser.app.notes_service import NotesService  # noqa: E402
from merkweiser.app.settings import Settings  # noqa: E402
from merkweiser.app.ticker import Ticker  # noqa: E402
from merkweiser.core.frontmatter import Stamp, minutes, parse_bytes  # noqa: E402
from merkweiser.mobile.ui import time_view  # noqa: E402
from merkweiser.mobile.ui.time_dialogs import end_from_time  # noqa: E402
from tests.fakes import FakeClock  # noqa: E402

CET = timezone(timedelta(hours=1))


class Handle:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def test_ticker_keeps_at_most_one_task() -> None:
    """Y12: mehrfaches Öffnen → genau ein aktiver Task; Verlassen → keiner."""
    handles = []
    ticker = Ticker(lambda tick: handles.append(Handle()) or handles[-1])
    ticker.start(lambda: None)
    ticker.start(lambda: None)
    assert len(handles) == 2 and handles[0].cancelled and not handles[1].cancelled and ticker.active
    ticker.stop()
    assert handles[1].cancelled and not ticker.active
    ticker.stop()  # ohne Task: nichts


def test_end_from_time_uses_today_or_yesterday() -> None:
    now = datetime(2026, 1, 15, 1, 30, tzinfo=CET)
    start = datetime(2026, 1, 14, 22, 0, tzinfo=CET)
    assert end_from_time(time(23, 45), start, now) == datetime(2026, 1, 14, 23, 45, tzinfo=CET)
    assert end_from_time(time(1, 10), start, now) == datetime(2026, 1, 15, 1, 10, tzinfo=CET)


def test_running_text() -> None:
    stamp = Stamp(datetime(2026, 1, 15, 8, 15, tzinfo=CET), "Orga")
    assert time_view.running_text(stamp, datetime(2026, 1, 15, 9, 38, 59, tzinfo=CET)) == "„Orga“ läuft seit 08:15 (1:23)"


def fake_app(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-14.md").write_bytes(b"---\nzeit_Kurs: 45\n---\nX\n")
    service = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    service.start()
    said, dialogs, pages = [], [], []

    async def act(action):
        try:
            return action(service)
        except Exception as exc:
            said.append(str(exc))

    app = SimpleNamespace(service=service, act=act, say=lambda m, link=False: said.append(m), render=lambda: None,
                          open_page=pages.append, page=SimpleNamespace(show_dialog=dialogs.append,
                                                                       pop_dialog=lambda: dialogs.pop()))
    return app, said, dialogs, pages


def buttons(controls):
    found = []
    for control in controls:
        if isinstance(control, (ft.Button, ft.TextButton)):
            found.append(control)
        found += buttons(getattr(control, "controls", None) or [])
    return found


def by_label(controls, label: str):
    return next(b for b in buttons(controls) if b.content == label)


def quick_row(controls, tooltip: str) -> ft.Row:
    """Die Zeile aus beschriftetem Knopf und Schnellknopf mit diesem Tooltip."""
    return next(c for c in controls if isinstance(c, ft.Row) and isinstance(c.controls[-1], ft.IconButton)
                and c.controls[-1].tooltip == tooltip)


def test_start_then_stop_from_the_tab(tmp_path: Path) -> None:
    app, said, _dialogs, _pages = fake_app(tmp_path)
    controls = time_view.time_view(app)
    dropdown = next(c for c in controls if isinstance(c, ft.Dropdown))
    assert [o.key for o in dropdown.options] == ["Kurs", "Orga"]  # Kurs hat Minuten in den letzten 7 Tagen
    asyncio.run(by_label(controls, "Start").on_click(None))
    assert app.time_tick is None  # Ticker meldet erst die nächste Ansicht an
    app.service.clock.advance(25 * 60)
    controls = time_view.time_view(app)
    assert controls[0].value.startswith("„Kurs“ läuft seit 10:00 (0:25)") and app.time_tick is not None
    button, stop = quick_row(controls, "Sofort stoppen").controls
    assert button.content == "Messung beenden" and stop.icon == ft.Icons.STOP
    assert not [b for b in buttons(controls) if b.content == "Stopp"]
    asyncio.run(stop.on_click(None))
    app.service.clock.advance(121)
    app.service.writer.finish_due()
    head = parse_bytes((app.service.root / "2026-01-15.md").read_bytes())
    assert minutes(head)[0] == {"Kurs": 25} and any("0:25 eingetragen" in s for s in said)


def test_abort_dialog_without_time_and_overview_ranges(tmp_path: Path) -> None:
    app, said, dialogs, pages = fake_app(tmp_path)
    asyncio.run(by_label(time_view.time_view(app), "Start").on_click(None))
    controls = time_view.time_view(app)
    by_label(controls, "Messung beenden").on_click(None)
    assert dialogs[-1].title.value == "Messung beenden"
    asyncio.run(dialogs[-1].actions[1].on_click(None))  # „Keine Zeit eintragen“
    assert any("verworfen" in s for s in said)
    controls = time_view.time_view(app)
    seg = next(c for c in controls if isinstance(c, ft.SegmentedButton))
    asyncio.run(seg.on_change(SimpleNamespace(control=SimpleNamespace(selected=["14"]))))
    assert app._time["days"] == 14
    lines = [c.value for c in time_view.time_view(app) if isinstance(c, ft.Text) and c.value]
    assert len([line for line in lines if ": " in line and line[:2] in ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")]) == 14
    assert any(line.startswith("Summe: Kurs 0:45") for line in lines)
    by_label(time_view.time_view(app), "Tätigkeiten verwalten").on_click(None)
    assert pages[-1].kind == "taetigkeiten"


def test_activities_page_add_and_rename_with_merge_question(tmp_path: Path) -> None:
    app, said, dialogs, _pages = fake_app(tmp_path)
    controls = time_view.activities_page(app, "")
    field = next(c for row in controls if isinstance(row, ft.Row) for c in row.controls if isinstance(c, ft.TextField))
    field.value = "Verwaltung"
    asyncio.run(by_label(controls, "Hinzufügen").on_click(None))
    assert said[-1] == "„Verwaltung“ hinzugefügt."
    rows = [r for r in time_view.activities_page(app, "") if isinstance(r, ft.Row) and isinstance(r.controls[0], ft.Text)]
    kurs = next(r for r in rows if r.controls[0].value == "Kurs")
    kurs.controls[1].on_click(None)  # Umbenennen
    dialogs[-1].content.value = "Verwaltung"
    asyncio.run(dialogs[-1].actions[1].on_click(None))
    assert dialogs[-1].title.value == "Name gibt es schon"
    asyncio.run(dialogs[-1].actions[1].on_click(None))
    app.service.clock.advance(121)
    app.service.writer.finish_due()
    assert minutes(parse_bytes((app.service.root / "2026-01-14.md").read_bytes()))[0] == {"Verwaltung": 45}


def test_mobile_app_runs_ticker_only_while_time_tab_is_visible(tmp_path: Path) -> None:
    """Y12 in der App: ein Task im sichtbaren Zeit-Tab; Tabwechsel und Hintergrund beenden ihn."""
    from merkweiser.app import time_service as ts
    from merkweiser.mobile.ui.app import TIME_TAB, MobileApp
    from tests.mobile.test_mobile_tabs import FakeAccess
    root = tmp_path / "vault"
    root.mkdir()
    handles = []
    page = SimpleNamespace(update=lambda: None, run_task=lambda tick: handles.append(Handle()) or handles[-1])
    mobile = MobileApp(page, SimpleNamespace(data_dir=tmp_path / "app"), FakeAccess())
    mobile.settings = Settings(vault=str(root))
    asyncio.run(mobile.open_vault())
    ts.start(mobile.service, "Orga")
    tab = lambda i: asyncio.run(mobile._on_tab(SimpleNamespace(control=SimpleNamespace(selected_index=i))))  # noqa: E731
    tab(TIME_TAB)
    mobile.render()
    assert len(handles) == 2 and handles[0].cancelled and mobile.ticker.active
    tab(0)
    assert handles[1].cancelled and not mobile.ticker.active
    tab(TIME_TAB)
    asyncio.run(mobile._on_lifecycle(SimpleNamespace(state="AppLifecycleState.HIDE")))
    assert not mobile.ticker.active


def test_switch_button_opens_time_picker_and_mini_button_switches_now(tmp_path: Path) -> None:
    """W6a: „Wechseln zu …“ öffnet die Uhrzeit-Wahl (vorbelegt jetzt); der Mini-Knopf wechselt sofort."""
    app, said, dialogs, _pages = fake_app(tmp_path)
    asyncio.run(by_label(time_view.time_view(app), "Start").on_click(None))  # Kurs ab 10:00
    app._time["activity"] = "Orga"
    app.service.clock.advance(60 * 60)  # 11:00
    controls = time_view.time_view(app)
    dialog_button, mini = quick_row(controls, "Sofort wechseln").controls
    assert dialog_button.content == "Wechseln zu „Orga“"
    dialog_button.on_click(None)
    picker = dialogs[-1]
    assert isinstance(picker, ft.TimePicker) and picker.value.hour == 11
    asyncio.run(picker.on_change(SimpleNamespace(control=SimpleNamespace(value=time(10, 20)))))
    assert any("„Orga“ läuft seit 10:20" in s for s in said)
    app.service.clock.advance(121)
    app.service.writer.finish_due()
    head = parse_bytes((app.service.root / "2026-01-15.md").read_bytes())
    assert minutes(head)[0] == {"Kurs": 20}
    app._time["activity"] = "Kurs"
    row = quick_row(time_view.time_view(app), "Sofort wechseln")
    asyncio.run(row.controls[1].on_click(None))
    assert any("„Kurs“ läuft seit" in s for s in said)
