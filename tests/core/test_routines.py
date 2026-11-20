"""Tests für Parser, Instanzen und Ablauf der Routinen-Datei (W9, ``core/routines.py``). Nur synthetische Daten."""

from datetime import date

from merkweiser.core.document import parse_document
from merkweiser.core.inline import TodoStatus
from merkweiser.core.rhythm import Options
from merkweiser.core.routines import (DEFAULT_TEXT, expires_on, expiry_for, instance_key, instance_line, occurrences,
                                      parse_routines)

EXAMPLE = """---
eingetragen_bis: 2026-11-17
tags: [privat]
---
# Routinen
Doku-Text wird ignoriert.
- [ ] auch diese Liste im Doku-Block

```
## täglich
- [ ] Beispiel im Codeblock
```

## täglich
- [ ] Mails checken

## werktags #schule (Frist 2 Tage)
- [ ] Vertretungsplan prüfen
- [x] pausierte Regel

## wöchentlich Mo (Frist 3 Tage)
- [ ] ==Wochenplan schreiben==

## alle 3 Tage ab 17.11.2026 (auch in Pausen)
- [ ] Pflanzen gießen

## monatlich 1., 31.
- [ ] ==🔴Noten eintragen== #schule

## jährlich 15.09.
- [ ] Versicherung prüfen

## Pausen
- 21.12.2026 bis 04.01.2027
- 06.04.2027
"""


def parse(text: str, crlf: bool = False, bom: bool = False):
    """Parst synthetischen Text als Routinen-Datei."""
    raw = text.replace("\n", "\r\n") if crlf else text
    return parse_routines(parse_document((b"\xef\xbb\xbf" if bom else b"") + raw.encode("utf-8")))


def test_example_sections_pauses_and_until() -> None:
    """Beispieldatei: Doku-Block und Codeblock ignoriert, Abschnitte, Tags, Optionen, Pausen, Merkpunkt."""
    rf = parse(EXAMPLE)
    assert rf.errors == () and rf.until == date(2026, 11, 17) and rf.head_writable
    assert [s.topic for s in rf.sections] == [
        "täglich", "werktags", "wöchentlich Mo", "alle 3 Tage ab 17.11.2026", "monatlich 1., 31.", "jährlich 15.09."]
    werktags = rf.sections[1]
    assert werktags.tags == ("schule",) and werktags.options == Options(2, False)
    assert [(i.body, i.paused) for i in werktags.items] == [("Vertretungsplan prüfen", False), ("pausierte Regel", True)]
    assert [(p.start, p.end) for p in rf.pauses] == [(date(2026, 12, 21), date(2027, 1, 4)),
                                                     (date(2027, 4, 6), date(2027, 4, 6))]
    assert rf.in_pause(date(2027, 1, 1)) and not rf.in_pause(date(2027, 1, 5))


def test_crlf_and_bom_read_the_same() -> None:
    """CRLF und BOM ändern nichts am Ergebnis (außer Zeilenenden in den Rohzeilen)."""
    plain, other = parse(EXAMPLE), parse(EXAMPLE, crlf=True, bom=True)
    assert [s.topic for s in other.sections] == [s.topic for s in plain.sections]
    assert other.until == plain.until and other.errors == ()


def test_errors_are_collected_not_raised() -> None:
    """Jede Fehlerart wird mit Zeile gemeldet; gültige Abschnitte bleiben gültig."""
    rf = parse("## täglich\n- [ ] gut\nFreitext\n  - [ ] eingerückt\n- [-] verpasst?\n- [ ]   \n- ohne Box\n"
               "## stündlich\n- [ ] wird übersprungen\n## Pausen\n- 05.01.2027 bis 01.01.2027\n- morgen\n"
               "## Pausen\n")
    assert [i.body for s in rf.sections for i in s.items] == ["gut"]
    messages = [(e.line, e.message) for e in rf.errors]
    assert [line for line, _m in messages] == ["Freitext", "  - [ ] eingerückt", "- [-] verpasst?", "- [ ]   ",
                                               "- ohne Box", "## stündlich", "- 05.01.2027 bis 01.01.2027",
                                               "- morgen", "## Pausen"]
    assert "unbekannt" in messages[5][1] and "vor ihrem Beginn" in messages[6][1]


