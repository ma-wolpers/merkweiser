"""Tests für Inline-Lexer und Zeilensemantik (Marker, Checkbox, Tags, Projekte)."""

import pytest

from merkweiser.core.inline import (
    TodoStatus, find_tags, indent_columns, is_urgent, parse_list_item, project_name,
)
from merkweiser.core.lexer import TokenKind, tokenize


def kinds(text: str) -> list[tuple[str, str]]:
    """Hilfsfunktion: (Art, Text) jedes Tokens."""
    return [(t.kind.value, text[t.start:t.end]) for t in tokenize(text)]


def tag_names(text: str) -> list[str]:
    """Hilfsfunktion: Namen der gefundenen Tags."""
    return [t.name for t in find_tags(text)]


def test_tokens_cover_line_without_gaps() -> None:
    """Die Tokens decken die Zeile lückenlos ab."""
    text = "a `b` [[c]] [d](http://e) <https://f> g"
    tokens = tokenize(text)
    assert tokens[0].start == 0 and tokens[-1].end == len(text)
    assert all(a.end == b.start for a, b in zip(tokens, tokens[1:]))


def test_code_needs_matching_backtick_run() -> None:
    """Inline-Code endet bei einer Folge gleicher Länge, sonst sind Backticks Text."""
    assert kinds("x ``a`b`` y")[1] == ("code", "``a`b``")
    assert kinds("x `offen") == [("text", "x `offen")]


def test_link_label_is_text_url_is_link() -> None:
    """Die Beschriftung eines Links ist Text, das Ziel ``LINK_URL``."""
    assert kinds("[Label #t](https://x.de/#anker)") == [("text", "[Label #t]"), ("link_url", "(https://x.de/#anker)")]


@pytest.mark.parametrize("text, expected", [
    ("Thema #uni", ["uni"]),
    ("#a #b/c #d-e #f_g", ["a", "b/c", "d-e", "f_g"]),
    ("#Ümlaut und #Tag.", ["Ümlaut", "Tag"]),
    ("# Überschrift", []),
    ("## Überschrift #tag", ["tag"]),
    ("#2026 ist kein Tag, #2026-10 schon", ["2026-10"]),
    ("abc#kein", []),
    ("`#code` und [[#wiki]] und https://x.de/#anker", []),
    ("![bild](pfad#x) #echt", ["echt"]),
    ("==#dringend==", []),
    ("== #dringend==", ["dringend"]),
])
def test_find_tags(text: str, expected: list[str]) -> None:
    """Tags wie Obsidian: Wortanfang, nicht numerisch, nicht in Code oder Links."""
    assert tag_names(text) == expected


@pytest.mark.parametrize("prefix, expected", [
    ("", 0), ("  ", 2), ("\t", 4), (" \t", 4), ("  \t", 4), ("    \t", 8), ("\t  ", 6), ("\t\t", 8),
])
def test_indent_columns_use_tab_stops(prefix: str, expected: int) -> None:
    """Tabs springen zum nächsten Vielfachen von 4."""
    assert indent_columns(prefix) == expected


@pytest.mark.parametrize("text, status, urgent", [
    ("- [ ] offen", TodoStatus.OPEN, False),
    ("- [x] erledigt", TodoStatus.DONE, False),
    ("- [X] Erledigt", TodoStatus.DONE, False),
    ("- [-] abgebrochen", TodoStatus.OTHER, False),
    ("- [ ] ==dringend== mehr", TodoStatus.OPEN, True),
    ("- ==hervorgehoben==", TodoStatus.NONE, True),
    ("- [ ]", TodoStatus.OPEN, False),
    ("- [x]direkt", TodoStatus.NONE, False),
    ("1. [ ] nummeriert", TodoStatus.OPEN, False),
    ("* Punkt", TodoStatus.NONE, False),
])
def test_parse_list_item(text: str, status: TodoStatus, urgent: bool) -> None:
    """Checkbox-Status und Dringlichkeit nach FORMAT.md."""
    item = parse_list_item(text)
    assert item is not None
    assert (item.status, item.urgent) == (status, urgent)


@pytest.mark.parametrize("text", ["Text", "-kein Punkt", "#tag", "", "    "])
def test_non_list_lines(text: str) -> None:
    """Zeilen ohne Listenmarker sind keine Listenpunkte."""
    assert parse_list_item(text) is None


def test_status_column_points_into_brackets() -> None:
    """``status_col`` zeigt auf das Zeichen zwischen den eckigen Klammern."""
    text = "\t- [x] a"
    item = parse_list_item(text)
    assert item is not None and text[item.status_col] == "x"
    assert item.indent == 4


@pytest.mark.parametrize("body, expected", [("==a==", True), ("====", False), ("==offen", False), ("a ==b==", False)])
def test_is_urgent(body: str, expected: bool) -> None:
    """Dringend nur bei vollständiger Hervorhebung am Inhaltsanfang."""
    assert is_urgent(body) is expected


def test_project_name_is_case_insensitive_prefix() -> None:
    """Projekt-Tags erkennen das Präfix ohne Groß-/Kleinschreibung."""
    tags = find_tags("#Projekt/Umzug #projekt #projektx/y")
    assert [project_name(t, "projekt") for t in tags] == ["Umzug", None, None]


def test_empty_line_has_no_tokens() -> None:
    """Eine leere Zeile ergibt keine Tokens."""
    assert tokenize("") == ()
    assert TokenKind.TEXT.value == "text"
