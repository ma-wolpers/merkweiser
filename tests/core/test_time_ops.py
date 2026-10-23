"""Tests für den Zeit-Tracker-Core (W6, PLAN-SPAETERE-SCHRITTE.md S1/S2/S7, Y1/Y2)."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from merkweiser.core.frontmatter import Stamp, minutes, parse_bytes, stamp_of
from merkweiser.core.fsops import SimulatedCrash
from merkweiser.core.recovery import recover
from merkweiser.core.time_ops import (MeasurementError, Part, book, discard_stamp, pending_booking, plan_rename_file,
                                      recover_time_ops, rename, start_measurement)
from merkweiser.core.timetrack import hm, order_activities, segments, stale
from tests.core.test_move_exec import Env

BERLIN = ZoneInfo("Europe/Berlin")
CET = timezone(timedelta(hours=1))
D1, D2 = "2026-01-01.md", "2026-01-02.md"
START = Stamp(datetime(2026, 1, 1, 22, 0, tzinfo=CET), "Orga")


# --- rein (S7) ------------------------------------------------------------------------------


def test_same_day_floors_minutes() -> None:
    start = datetime(2026, 1, 1, 8, 15, 30, tzinfo=CET)
    assert segments(start, start.replace(hour=9, minute=0, second=10), date(2026, 1, 1), BERLIN) == [
        (date(2026, 1, 1), 44)]
    assert segments(start, start, date(2026, 1, 1), BERLIN) == []


def test_midnight_split_floors_each_part() -> None:
    start = datetime(2026, 1, 1, 23, 30, 30, tzinfo=CET)
    end = datetime(2026, 1, 2, 0, 10, 50, tzinfo=CET)
    assert segments(start, end, date(2026, 1, 1), BERLIN) == [(date(2026, 1, 1), 29), (date(2026, 1, 2), 10)]


@pytest.mark.parametrize("day, first, second", [(date(2026, 3, 28), 120, 180), (date(2026, 10, 24), 120, 300)])
def test_dst_nights_keep_true_duration(day: date, first: int, second: int) -> None:
    """Sommerzeit (eine Stunde weniger) und Winterzeit (eine mehr): Summe = echte Dauer."""
    start = datetime(day.year, day.month, day.day, 22, 0, tzinfo=BERLIN)
    end = datetime(day.year, day.month, day.day + 1, 4, 0, tzinfo=BERLIN)
    parts = segments(start, end, day, BERLIN)
    assert parts == [(day, first), (day + timedelta(days=1), second)]
    real = end.astimezone(timezone.utc) - start.astimezone(timezone.utc)  # echte Dauer (nicht Wanduhr)
    assert sum(m for _, m in parts) == int(real.total_seconds() // 60)


def test_timezone_change_keeps_total() -> None:
    """GRENZE(Zeitzone): andere Zone beim Stoppen → Summe stimmt, nur die Teilung verschiebt sich."""
    start = datetime(2026, 1, 1, 22, 0, tzinfo=CET)
    end = datetime(2026, 1, 2, 2, 0, tzinfo=CET)
    parts = segments(start, end, date(2026, 1, 1), ZoneInfo("America/New_York"))
    assert sum(m for _, m in parts) == 240


def test_helpers() -> None:
    now = datetime(2026, 1, 2, 22, 1, tzinfo=CET)
    assert stale(START.start, now) and not stale(START.start, now - timedelta(minutes=2))
    assert hm(65) == "1:05" and hm(0) == "0:00"
    assert order_activities(["b", "Orga", "a", "Kurs"], {"Kurs": 30, "Orga": 30, "b": 5}) == ["Kurs", "Orga", "b", "a"]


# --- Buchung (S1/Y1) ------------------------------------------------------------------------


def setup(tmp_path, crash=None) -> Env:
    env = Env(tmp_path, crash=crash)
    (env.root / D1).write_bytes(b"---\nzeit_Orga: 10\nmessung_start: 2026-01-01T22:00:00+01:00\n"
                                b"messung_taetigkeit: Orga\n---\nThema\n")
    return env


def run_booking(env: Env) -> str:
    end = datetime(2026, 1, 2, 1, 30, tzinfo=CET)
    return book(env.writer, env.store, START, D1, end, [Part(D1, date(2026, 1, 1), 120), Part(D2, date(2026, 1, 2), 90)])


def assert_booked_once(env: Env) -> None:
    head1, head2 = parse_bytes((env.root / D1).read_bytes()), parse_bytes((env.root / D2).read_bytes())
    assert minutes(head1)[0] == {"Orga": 130} and stamp_of(head1) is None
    assert minutes(head2)[0] == {"Orga": 90}


def test_booking_over_midnight(tmp_path) -> None:
    env = setup(tmp_path)
    assert run_booking(env) == ""
    env.settle()
    assert_booked_once(env)
    assert (env.root / D1).read_bytes().endswith(b"---\nThema\n")


@pytest.mark.parametrize("nth", [1, 2])
def test_crash_before_each_step_resumes_exactly_once(tmp_path, nth: int) -> None:
    """Y1: Absturz vor dem 1. bzw. 2. Schreibschritt → Wiederaufnahme ohne doppelte Minuten, Stempel weg."""
    env = setup(tmp_path, crash=("write:before_prepared", nth))
    with pytest.raises(SimulatedCrash):
        run_booking(env)
    env.die()
    fresh = Env(tmp_path)
    assert pending_booking(fresh.store) is not None
    recover(fresh.writer)
    fresh.settle()
    assert len(recover_time_ops(fresh.writer, fresh.store)) == 1
    fresh.settle()
    assert_booked_once(fresh)
    assert pending_booking(fresh.store) is None and recover_time_ops(fresh.writer, fresh.store) == []


@pytest.mark.parametrize("point", ["write:tmp_ready", "write:installed"])
def test_crash_inside_a_step_resumes_exactly_once(tmp_path, point: str) -> None:
    env = setup(tmp_path, crash=(point, 2))
    with pytest.raises(SimulatedCrash):
        run_booking(env)
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    fresh.settle()
    recover_time_ops(fresh.writer, fresh.store)
    fresh.settle()
    assert_booked_once(fresh)


def test_stamp_gone_before_first_step_books_nothing(tmp_path) -> None:
    env = setup(tmp_path)
    (env.root / D1).write_bytes(b"---\nzeit_Orga: 40\n---\nThema\n")  # anderes Gerät hat gestoppt
    assert "anderswo beendet" in run_booking(env)
    assert not (env.root / D2).exists() and minutes(parse_bytes((env.root / D1).read_bytes()))[0] == {"Orga": 40}


def test_stamp_gone_after_first_step_stops_further_booking(tmp_path) -> None:
    env = setup(tmp_path, crash=("write:before_prepared", 2))
    with pytest.raises(SimulatedCrash):
        run_booking(env)
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    fresh.settle()
    (fresh.root / D1).write_bytes(b"---\nzeit_Orga: 40\n---\nThema\n")
    [op_id] = [o for o in fresh.store.all_ids() if fresh.store.read(o)[0].get("art") == "zeitbuchung"]
    from merkweiser.core.time_ops import resume
    hint = resume(fresh.writer, fresh.store, op_id)
    assert "Schon eingetragen" in hint and D2 in hint
    assert minutes(parse_bytes((fresh.root / D1).read_bytes()))[0] == {"Orga": 40}


def test_switch_same_day_sets_new_stamp_in_same_write(tmp_path) -> None:
    env = setup(tmp_path)
    new = Stamp(datetime(2026, 1, 1, 23, 0, tzinfo=CET), "Kurs")
    end = new.start
    assert book(env.writer, env.store, START, D1, end, [Part(D1, date(2026, 1, 1), 60)], new, D1) == ""
    env.settle()
    head = parse_bytes((env.root / D1).read_bytes())
    assert minutes(head)[0] == {"Orga": 70} and stamp_of(head) == new


def test_start_refuses_second_stamp_and_discard_checks_identity(tmp_path) -> None:
    env = setup(tmp_path)
    with pytest.raises(MeasurementError):
        start_measurement(env.writer, D1, START)
    with pytest.raises(MeasurementError):
        discard_stamp(env.writer, D1, Stamp(START.start, "Kurs"))
    discard_stamp(env.writer, D1, START)
    env.settle()
    assert stamp_of(parse_bytes((env.root / D1).read_bytes())) is None
    start_measurement(env.writer, D2, START)
    env.settle()
    assert stamp_of(parse_bytes((env.root / D2).read_bytes())) == START


# --- Umbenennen (S2/Y2) -------------------------------------------------------------------


def rename_setup(tmp_path, crash=None) -> tuple[Env, list[dict]]:
    env = Env(tmp_path, crash=crash)
    (env.root / D1).write_bytes(b"---\nzeit_Orga: 30\nzeit_Verwaltung: 5\n---\nA\n")
    (env.root / D2).write_bytes(b"---\nzeit_Orga: 20\nmessung_start: 2026-01-02T08:00:00+01:00\n"
                                b"messung_taetigkeit: Orga\n---\nB\n")
    files = [plan_rename_file(n, (env.root / n).read_bytes(), "Orga", "Verwaltung") for n in (D1, D2)]
    return env, files


def assert_renamed(env: Env) -> None:
    h1, h2 = parse_bytes((env.root / D1).read_bytes()), parse_bytes((env.root / D2).read_bytes())
    assert minutes(h1)[0] == {"Verwaltung": 35} and minutes(h2)[0] == {"Verwaltung": 20}
    assert stamp_of(h2).activity == "Verwaltung"


def test_rename_merges_and_renames_active_stamp(tmp_path) -> None:
    env, files = rename_setup(tmp_path)
    assert rename(env.writer, env.store, "Orga", "Verwaltung", True, files) == ""
    env.settle()
    assert_renamed(env)


def test_rename_crash_after_first_file_never_adds_twice(tmp_path) -> None:
    env, files = rename_setup(tmp_path, crash=("write:before_prepared", 2))
    with pytest.raises(SimulatedCrash):
        rename(env.writer, env.store, "Orga", "Verwaltung", True, files)
    env.die()
    fresh = Env(tmp_path)
    recover(fresh.writer)
    fresh.settle()
    recover_time_ops(fresh.writer, fresh.store)
    fresh.settle()
    assert_renamed(fresh)


def test_rename_skips_file_changed_since_planning(tmp_path) -> None:
    env, files = rename_setup(tmp_path)
    (env.root / D2).write_bytes(b"---\nzeit_Orga: 99\n---\nB\n")
    assert D2 in rename(env.writer, env.store, "Orga", "Verwaltung", True, files)
    env.settle()
    assert minutes(parse_bytes((env.root / D2).read_bytes()))[0] == {"Orga": 99}
    assert minutes(parse_bytes((env.root / D1).read_bytes()))[0] == {"Verwaltung": 35}