def test_until_states() -> None:
    """Merkpunkt fehlt, ungültig, undurchsichtiger Kopf (nicht beschreibbar)."""
    assert parse("## täglich\n- [ ] a\n").until is None
    bad = parse("---\neingetragen_bis: gestern\n---\n## täglich\n- [ ] a\n")
    assert bad.until is None and "kein Datum" in bad.until_error
    opaque = parse("---\n# Kommentar\neingetragen_bis: 2026-11-17\n---\n## täglich\n- [ ] a\n")
    assert not opaque.head_writable and [s.topic for s in opaque.sections] == ["täglich"]


def test_default_text_has_no_rules() -> None:
    """Der Standard-Doku-Block erzeugt keine Abschnitte und keine Fehler."""
    rf = parse(DEFAULT_TEXT)
    assert rf.sections == () and rf.errors == () and rf.pauses == ()


def test_occurrences_respect_pauses_paused_rules_and_inherit_tags() -> None:
    """Pausierte Regeln fehlen; in Pausen nur ``auch in Pausen``; Tags der Überschrift vererbt."""
    rf = parse(EXAMPLE)
    monday = occurrences(rf, date(2026, 11, 23))
    assert [(o.topic, o.body) for o in monday] == [
        ("täglich", "Mails checken"), ("werktags", "Vertretungsplan prüfen"),
        ("wöchentlich Mo", "==Wochenplan schreiben=="), ("alle 3 Tage ab 17.11.2026", "Pflanzen gießen")]
    assert monday[1].line(TodoStatus.OPEN) == "- [ ] Vertretungsplan prüfen #schule #wdh"
    in_pause = occurrences(rf, date(2026, 12, 23))  # alle 3 Tage ab 17.11.: 23.12. fällig
    assert [o.body for o in in_pause] == ["Pflanzen gießen"]
    end_of_month = occurrences(rf, date(2026, 11, 30))
    assert "==🔴Noten eintragen== #schule" in [o.body for o in end_of_month]


def test_expiry_default_frist_and_pause_skip() -> None:
    """Ohne Frist: nächste Instanz (Pausen übersprungen); mit Frist: Tag + N."""
    rf = parse(EXAMPLE)
    by_body = {o.body: o for o in occurrences(rf, date(2026, 11, 23))}
    assert by_body["Mails checken"].expires == date(2026, 11, 24)
    assert by_body["Vertretungsplan prüfen"].expires == date(2026, 11, 25)
    assert by_body["==Wochenplan schreiben=="].expires == date(2026, 11, 26)
    sunday = {o.body: o for o in occurrences(rf, date(2026, 12, 20))}  # letzter Tag vor der Pause
    assert sunday["Mails checken"].expires == date(2027, 1, 5)  # über die Ferien offen
    assert expires_on(rf.sections[5].rhythm, Options(), lambda _d: False, date(2026, 9, 15)) == date(2027, 9, 15)


def test_expiry_for_existing_instances() -> None:
    """Ablauf aus dem Notiz-Thema: Optionen der passenden Regel, sonst Standard; unlesbares Thema → nie."""
    rf = parse(EXAMPLE)
    assert expiry_for(rf, "werktags", "Vertretungsplan prüfen #schule #wdh", date(2026, 11, 23)) == date(2026, 11, 25)
    assert expiry_for(None, "werktags", "x #wdh", date(2026, 11, 20)) == date(2026, 11, 23)
    assert expiry_for(rf, "Elternabend", "x #wdh", date(2026, 11, 20)) is None
    assert expiry_for(rf, "täglich #wdh", "x", date(2026, 11, 20)) == date(2026, 11, 21)  # Tags im Thema egal


def test_instance_line_and_key() -> None:
    """Instanzzeile hängt fehlende Tags an (nie doppelt); Schlüssel ignoriert Ampel, Tags, Leerraum, Schreibung."""
    assert instance_line("a #wdh", ("schule",), TodoStatus.MISSED) == "- [-] a #wdh #schule"
    assert instance_line("==🔴b== #Schule", ("schule",), TodoStatus.DONE) == "- [x] ==🔴b== #Schule #wdh"
    assert instance_key("==🔴Noten  eintragen== #schule #wdh") == instance_key("noten eintragen") == "noten eintragen"


def test_same_rules_ignores_until_and_line_numbers() -> None:
    """Gleiche Regeln trotz anderem Merkpunkt und verschobener Zeilen; geänderte Regel → verschieden."""
    base = parse(EXAMPLE)
    assert base.same_rules(parse(EXAMPLE.replace("2026-11-17", "2026-11-20").replace("# Routinen", "# R\n\nmehr")))
    assert not base.same_rules(parse(EXAMPLE.replace("Mails checken", "Mails lesen")))
