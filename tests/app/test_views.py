"""Tests für die UI-neutralen Anzeigemodelle."""

from datetime import date
from pathlib import Path

import pytest

from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings
from merkweiser.app.conflict_views import Choice, conflict_result
from merkweiser.app.views import hit_rows, note_rows
from merkweiser.core.document import parse_document
from merkweiser.core.query import Filter
from tests.fakes import FakeClock


def test_note_rows_strip_markers_and_track_depth() -> None:
    """Zeilen ohne Marker/Checkbox, mit Tiefe, Status und effektiven Tags."""
    doc = parse_document(b"## Woche #w\nThema #t\n- [ ] ==eilig==\n  - Unterpunkt\n- [x] fertig\n")
    rows = note_rows("a.md", doc, doc.notes[0])
    assert [(r.kind, r.text, r.depth, r.done) for r in rows] == [
        ("heading", "Woche #w", 0, None), ("topic", "Thema #t", 1, None), ("todo", "==eilig==", 2, False),
        ("item", "Unterpunkt", 3, None), ("todo", "fertig", 2, True)]
    assert rows[2].urgent and rows[2].tags == ("t", "w") and rows[2].target.line_no == 2


def test_hit_rows_and_conflict_choices(tmp_path: Path) -> None:
    """Treffer-Zeilen mit Kontext; Konfliktentscheidungen liefern die richtigen Bytes."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-01.md").write_bytes(b"Uni #uni\n- [ ] Lernen\n")
    (root / "2026-01-01.sync-conflict-20260101-120000-AAAAAAA.sync-conflict-20260102-120000-BBBBBBB.md").write_bytes(
        b"Uni #uni\n- [ ] Lesen\n")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    [row] = hit_rows(svc.search(Filter(nur_todos=True)))
    assert (row.day, row.text, row.context, row.done) == ("2026-01-01", "Lernen", "Uni #uni", False)
    [case] = svc.conflicts()  # verschachtelt → manuell
    assert conflict_result(case, Choice.HAUPTDATEI) == case.main_bytes
    assert conflict_result(case, Choice.KONFLIKTVERSION) == case.conflict_bytes
    assert conflict_result(case, Choice.BEIDE) == b"Uni #uni\n- [ ] Lernen\n- [ ] Lesen\n"
    assert date(2026, 1, 1).isoformat() == row.day


def _case(main: bytes | None, other: bytes, device: str = "ABCDEFG"):
    """Synthetischer Konfliktfall nur mit den Feldern, die die Anzeigemodelle lesen."""
    from types import SimpleNamespace
    conflict = SimpleNamespace(stamp="20261021-140312", device=device, own=device.startswith("MERKWEISER"))
    return SimpleNamespace(main_bytes=main, conflict_bytes=other, conflict=conflict)


def test_conflict_diff_marks_sides_and_skips_long_equal_runs() -> None:
    from merkweiser.app.conflict_views import conflict_diff
    common = b"".join(b"Zeile %d\n" % i for i in range(10))
    rows = conflict_diff(_case(common + b"- [ ] Aufgabe\n", common + b"- [x] Aufgabe\n"))
    sides = [(r.side, r.text) for r in rows]
    assert sides[0] == ("ausgelassen", "… 9 gleiche Zeile(n) …")
    assert sides[1:] == [("beide", "Zeile 9"), ("haupt", "- [ ] Aufgabe"), ("konflikt", "- [x] Aufgabe")]


def test_conflict_diff_without_main_shows_only_conflict_lines() -> None:
    from merkweiser.app.conflict_views import conflict_diff
    assert [r.side for r in conflict_diff(_case(None, b"a\nb\n"))] == ["konflikt", "konflikt"]


def test_conflict_origin_names_source_and_time() -> None:
    from merkweiser.app.conflict_views import conflict_origin
    assert conflict_origin(_case(b"", b"")) == "von Syncthing-Gerät ABCDEFG, 21.10.2026 14:03"
    assert conflict_origin(_case(b"", b"", "MERKWEISERAB12CD34")).startswith("von Merkweiser selbst")


def test_note_ref_addresses_note_by_content_lines(tmp_path: Path) -> None:
    """NoteRef trägt Planungsstand und Inhaltszeilen; damit bearbeitet und löscht der Service genau diese Notiz."""
    from merkweiser.app.views import note_ref
    root = tmp_path / "vault"
    root.mkdir()
    raw = b"Erste #a\n- [ ] eins\n\n---\n\nZweite\n- [ ] zwei\n"
    (root / "2026-01-15.md").write_bytes(raw)
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    [day] = svc.day(date(2026, 1, 15))
    first, second = (note_ref(day.relpath, day.document, n) for n in day.document.notes)
    assert first.original == ("Erste #a", "- [ ] eins") and first.text == "Erste #a\n- [ ] eins"
    assert first.planned_raw == raw
    svc.replace_note_text(first.relpath, first.planned_raw, first.original, "Erste #a\n- [x] eins")
    svc.delete_note(second.relpath, second.original)
    assert (root / "2026-01-15.md").read_bytes() == b"Erste #a\n- [x] eins\n"


def test_note_ref_skips_empty_notes() -> None:
    """Leere Notizen (zwei Trenner hintereinander) haben nichts zu bearbeiten."""
    from merkweiser.app.views import note_ref
    doc = parse_document(b"a\n\n---\n\n---\n\nb\n")
    assert [note_ref("x.md", doc, n) is None for n in doc.notes] == [False, True, False]


@pytest.mark.parametrize("today, expected", [
    (date(2026, 10, 21), [date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 26), date(2026, 10, 28)]),  # Mi
    (date(2026, 10, 24), [date(2026, 10, 25), date(2026, 10, 26), date(2026, 11, 2), date(2026, 10, 31)]),  # Sa
    (date(2026, 10, 26), [date(2026, 10, 27), date(2026, 10, 28), date(2026, 11, 2)]),  # Mo: Montag = in einer Woche
])
def test_move_choices(today: date, expected: list[date]) -> None:
    """Schnellwahl: morgen, übermorgen, nächster Montag nach übermorgen, in einer Woche – ohne Dubletten."""
    from merkweiser.app.views import move_choices
    choices = move_choices(today)
    assert [day for _label, day in choices] == expected
    assert choices[0][0] == f"Morgen ({['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][expected[0].weekday()]}, {expected[0]:%d.%m.})"


def test_hunk_result_renders_like_main_and_names_decision() -> None:
    """Ergebnis übernimmt den Zeilenende-Stil der Hauptdatei; die Entscheidung ist lesbar."""
    from types import SimpleNamespace

    from merkweiser.app.conflict_views import hunk_result
    from merkweiser.core.conflicts import HunkPick
    from merkweiser.core.merge.diff3 import merge3
    merge = merge3(["T", "a", "Ende"], ["T", "a A", "Ende"], ["T", "a B", "Ende"])
    case = SimpleNamespace(merge=merge, main_bytes=b"T\r\na A\r\nEnde\r\n")
    result, decision = hunk_result(case, [(HunkPick.BEIDE, "")])
    assert result == b"T\r\na A\r\na B\r\nEnde\r\n" and decision == "Abschnitt 1: Beide"
    with pytest.raises(ValueError):
        hunk_result(SimpleNamespace(merge=None, main_bytes=b""), [])
