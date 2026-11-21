"""Tests für den Routinen-Durchlauf (W9, ``app/routine_service.py``): Eintragen, Nachholen, Ablauf, Merkpunkt.

Synthetischer Vault, ``FakeClock`` (heute = Do, 15.01.2026). Dateien werden
byte-genau geschrieben und gelesen (keine Zeilenend-Übersetzung).
"""

from pathlib import Path

from merkweiser.app import routine_service
from merkweiser.app.notes_service import NotesService
from merkweiser.app.routine_service import run_due
from merkweiser.app.settings import Settings
from tests.fakes import FakeClock

DAY = 86400
RULES = "## täglich\n- [ ] Mails\n\n## wöchentlich Do\n- [ ] Wochenplan\n"


def make(tmp_path: Path, files: dict[str, str], clock: FakeClock | None = None) -> NotesService:
    """Service auf einem synthetischen Vault (noch nicht gestartet)."""
    root = tmp_path / "vault"
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return NotesService(root, tmp_path / "app", Settings(vault=str(root)), clock or FakeClock())


def read(service: NotesService, name: str) -> str:
    """Dateiinhalt (oder ``""``, wenn es die Datei nicht gibt)."""
    path = service.root / name
    return path.read_bytes().decode("utf-8") if path.exists() else ""


def with_until(day: str, rules: str = RULES) -> str:
    """Routinen-Datei mit Merkpunkt."""
    return f"---\neingetragen_bis: {day}\n---\n{rules}"


def test_first_start_writes_only_today_and_sets_the_mark(tmp_path: Path) -> None:
    """Ohne Merkpunkt: nur heute, je Rhythmus eine Notiz; danach ``eingetragen_bis`` = heute."""
    service = make(tmp_path, {"Routinen.md": RULES})
    report = service.start()
    assert read(service, "2026-01-15.md") == "täglich\n- [ ] Mails #wdh\n\nwöchentlich Do\n- [ ] Wochenplan #wdh\n"
    assert read(service, "Routinen.md") == with_until("2026-01-15")
    assert report.routines.written == 2 and report.routines.problems == []
    assert not (service.root / "2026-01-14.md").exists()


def test_second_start_changes_nothing(tmp_path: Path) -> None:
    """Idempotent: erneuter Start schreibt nichts."""
    service = make(tmp_path, {"Routinen.md": RULES})
    service.start()
    before = (read(service, "2026-01-15.md"), read(service, "Routinen.md"))
    again = NotesService(service.root, tmp_path / "app", service.settings, FakeClock())
    report = again.start()
    assert (read(again, "2026-01-15.md"), read(again, "Routinen.md")) == before and report.routines.written == 0


def test_catch_up_writes_expired_as_missed_and_open_within_frist(tmp_path: Path) -> None:
    """Nachholen: abgelaufene Instanzen direkt ``[-]``, solche mit laufender Frist offen, heute offen."""
    rules = "## täglich\n- [ ] Mails\n\n## täglich (Frist 3 Tage)\n- [ ] Lesen\n"
    service = make(tmp_path, {"Routinen.md": with_until("2026-01-12", rules)})
    report = service.start()
    assert read(service, "2026-01-13.md") == "täglich\n- [-] Mails #wdh\n- [ ] Lesen #wdh\n"
    assert read(service, "2026-01-14.md") == "täglich\n- [-] Mails #wdh\n- [ ] Lesen #wdh\n"
    assert read(service, "2026-01-15.md") == "täglich\n- [ ] Mails #wdh\n- [ ] Lesen #wdh\n"
    assert (report.routines.missed, report.routines.written) == (2, 4)
    assert "eingetragen_bis: 2026-01-15" in read(service, "Routinen.md")


def test_early_check_then_day_arrives_without_duplicate(tmp_path: Path) -> None:
    """Vorzeitig abgehakt (schon in der Datei des Tages) → am Tag selbst kein Duplikat."""
    clock = FakeClock()
    service = make(tmp_path, {"Routinen.md": with_until("2026-01-15"), "2026-01-16.md": "täglich\n- [x] Mails #wdh\n"},
                   clock)
    service.start()
    clock.jump_wall(DAY)
    service.poll()
    assert read(service, "2026-01-16.md") == "täglich\n- [x] Mails #wdh\n"
    assert "eingetragen_bis: 2026-01-16" in read(service, "Routinen.md")


def test_deleted_instance_is_not_recreated(tmp_path: Path) -> None:
    """Gelöschte Instanz bleibt weg (Merkpunkt), auch bei weiteren Durchläufen."""
    service = make(tmp_path, {"Routinen.md": RULES})
    service.start()
    (service.root / "2026-01-15.md").write_bytes("wöchentlich Do\n- [ ] Wochenplan #wdh\n".encode())
    service.cache.forget("2026-01-15.md")
    assert run_due(service).written == 0
    assert read(service, "2026-01-15.md") == "wöchentlich Do\n- [ ] Wochenplan #wdh\n"


def test_crash_between_day_file_and_mark_does_not_duplicate(tmp_path: Path) -> None:
    """Instanz steht schon in der Tagesdatei, Merkpunkt fehlt (Abbruch dazwischen) → nichts doppelt."""
    service = make(tmp_path, {"Routinen.md": RULES, "2026-01-15.md": "täglich\n- [ ] Mails #wdh\n"})
    service.start()
    assert read(service, "2026-01-15.md") == "täglich\n- [ ] Mails #wdh\n\nwöchentlich Do\n- [ ] Wochenplan #wdh\n"


