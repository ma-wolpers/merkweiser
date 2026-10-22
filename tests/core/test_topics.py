"""Tests für Themenschlüssel, leere Themen und die eindeutige Themensuche."""

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.topics import find_topic_note, is_empty_topic, is_tag_topic, mergeable, topic_key, topic_line


@pytest.mark.parametrize("line, empty, tagged", [
    ("...", True, False),
    ("…", True, False),
    ("  ...  ", True, False),
    ("#a #b", True, True),
    ("... #a", True, True),
    ("#a `code`", False, False),
    ("[x](u#a)", False, False),
    ("[[Seite#a]]", False, False),
    ("`#a`", False, False),
    ("Elternabend #schule", False, False),
    ("....", False, False),
])
def test_empty_and_tag_topics(line: str, empty: bool, tagged: bool) -> None:
    """Leer heißt: nur ``...`` und/oder echte Tags; ``#`` in Code oder Links zählt nicht als Tag."""
    assert is_empty_topic(line) is empty
    assert is_tag_topic(line) is tagged


def test_topic_key_normalizes_only_trim_and_ellipsis() -> None:
    """Schlüssel: getrimmt, ``…`` wird ``...``; sonst keine Normalisierung."""
    assert topic_key("  … #a ") == "... #a"
    assert topic_key("Thema") != topic_key("thema")


def test_mergeable() -> None:
    """Zusammenführbar sind normale Themen und Tag-Themen, nicht ``...`` und nicht „ohne Thema“."""
    assert mergeable("Thema") and mergeable("#schule")
    assert not mergeable("...") and not mergeable(None)


def test_topic_line_and_find_topic_note() -> None:
    """Genau ein Treffer liefert die Notiz; kein oder zwei Treffer liefern ``None``; ``...`` nie."""
    doc = parse_document(b"A #x\n- [ ] 1\n\nB\n- [ ] 2\n\nB\n- [ ] 3\n\n- [ ] ohne\n\n...\n- [ ] p\n")
    assert [topic_line(doc, n) for n in doc.notes] == ["A #x", "B", "B", None, "..."]
    assert find_topic_note(doc, "A #x") is doc.notes[0]
    assert find_topic_note(doc, "B") is None
    assert find_topic_note(doc, "C") is None
    assert find_topic_note(doc, "...") is None
