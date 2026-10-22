"""Tests für das strukturbewusste Einrücken und das Fortsetzen von Listen mit Enter."""

import pytest

from merkweiser.app.list_editing import continue_list, shift_item


def caret(text: str, marker: str = "|") -> tuple[str, int]:
    """Hilfsfunktion: Text mit ``|`` als Caret → (Text ohne ``|``, Position)."""
    return text.replace(marker, ""), text.index(marker)


def shifted(text: str, delta: int, width: int = 4) -> str:
    """Hilfsfunktion: ``shift_item`` an der ``|``-Position, nur der neue Text."""
    plain, at = caret(text)
    return shift_item(plain, at, at, delta, width)[0]


def test_unknown_position_and_non_items_do_nothing() -> None:
    """Ohne Position, auf Thema/Text oder Leerzeile passiert nichts."""
    assert shift_item("- a\n- b", None, None, 1) == ("- a\n- b", None, None)
    assert shifted("Th|ema\n- a\n- b", 1) == "Thema\n- a\n- b"
    assert shifted("- a\n|\n- b", 1) == "- a\n\n- b"


def test_indent_is_limited_to_previous_item_plus_one() -> None:
    """Ohne Punkt darüber: kein Einrücken; sonst höchstens eine Ebene tiefer als der vorige Punkt."""
    assert shifted("T\n- |a", 1) == "T\n- a"
    assert shifted("- a\n- |b", 1) == "- a\n    - b"
    assert shifted("- a\n    - |b", 1) == "- a\n    - b"  # schon eine Ebene tiefer
    assert shifted("- a\n- |b", 1, width=2) == "- a\n  - b"
    assert shifted("- a\n\n- |b", 1) == "- a\n\n- b"  # vorige Notiz zählt nicht


def test_only_the_first_line_moves_and_continuations_find_their_item() -> None:
    """Caret in der Fortsetzung → der Punkt wird verschoben; die Fortsetzung selbst bleibt."""
    assert shifted("- [ ] a\n- [ ] b\nweit|er", 1) == "- [ ] a\n    - [ ] b\nweiter"


def test_subtree_moves_in_both_directions() -> None:
    """Einrücken und Ausrücken nehmen alle Unterpunkte mit, Fortsetzungen bleiben; Geschwister nicht."""
    text = "- a\n- |b\n    - b1\n        - b2\n    mehr\n- c"
    assert shifted(text, 1) == "- a\n    - b\n        - b1\n            - b2\n    mehr\n- c"
    out = "- a\n    - |b\n        - b1\n- c"
    assert shifted(out, -1) == "- a\n- b\n    - b1\n- c"
    assert shifted("- |a", -1) == "- a"  # Ebene 0 bleibt


def test_outdent_removes_a_tab_or_up_to_width_spaces() -> None:
    """Ausrücken entfernt einen Tab bzw. bis zu ``width`` Leerzeichen am Ende des Leerraums."""
    assert shifted("- a\n\t- |b", -1) == "- a\n- b"
    assert shifted("- a\n      - |b", -1, width=4) == "- a\n  - b"
    assert shifted("- a\n  - |b", -1, width=2) == "- a\n- b"


def test_selection_moves_each_item_once() -> None:
    """Auswahl über Eltern und Kind: das Kind wandert nur einmal (mit dem Elternpunkt)."""
    text = "- a\n- b\n    - b1"
    new, start, end = shift_item(text, 5, len(text), 1)
    assert new == "- a\n    - b\n        - b1" and (start, end) == (9, len(new))


@pytest.mark.parametrize("before, after", [
    ("- a|", "- a\n- |"),
    ("  - [x] a|\nb", "  - [x] a\n  - [ ] |\nb"),
    ("- ab|cd", "- ab\n- |cd"),
    ("9. a|", "9. a\n10. |"),
])
def test_enter_in_an_item_with_content_starts_a_new_item(before: str, after: str) -> None:
    """Enter in einem Punkt mit Inhalt → neuer leerer Punkt gleicher Art und Einrückung (Todos offen)."""
    old, at = caret(before)
    expected, expected_caret = caret(after)
    assert continue_list(old, old[:at] + "\n" + old[at:], at) == (expected, expected_caret)


def test_enter_in_an_empty_item_turns_it_into_text() -> None:
    """Enter in einem leeren Punkt/Todo → Marker weg, Zeile wird (leerer) Text, kein Zeilenumbruch."""
    old = "- a\n    - [ ] \nb"
    at = old.index("\nb")
    assert continue_list(old, old[:at] + "\n" + old[at:], at) == ("- a\n\nb", 4)


def test_enter_elsewhere_is_ignored() -> None:
    """Kein Punkt, Enter vor dem Inhalt, ``[-]`` oder mehr als ein Zeichen eingefügt → ``None``."""
    assert continue_list("Text", "Text\n", 4) is None
    assert continue_list("- a", "-\n a", 1) is None
    assert continue_list("- [-] a", "- [-] a\n", 7) is None
    assert continue_list("- a", "- a\nxy", 3) is None


def test_ambiguous_newline_position_uses_the_caret() -> None:
    """Enter direkt vor einem vorhandenen Zeilenumbruch: der vorige Caret entscheidet."""
    old = "- a\nb"
    assert continue_list(old, "- a\n\nb", 3) == ("- a\n- \nb", 6)
    assert continue_list(old, "- a\n\nb", 4) is None  # Enter am Anfang von „b“ (Text)