def test_midnight_poll_writes_new_day_and_expires_yesterday(tmp_path: Path) -> None:
    """App bleibt offen: nach Mitternacht trägt der Poll den neuen Tag ein und lässt gestern ablaufen."""
    clock = FakeClock()
    service = make(tmp_path, {"Routinen.md": RULES}, clock)
    service.start()
    clock.jump_wall(DAY)
    service.poll()
    assert read(service, "2026-01-16.md") == "täglich\n- [ ] Mails #wdh\n"
    assert read(service, "2026-01-15.md") == "täglich\n- [-] Mails #wdh\n\nwöchentlich Do\n- [ ] Wochenplan #wdh\n"
    assert service.routines.expired == 1 and service.routines.written == 1


def test_expiry_only_for_wdh_in_rhythm_topic(tmp_path: Path) -> None:
    """Abgelaufen wird nur ``#wdh`` unter einem Rhythmus-Thema; Erledigtes und Fremdes bleibt."""
    day = "täglich\n- [ ] a #wdh\n- [x] erledigt #wdh\n\nEinkauf\n- [ ] b #wdh\n\nwerktags\n- [ ] c\n"
    service = make(tmp_path, {"2026-01-14.md": day})
    service.start()
    assert read(service, "2026-01-14.md") == day.replace("- [ ] a #wdh", "- [-] a #wdh")


def test_read_only_writes_nothing(tmp_path: Path) -> None:
    """Schreibschutz: kein Durchlauf."""
    service = make(tmp_path, {"Routinen.md": RULES, "2026-01-14.md": "täglich\n- [ ] a #wdh\n"})
    service.read_only = True
    report = service.start()
    assert run_due(service).written == 0 and report.routines.written == 0
    assert read(service, "Routinen.md") == RULES and not (service.root / "2026-01-15.md").exists()


def test_ambiguous_day_file_stops_before_that_day(tmp_path: Path) -> None:
    """Zwei Dateien ohne kanonische für den 14.: 13. eingetragen, Merkpunkt = 13., Problem gemeldet."""
    service = make(tmp_path, {"Routinen.md": with_until("2026-01-12", "## täglich\n- [ ] Mails\n"),
                              "a/2026-01-14.md": "A\n", "b/2026-01-14.md": "B\n"})
    report = service.start()
    assert read(service, "2026-01-13.md") == "täglich\n- [-] Mails #wdh\n"
    assert "eingetragen_bis: 2026-01-13" in read(service, "Routinen.md")
    assert any("14.01.2026" in p for p in report.routines.problems) and not (service.root / "2026-01-15.md").exists()


def test_rules_changed_during_run_keep_the_mark(tmp_path: Path, monkeypatch) -> None:
    """Ändern sich die Regeln während des Eintragens, wird der Merkpunkt nicht fortgeschrieben."""
    service = make(tmp_path, {"Routinen.md": RULES})
    original = routine_service.plan_day

    def editing(doc, entries):
        (service.root / "Routinen.md").write_bytes((RULES + "\n## werktags\n- [ ] neu\n").encode())
        return original(doc, entries)

    monkeypatch.setattr(routine_service, "plan_day", editing)
    service.start()
    assert "eingetragen_bis" not in read(service, "Routinen.md")
    assert "- [ ] Mails #wdh" in read(service, "2026-01-15.md")


def test_unsafe_head_and_open_conflict_block_writing(tmp_path: Path) -> None:
    """Undurchsichtiger Kopf bzw. offener Konflikt auf Routinen.md → nichts eingetragen, Grund gemeldet."""
    opaque = make(tmp_path / "a", {"Routinen.md": "---\n# Kommentar\n---\n" + RULES})
    report = opaque.start()
    assert "Kopfbereich" in report.routines.summary and not (opaque.root / "2026-01-15.md").exists()
    clock = FakeClock()
    service = make(tmp_path / "b", {"Routinen.md": with_until("2026-01-15")}, clock)
    service.start()
    (service.root / "Routinen.sync-conflict-20260115-090000-ABCDEFG.md").write_bytes(b"## t\xc3\xa4glich\n- [ ] x\n")
    service.rescan()
    assert any(c.conflict.main_relpath == "Routinen.md" for c in service.conflicts())  # classify kennt den Fall
    clock.jump_wall(DAY)
    result = run_due(service)
    assert "offenen Konflikt" in result.summary and not (service.root / "2026-01-16.md").exists()


def test_catch_up_is_chunked(tmp_path: Path) -> None:
    """Lange Pause: höchstens 31 Tage je Durchlauf, der nächste macht weiter."""
    service = make(tmp_path, {"Routinen.md": with_until("2025-11-01", "## täglich\n- [ ] x\n")})
    service.start()
    assert "eingetragen_bis: 2025-12-02" in read(service, "Routinen.md")
    run_due(service)
    assert "eingetragen_bis: 2026-01-02" in read(service, "Routinen.md")
    run_due(service)
    assert "eingetragen_bis: 2026-01-15" in read(service, "Routinen.md")
    assert read(service, "2026-01-15.md") == "täglich\n- [ ] x #wdh\n"


def test_no_routines_file_no_problem(tmp_path: Path) -> None:
    """Ohne Routinen.md passiert nichts und es gibt keine Meldung."""
    service = make(tmp_path, {"2026-01-15.md": "Heute\n- [ ] a\n"})
    assert service.start().routines.summary == ""
