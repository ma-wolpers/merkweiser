"""Tests für die Zeilen-Edits auf ``Routinen.md`` (W9, ``core/routine_edit.py``): byte-genau, nur betroffene Zeilen."""

from datetime import date

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.patch import StaleTargetError, Target
from merkweiser.core.rhythm import Options, parse_rhythm
from merkweiser.core.routine_edit import (add_pause, add_rule, delete_line, delete_rule, heading_line, new_file,
                                          replace_all, rule_line, update_rule)
from merkweiser.core.routines import DEFAULT_TEXT, parse_routines

BASE = "---\neingetragen_bis: 2026-11-17\n---\n# Routinen\nDoku\n\n## Wöchentlich mo\n- [ ] Plan\n\n## Pausen\n- 01.01.2027\n"
MO, DAILY = parse_rhythm("wöchentlich Mo"), parse_rhythm("täglich")


def doc(text: str, crlf: bool = False):
    """Dokument aus synthetischem Text."""
    return parse_document((text.replace("\n", "\r\n") if crlf else text).encode())


def tgt(line_no: int, text: str) -> Target:
    """Ziel in ``Routinen.md``."""
    return Target("Routinen.md", line_no, text)


def test_heading_and_rule_line() -> None:
    """Kanonische Überschrift mit Tags vor den Optionen; aktive und pausierte Regel."""
    assert heading_line(MO, Options(3, True), ("schule",)) == "## wöchentlich Mo #schule (Frist 3 Tage, auch in Pausen)"
    assert rule_line(" a ") == "- [ ] a" and rule_line("a", active=False) == "- [x] a"


def test_add_to_matching_section_by_meaning_keeps_crlf() -> None:
    """Gleicher Rhythmus trotz anderer Schreibweise → ans Abschnittsende; CRLF bleibt."""
    after = add_rule(doc(BASE, crlf=True), MO, Options(), (), "- [ ] Kopien")
    assert after == BASE.replace("- [ ] Plan\n", "- [ ] Plan\n- [ ] Kopien\n").replace("\n", "\r\n").encode()


def test_new_section_before_pauses_or_at_end_or_new_file() -> None:
    """Neuer Abschnitt vor ``## Pausen``; ohne Pausen am Ende; leere Datei bekommt den Doku-Block."""
    after = add_rule(doc(BASE), DAILY, Options(1), ("a",), "- [ ] Mails").decode()
    assert after.endswith("- [ ] Plan\n\n## täglich #a (Frist 1 Tag)\n- [ ] Mails\n\n## Pausen\n- 01.01.2027\n")
    assert add_rule(doc("## täglich\n- [ ] x"), MO, Options(), (), "- [ ] y").decode() == \
        "## täglich\n- [ ] x\n\n## wöchentlich Mo\n- [ ] y\n"
    fresh = add_rule(doc(""), DAILY, Options(), (), "- [ ] Mails").decode()
    assert fresh.startswith(DEFAULT_TEXT) and fresh.endswith("\n## täglich\n- [ ] Mails\n")
    assert [s.topic for s in parse_routines(parse_document(fresh.encode())).sections] == ["täglich"]


def test_update_in_place_or_move_and_drop_empty_section() -> None:
    """Gleicher Abschnitt → nur die Zeile; anderer Rhythmus → umziehen, leerer Abschnitt weg."""
    same = update_rule(doc(BASE), tgt(7, "- [ ] Plan"), MO, Options(), (), "- [x] ==Plan==")
    assert same == BASE.replace("- [ ] Plan", "- [x] ==Plan==").encode()
    moved = update_rule(doc(BASE), tgt(7, "- [ ] Plan"), DAILY, Options(), (), "- [ ] Plan").decode()
    assert "Wöchentlich" not in moved and "## täglich\n- [ ] Plan\n\n## Pausen" in moved
    assert moved.startswith("---\neingetragen_bis: 2026-11-17\n---\n# Routinen\nDoku\n\n## täglich")


def test_delete_rule_keeps_section_with_other_rules() -> None:
    """Weitere Regeln im Abschnitt → nur die Zeile; veraltetes Ziel → ``StaleTargetError``."""
    two = BASE.replace("- [ ] Plan\n", "- [ ] Plan\n- [ ] Kopien\n")
    assert delete_rule(doc(two), tgt(8, "- [ ] Kopien")) == BASE.encode()
    with pytest.raises(StaleTargetError):
        delete_rule(doc(BASE), tgt(7, "- [ ] anders"))


def test_pauses_add_create_and_delete() -> None:
    """Pause ans Ende der Liste; ``## Pausen`` entsteht bei Bedarf; Zeile löschen; Ende vor Beginn abgelehnt."""
    added = add_pause(doc(BASE), date(2027, 3, 29), date(2027, 4, 10))
    assert added.decode().endswith("## Pausen\n- 01.01.2027\n- 29.03.2027 bis 10.04.2027\n")
    created = add_pause(doc("## täglich\n- [ ] x\n"), date(2027, 1, 6), date(2027, 1, 6))
    assert created.decode() == "## täglich\n- [ ] x\n\n## Pausen\n- 06.01.2027\n"
    assert delete_line(doc(BASE), tgt(10, "- 01.01.2027")).decode().endswith("## Pausen\n")
    with pytest.raises(ValueError):
        add_pause(doc(BASE), date(2027, 2, 2), date(2027, 2, 1))


def test_replace_all_keeps_style() -> None:
    """Rohtext ersetzen: CRLF der Datei bleibt; ``new_file`` ist der Doku-Block."""
    assert replace_all(doc("a\nb\n", crlf=True), "x\ny\n") == b"x\r\ny\r\n"
    assert new_file() == DEFAULT_TEXT.encode()
