"""Tests für Tag-Eingabe, ``add_tag``/``insert_topic`` und das Taggen vor dem Verschieben."""

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.edits import add_tag, insert_topic
from merkweiser.core.move_plan import move_context, tag_for_move
from merkweiser.core.patch import Target
from merkweiser.core.tags import tag_from_input


@pytest.mark.parametrize("raw, project, expected", [
    ("schule", False, "schule"),
    ("#schule", False, "schule"),
    ("  #schule ", False, "schule"),
    ("umzug", True, "projekt/umzug"),
    ("#projekt/umzug", True, "projekt/umzug"),
    ("Projekt/Umzug", True, "projekt/Umzug"),
    ("a/b", False, "a/b"),
])
def test_tag_from_input_accepts(raw: str, project: bool, expected: str) -> None:
    """Führendes ``#`` und mitgetipptes Präfix werden entfernt, kein doppeltes Präfix."""
    assert tag_from_input(raw, project) == expected


@pytest.mark.parametrize("raw, project", [("", False), ("#", False), ("zwei worte", False), ("2026", False),
                                          ("a/", False), ("ä!", False), ("projekt/", True), ("#", True)])
def test_tag_from_input_rejects(raw: str, project: bool) -> None:
    """Leer, Leerzeichen, rein numerisch und ungültige Zeichen werden mit Begründung abgelehnt."""
    with pytest.raises(ValueError):
        tag_from_input(raw, project)


def test_add_tag_respects_real_tags_trailing_space_and_crlf() -> None:
    """Vorhandener echter Tag → unverändert; nur in Code vorhanden → wird ergänzt; Leerraum und CRLF bleiben."""
    doc = parse_document(b"T #Schule\r\n- [ ] a `#x`  \r\n")
    assert add_tag(doc, Target("a.md", 0, "T #Schule"), "schule") == doc.source.to_bytes()
    assert add_tag(doc, Target("a.md", 1, "- [ ] a `#x`  "), "x") == b"T #Schule\r\n- [ ] a `#x` #x  \r\n"


def test_insert_topic_only_for_notes_without_topic() -> None:
    """``insert_topic`` setzt eine Themenzeile vor eine Notiz ohne Thema; mit Thema → ValueError."""
    doc = parse_document(b"A\n- x\n\n- [ ] a\n- [ ] b\n")
    assert insert_topic(doc, 1, "#neu") == b"A\n- x\n\n#neu\n- [ ] a\n- [ ] b\n"
    with pytest.raises(ValueError):
        insert_topic(doc, 0, "#neu")


def test_move_context() -> None:
    """Überpunkt (Eltern-Punkt bzw. Thema), alleiniges Todo und gemeinsame Projekte."""
    doc = parse_document(b"T #projekt/a\n- [ ] eins\n  - [ ] teil\n- [ ] zwei\n\n- [ ] frei\n- [ ] frei2\n")
    top = move_context(doc, Target("a.md", 1, "- [ ] eins"))
    assert (top.sole_todo, top.parent.line_no, top.shared_projects) == (False, 0, ("a",))
    sub = move_context(doc, Target("a.md", 2, "  - [ ] teil"))
    assert sub.parent.expected_text == "- [ ] eins" and sub.shared_projects == ("a",)
    free = move_context(doc, Target("a.md", 5, "- [ ] frei"))
    assert free.parent is None and free.t_projects == ()
    assert top.project_conflict("a") is None and "nicht überschrieben" in top.project_conflict("b")


def test_tag_for_move_tags_todo_and_parent_and_resolves_new_target() -> None:
    """Tag an Todo und Überpunkt; ohne Thema neue Themenzeile, Target danach neu aufgelöst."""
    doc = parse_document(b"T\n- P\n  - [ ] teil\n  - [ ] anderes\n")
    raw, target = tag_for_move(doc, Target("a.md", 2, "  - [ ] teil"), "x")
    assert raw == b"T\n- P #x\n  - [ ] teil #x\n  - [ ] anderes\n"
    assert (target.line_no, target.expected_text) == (2, "  - [ ] teil #x")
    untitled = parse_document(b"A\n\n- [ ] eins\n- [ ] zwei\n")
    raw, target = tag_for_move(untitled, Target("a.md", 2, "- [ ] eins"), "x")
    assert raw == b"A\n\n#x\n- [ ] eins #x\n- [ ] zwei\n"
    assert parse_document(raw).line_text(target.line_no) == target.expected_text == "- [ ] eins #x"
