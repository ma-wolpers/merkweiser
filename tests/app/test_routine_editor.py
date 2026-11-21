"""Tests für Formularmodell und Schreibwege des Routinen-Editors (W9 P6). Synthetisch, heute = Do, 15.01.2026."""

from datetime import date
from pathlib import Path

import pytest

from merkweiser.app import routine_service as rs
from merkweiser.app.notes_service import ReadOnlyVaultError
from merkweiser.app.routine_views import (RuleForm, due_today, find_rule, form_of, new_form, section_title,
                                          text_problems, upcoming)
from merkweiser.core.document import parse_document
from merkweiser.core.patch import Target
from merkweiser.core.rhythm import Kind, RhythmError
from merkweiser.core.routines import DEFAULT_TEXT, parse_routines
from tests.app.test_routine_service import make, read
from tests.core.test_routines import EXAMPLE

TODAY = date(2026, 1, 15)


def test_form_round_trip_for_every_section() -> None:
    """Formular aus jeder Regel der Beispieldatei ergibt wieder denselben Rhythmus, dieselben Optionen und Tags."""
    rf = parse_routines(parse_document(EXAMPLE.encode()))
    for section in rf.sections:
        form = form_of(section, section.items[0])
        assert (form.rhythm(), form.options(), form.tag_tuple()) == (section.rhythm, section.options, section.tags)
        assert form.line() == section.items[0].line.strip()


def test_form_validation_messages() -> None:
    """Fehlende Wochentage, ungültige Frist, fehlender Text → verständliche Fehler."""
    with pytest.raises(RhythmError, match="Wochentag"):
        RuleForm(body="x", kind=Kind.WOECHENTLICH).rhythm()
    with pytest.raises(RhythmError, match="Zahl"):
        RuleForm(body="x", frist="drei").options()
    with pytest.raises(ValueError, match="Text"):
        RuleForm(body=" ").line()
    with pytest.raises(RhythmError, match="Starttag"):
        RuleForm(kind=Kind.TAGE).rhythm()


def test_upcoming_and_due_today() -> None:
    """„Nächste: …“ mit Pausen; heute fällig nur aktiv und außerhalb von Pausen."""
    form = new_form(TODAY)  # täglich
    assert upcoming(form, None, TODAY) == "Nächste: Do 15.01., Fr 16.01., Sa 17.01."
    weekly = RuleForm(body="x", kind=Kind.WOECHENTLICH, weekdays=(0,))
    assert upcoming(weekly, None, TODAY) == "Nächste: Mo 19.01., Mo 26.01., Mo 02.02."
    assert not due_today(weekly, None, TODAY) and due_today(form, None, TODAY)
    paused = parse_routines(parse_document(b"## Pausen\n- 15.01.2026\n"))
    assert not due_today(form, paused, TODAY) and upcoming(form, paused, TODAY).startswith("Nächste: Fr 16.01.")
    assert upcoming(RuleForm(kind=Kind.WOECHENTLICH), None, TODAY).startswith("Wochentag fehlt")


def test_text_problems_find_rule_and_title() -> None:
    """Rohtext-Prüfung nennt Zeilen; ``find_rule`` findet die Regel auch nach verschobenen Zeilen."""
    assert text_problems(EXAMPLE) is None and text_problems(DEFAULT_TEXT) is None
    assert text_problems("## stündlich\n") == "Zeile 1: ## stündlich – Rhythmus „stündlich“ unbekannt (täglich, " \
        "werktags, wöchentlich …, alle …, monatlich …, jährlich …)"
    with pytest.raises(RhythmError, match="Abstand"):
        RuleForm(body="x", kind=Kind.TAGE, start=TODAY, interval="zwei").rhythm()
    with pytest.raises(RhythmError, match="mindestens"):
        RuleForm(body="x", frist="0").options()
    rf = parse_routines(parse_document(EXAMPLE.encode()))
    section, item = find_rule(rf, 999, "- [ ] Mails checken")
    assert item.body == "Mails checken" and section_title(rf.sections[1]) == "werktags #schule (Frist 2 Tage)"


