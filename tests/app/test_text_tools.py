"""Tests für die Einfüge-Werkzeuge der Editoren (Bereich, Umwandlungen, Auswahl, UTF-16)."""

import pytest

from merkweiser.app.text_tools import index_to_utf16, indent, insert_tag, toggle_todo, utf16_to_index


def test_unknown_position_does_nothing() -> None:
    """Unbekannte Cursorposition → nichts verändern (kein Ausweichen aufs Textende)."""
    for tool in (toggle_todo, insert_tag):
        assert tool("a\nb", None, None) == ("a\nb", None, None)
    assert indent("a", None, None, 1) == ("a", None, None)


def test_toggle_todo_at_caret_keeps_indentation_and_selection() -> None:
    """Caret: nur die Caret-Zeile; ``x`` → ``- [ ] x``, eingerückt bleibt eingerückt; Caret wandert mit."""
    assert toggle_todo("a\n\tb\nc", 4, 4) == ("a\n\t- [ ] b\nc", 10, 10)
    assert toggle_todo("- x", 3, 3) == ("- [ ] x", 7, 7)
    assert toggle_todo("1. x", 0, 0) == ("1. [ ] x", 0, 0)
    assert toggle_todo("-", 1, 1) == ("- [ ] ", 6, 6)


def test_toggle_todo_back_counts_done_todos_and_drops_the_marker() -> None:
    """Rückumschalten von offenen und abgehakten Todos ergibt ``x`` (Marker kommt nicht zurück)."""
    assert toggle_todo("  - [x] fertig", 14, 14) == ("  fertig", 8, 8)
    assert toggle_todo("- [ ] a\n- [X] b", 0, 15) == ("a\nb", 0, 3)


def test_toggle_todo_mixed_selection_and_blank_lines() -> None:
    """Gemischt → alle werden Todos; Leerzeilen im Bereich bleiben leer (Notizgrenze); ``[-]`` bleibt."""
    text = "- [ ] a\n\nb\n- [-] c"
    new, start, end = toggle_todo(text, 0, len(text))
    assert new == "- [ ] a\n\n- [ ] b\n- [-] c" and (start, end) == (0, len(new))


def test_selection_ending_at_line_start_excludes_that_line() -> None:
    """Endet die Auswahl genau am Zeilenanfang, zählt diese Zeile nicht; die Auswahl umfasst danach dieselben
    Zeichen (``a\\n``), ein zweiter Tipp schaltet also dieselbe Zeile zurück."""
    new, start, end = toggle_todo("a\nb", 0, 2)
    assert (new, start, end) == ("- [ ] a\nb", 6, 8)
    assert toggle_todo(new, start, end) == ("a\nb", 0, 2)


def test_indent_and_outdent() -> None:
    """Einrücken mit Tab; Ausrücken entfernt einen Tab oder bis zu vier Leerzeichen; Leerzeilen bleiben."""
    assert indent("a\n\nb", 0, 4, 1) == ("\ta\n\n\tb", 1, 6)
    assert indent("\ta\n      b", 0, 10, -1) == ("a\n  b", 0, 5)
    assert indent("a", 1, 1, -1) == ("a", 1, 1)


def test_insert_tag_at_word_start_or_line_end() -> None:
    """Auswahl → ``#`` vor das Wort (Auswahl verschiebt sich); Caret → ``#`` ans Zeilenende."""
    assert insert_tag("Kisten packen", 9, 13) == ("Kisten #packen", 10, 14)
    assert insert_tag("Kisten packen", 3, 3) == ("Kisten packen #", 15, 15)
    assert insert_tag("a \nb", 0, 0) == ("a #\nb", 3, 3)
    assert insert_tag("#da", 1, 3) == ("#da", 1, 3)


@pytest.mark.parametrize("text", ["ä x", "😀 x", "a😀b😀 x"])
def test_utf16_roundtrip_with_non_ascii_before_the_caret(text: str) -> None:
    """Umrechnung UTF-16 ↔ Index: ``ä`` zählt 1, Emoji zählen 2 UTF-16-Einheiten."""
    caret = text.index("x")
    units = index_to_utf16(text, caret)
    assert utf16_to_index(text, units) == caret
    assert units == caret + text.count("😀")
    new, start, _end = insert_tag(text, caret, caret)
    assert new == text + " #" and start == len(new)
