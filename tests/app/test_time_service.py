"""Tests für den Zeit-Tracker in der App-Schicht (W6, 1.7/R1, S2/Y8)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from merkweiser.app import time_service as ts
from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings
from merkweiser.app.time_scan import refresh
from merkweiser.app.time_state import load_state
from merkweiser.core.conflicts import CaseKind
from merkweiser.core.frontmatter import minutes, parse_bytes, stamp_of
from merkweiser.core.time_ops import MeasurementError
from tests.fakes import FakeClock

CET = timezone(timedelta(hours=1))
TODAY = "2026-01-15.md"  # FakeClock: 2026-01-15 10:00 +01:00


def service(tmp_path: Path, files: dict[str, bytes] | None = None) -> NotesService:
    root = tmp_path / "vault"
    root.mkdir()
    for name, data in (files or {}).items():
        (root / name).write_bytes(data)
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    return svc


def later(svc: NotesService, minutes_: float) -> None:
    svc.clock.advance(minutes_ * 60)
    svc.writer.finish_due()


def head(svc: NotesService, name: str = TODAY):
    return parse_bytes((svc.root / name).read_bytes())


def test_start_stop_books_floored_minutes_and_creates_file(tmp_path: Path) -> None:
    svc = service(tmp_path)
    assert "läuft seit 10:00" in ts.start(svc, "Orga")
    with pytest.raises(MeasurementError):
        ts.start(svc, "Kurs")
    later(svc, 90.5)
    assert "1:30 eingetragen" in ts.stop(svc)
    later(svc, 1)
    assert minutes(head(svc))[0] == {"Orga": 90} and stamp_of(head(svc)) is None
    with pytest.raises(MeasurementError):
        ts.stop(svc)


def test_switch_and_abort_variants(tmp_path: Path) -> None:
    svc = service(tmp_path)
    ts.start(svc, "Orga")
    later(svc, 30)
    ts.switch(svc, "Kurs")
    later(svc, 1)
    assert minutes(head(svc))[0] == {"Orga": 30} and stamp_of(head(svc)).activity == "Kurs"
    later(svc, 20)
    ts.abort(svc, None)  # „Keine Zeit eintragen“
    later(svc, 1)
    assert minutes(head(svc))[0] == {"Orga": 30} and stamp_of(head(svc)) is None
    ts.start(svc, "Kurs")
    begun = svc.clock.now()
    later(svc, 60)
    with pytest.raises(MeasurementError):
        ts.abort(svc, begun - timedelta(minutes=1))
    ts.abort(svc, begun + timedelta(minutes=15))
    later(svc, 1)
    assert minutes(head(svc))[0] == {"Orga": 30, "Kurs": 15}
    assert "Kurs" in load_state(svc.data).activities


def stamp_file(start: str, activity: str = "Orga") -> bytes:
    return f"---\nmessung_start: {start}\nmessung_taetigkeit: {activity}\n---\nX\n".encode()


def test_stale_stamps_are_cleaned_only_where_scanned(tmp_path: Path) -> None:
    """R1: im 7-Tage-Fenster bereinigt (mit Hinweis), älter nur bei der Archivsuche; nie verbucht."""
    svc = service(tmp_path, {"2026-01-13.md": stamp_file("2026-01-13T08:15:00+01:00"),
                             "2026-01-02.md": stamp_file("2026-01-02T08:15:00+01:00", "Kurs")})
    scan = refresh(svc)
    assert scan.running == [] and any("Di 13.01. 08:15" in h and "verworfen" in h for h in scan.hints)
    later(svc, 1)
    assert stamp_of(head(svc, "2026-01-13.md")) is None and minutes(head(svc, "2026-01-13.md"))[0] == {}
    assert stamp_of(head(svc, "2026-01-02.md")) is not None  # außerhalb des Fensters: nicht geprüft
    archive = refresh(svc, archive=True)
    assert any("Kurs" in h for h in archive.hints)
    later(svc, 1)
    assert stamp_of(head(svc, "2026-01-02.md")) is None


def test_overview_days_totals_and_order(tmp_path: Path) -> None:
    svc = service(tmp_path, {"2026-01-15.md": b"---\nzeit_Orga: 30\nzeit_Kurs: 45\n---\nX\n",
                             "2026-01-10.md": b"---\nzeit_Orga: 30\nzeit_Alt Name: 5\n---\nX\n",
                             "2026-01-01.md": b"---\nzeit_Fern: 500\n---\nX\n"})
    scan = refresh(svc)
    assert len(scan.days) == 7 and scan.days[0].day.isoformat() == "2026-01-15"
    assert scan.days[0].minutes == {"Orga": 30, "Kurs": 45}
    assert ts.activity_names(svc, scan) == ["Orga", "Kurs", "Alt Name"]


def test_two_running_stamps_offer_the_three_options(tmp_path: Path) -> None:
    svc = service(tmp_path, {"2026-01-14.md": stamp_file("2026-01-14T20:00:00+01:00"),
                             TODAY: stamp_file("2026-01-15T08:00:00+01:00", "Kurs")})
    conflict = ts.running_conflict(refresh(svc))
    assert [c for c, _ in conflict.options()] == ["spaeter", "frueher_endet"]
    with pytest.raises(MeasurementError):
        ts.stop(svc)
    ts.resolve_running(svc, "frueher_endet")
    later(svc, 1)
    assert minutes(head(svc, "2026-01-14.md"))[0] == {"Orga": 240}  # 20:00–24:00
    assert minutes(head(svc))[0] == {"Orga": 480} and stamp_of(head(svc)).activity == "Kurs"


def test_rename_needs_confirmation_to_merge_and_records_the_log(tmp_path: Path) -> None:
    svc = service(tmp_path, {"2026-01-14.md": b"---\nzeit_Orga: 30\nzeit_Verwaltung: 5\n---\nX\n"})
    ts.add_activity(svc, "Verwaltung")
    with pytest.raises(ts.NeedsConfirmation):
        ts.rename_activity(svc, "Orga", "verwaltung")
    ts.rename_activity(svc, "Orga", "Verwaltung", merge=True)
    later(svc, 1)
    assert minutes(head(svc, "2026-01-14.md"))[0] == {"Verwaltung": 35}
    state = load_state(svc.data)
    assert state.rename_pairs() == (("Orga", "Verwaltung"),) and "Orga" not in state.activities


def test_old_key_reappearing_after_rename_is_migrated_or_unclear(tmp_path: Path) -> None:
    """Y8: per Sync wieder aufgetaucht – allein → migriert; zusammen mit dem neuen → „unklar“, keine Rechnung."""
    svc = service(tmp_path, {"2026-01-14.md": b"---\nzeit_Orga: 30\n---\nX\n"})
    ts.rename_activity(svc, "Orga", "Verwaltung")
    later(svc, 1)
    (svc.root / "2026-01-13.md").write_bytes(b"---\nzeit_Orga: 20\n---\nY\n")
    (svc.root / "2026-01-12.md").write_bytes(b"---\nzeit_Orga: 10\nzeit_Verwaltung: 10\n---\nZ\n")
    svc.rescan()
    scan = refresh(svc)
    later(svc, 1)
    assert minutes(head(svc, "2026-01-13.md"))[0] == {"Verwaltung": 20}
    assert [(r, o, n) for r, _d, o, n in scan.unclear] == [("2026-01-12.md", "Orga", "Verwaltung")]
    assert minutes(head(svc, "2026-01-12.md"))[0] == {"Orga": 10, "Verwaltung": 10}
    ts.resolve_unclear(svc, "2026-01-12.md", "Orga", "Verwaltung", "groesser")
    later(svc, 1)
    assert minutes(head(svc, "2026-01-12.md"))[0] == {"Verwaltung": 10}


def test_sync_conflict_uses_the_rename_log(tmp_path: Path) -> None:
    """Nach lokaler Umbenennung: Konfliktdatei mit altem Schlüssel wird normalisiert, dann Maximum (AUTO)."""
    svc = service(tmp_path, {TODAY: b"---\nzeit_Orga: 90\n---\nX\n"})
    ts.rename_activity(svc, "Orga", "Verwaltung")
    later(svc, 1)
    (svc.root / "2026-01-15.sync-conflict-20260115-120000-AAAAAAA.md").write_bytes(b"---\nzeit_Orga: 120\n---\nX\n")
    svc.rescan()
    [case] = svc.conflicts()
    assert case.kind is CaseKind.AUTO and case.frontmatter.resolve() == ("---", "zeit_Verwaltung: 120", "---")


def test_delete_keeps_times_but_not_while_running(tmp_path: Path) -> None:
    svc = service(tmp_path)
    ts.start(svc, "Orga")
    with pytest.raises(MeasurementError):
        ts.delete_activity(svc, "orga")
    later(svc, 10)
    ts.stop(svc)
    later(svc, 1)
    ts.delete_activity(svc, "Orga")
    assert "Orga" not in load_state(svc.data).activities and minutes(head(svc))[0] == {"Orga": 10}
    with pytest.raises(ValueError):
        ts.add_activity(svc, "a:b")