def test_save_new_rule_creates_file_and_enters_today(tmp_path: Path) -> None:
    """Erste Regel legt Routinen.md mit Doku-Block an; „Heute schon eintragen“ schreibt die heutige Instanz."""
    service = make(tmp_path, {"2026-01-15.md": "Heute\n- [ ] a\n"})
    service.start()
    rs.save_rule(service, None, RuleForm(body="Mails", kind=Kind.TAEGLICH))
    assert read(service, "Routinen.md") == DEFAULT_TEXT + "\n## täglich\n- [ ] Mails\n"
    rs.run_due(service)  # setzt den Merkpunkt (heute) und trägt ein
    rs.save_rule(service, None, RuleForm(body="Lesen", kind=Kind.WERKTAGS), enter_today=True)
    assert read(service, "2026-01-15.md") == "Heute\n- [ ] a\n\ntäglich\n- [ ] Mails #wdh\n\nwerktags\n- [ ] Lesen #wdh\n"
    rs.save_rule(service, None, RuleForm(body="Später", kind=Kind.WERKTAGS))
    assert "Später" not in read(service, "2026-01-15.md")


def test_update_delete_and_pauses(tmp_path: Path) -> None:
    """Ändern (anderer Rhythmus → anderer Abschnitt), Löschen, Pausen hinzufügen und entfernen."""
    service = make(tmp_path, {"Routinen.md": "## täglich\n- [ ] Mails\n"})
    service.start()
    target = Target("Routinen.md", 4, "- [ ] Mails")  # nach dem Merkpunkt-Kopf (3 Zeilen)
    rs.save_rule(service, target, RuleForm(body="==Mails==", kind=Kind.WERKTAGS, frist="2"))
    assert read(service, "Routinen.md").endswith("---\n## werktags (Frist 2 Tage)\n- [ ] ==Mails==\n")
    rs.add_pause_range(service, date(2026, 12, 21), date(2027, 1, 4))
    assert read(service, "Routinen.md").endswith("\n## Pausen\n- 21.12.2026 bis 04.01.2027\n")
    rf = rs.load(service)
    rs.delete_pause(service, Target("Routinen.md", rf.pauses[0].line_no, rf.pauses[0].line))
    item = rs.load(service).sections[0].items[0]
    rs.delete_rule_at(service, Target("Routinen.md", item.line_no, item.line))
    assert rs.load(service).sections == ()


def test_editor_refuses_read_only(tmp_path: Path) -> None:
    """Schreibschutz: keine Editor-Aktion."""
    service = make(tmp_path, {})
    service.read_only = True
    with pytest.raises(ReadOnlyVaultError):
        rs.save_rule(service, None, RuleForm(body="x"))


def test_replace_text_keeps_style_or_creates_conflict(tmp_path: Path) -> None:
    """Rohtext: CRLF und BOM bleiben; geänderte Datei seit dem Öffnen → Konfliktdatei mit Sidecar, nichts überschrieben."""
    from merkweiser.core import conflict_files as cf
    original = b"\xef\xbb\xbf## t\xc3\xa4glich\r\n- [ ] Mails\r\n"
    service = make(tmp_path, {})
    (service.root / "Routinen.md").write_bytes(original)
    service.rescan()
    planned, text = rs.raw_text(service)
    assert planned == original and text == "## täglich\n- [ ] Mails\n"
    rs.replace_text(service, planned, "## werktags\n- [ ] Mails\n")
    assert (service.root / "Routinen.md").read_bytes() == b"\xef\xbb\xbf## werktags\r\n- [ ] Mails\r\n"
    stale, _text = rs.raw_text(service)
    (service.root / "Routinen.md").write_bytes(b"## t\xc3\xa4glich\n- [ ] extern\n")
    result = rs.replace_text(service, stale, "## werktags\n- [ ] meins\n")
    assert result.state == "CONFLICTED" and read(service, "Routinen.md") == "## täglich\n- [ ] extern\n"
    [conflict] = result.conflicts
    assert b"meins" in (service.root / conflict).read_bytes()
    assert cf.read_sidecar(service.data, conflict, cf.sha1((service.root / conflict).read_bytes())) is not None


def test_replace_text_creates_missing_file(tmp_path: Path) -> None:
    """Fehlt die Datei, ist der Editortext der Doku-Block; Speichern legt sie an."""
    service = make(tmp_path, {})
    planned, text = rs.raw_text(service)
    assert planned is None and text == DEFAULT_TEXT
    rs.replace_text(service, None, text + "\n## täglich\n- [ ] a")
    assert read(service, "Routinen.md") == DEFAULT_TEXT + "\n## täglich\n- [ ] a\n"
