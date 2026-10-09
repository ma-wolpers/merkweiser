"""Tests für Edit-Ziele, Minimal-Diff-Edits und Notiz-Operationen."""

import difflib

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.edits import NotATodoError, add_todo, set_done, set_project, set_urgent
from merkweiser.core.note_ops import NoteNotFoundError, append_note, delete_note, replace_note_text
from merkweiser.core.patch import (
    BlockTarget, LineEdit, StaleTargetError, Target, UnsupportedEncodingError, apply_edits, resolve_block,
    resolve_line,
)
from merkweiser.core.source import SourceText

BASE = "Thema #t\r\n- [ ] Kisten packen #keller\r\n- [X] Erledigt\r\n  - [ ] Kind\r\nEnde ohne Umbruch"


def changed_lines(before: bytes, after: bytes) -> list[str]:
    """Hilfsfunktion: geänderte Zeilen laut difflib (+/-)."""
    a = before.decode().splitlines(keepends=True)
    b = after.decode().splitlines(keepends=True)
    return [l for l in difflib.ndiff(a, b) if l[:1] in "+-"]


def doc(text: str = BASE):
    """Hilfsfunktion: Dokument aus Text."""
    return parse_document(text.encode())


def tgt(line_no: int, text: str) -> Target:
    """Hilfsfunktion: Ziel in der Testdatei."""
    return Target("x.md", line_no, text)


def test_set_done_changes_only_status_char_and_keeps_crlf() -> None:
    """Erledigen ändert genau ein Zeichen in einer Zeile; CRLF und fehlender Umbruch bleiben."""
    before = BASE.encode()
    after = set_done(doc(), tgt(1, "- [ ] Kisten packen #keller"), True)
    assert after == before.replace(b"- [ ] Kisten", b"- [x] Kisten")
    assert len(changed_lines(before, after)) == 2


def test_set_done_keeps_capital_x_and_is_idempotent() -> None:
    """``[X]`` bleibt beim Erledigen stehen; Zielzustand erreicht → unverändert."""
    assert set_done(doc(), tgt(2, "- [X] Erledigt"), True) == BASE.encode()
    reopened = set_done(doc(), tgt(2, "- [X] Erledigt"), False)
    assert b"- [ ] Erledigt" in reopened


def test_target_relocates_uniquely_after_insert() -> None:
    """Eine verschobene Zeile wird über eindeutigen Text wiedergefunden."""
    moved = doc("Neu\n" + BASE)
    after = set_done(moved, tgt(1, "- [ ] Kisten packen #keller"), True)
    assert b"- [x] Kisten packen" in after


def test_identical_todos_are_never_guessed() -> None:
    """Zwei identische Todos und das Ziel steht nicht mehr an seiner Stelle → StaleTargetError."""
    twins = doc("Neu\nT\n- [ ] gleich\n- [ ] gleich\n")
    with pytest.raises(StaleTargetError):
        set_done(twins, tgt(0, "- [ ] gleich"), True)
    assert b"- [x] gleich\n- [ ] gleich" in set_done(twins, tgt(2, "- [ ] gleich"), True)


def test_not_a_todo() -> None:
    """Thema, Punkt ohne Checkbox oder Todo im Codeblock sind keine Todos."""
    with pytest.raises(NotATodoError):
        set_done(doc(), tgt(0, "Thema #t"), True)
    with pytest.raises(NotATodoError):
        set_done(doc("```\n- [ ] code\n```\n"), tgt(1, "- [ ] code"), True)


def test_set_urgent_wraps_content_before_trailing_tags_and_back() -> None:
    """Dringend: ``==…==`` um den Inhalt, Tags am Ende bleiben draußen; Aufheben stellt wieder her."""
    urgent = set_urgent(doc(), tgt(1, "- [ ] Kisten packen #keller"), True)
    assert b"- [ ] ==Kisten packen== #keller\r\n" in urgent
    back = set_urgent(parse_document(urgent), tgt(1, "- [ ] ==Kisten packen== #keller"), False)
    assert back == BASE.encode()


def test_set_project_replaces_explicit_projects_only() -> None:
    """Projekt setzen ersetzt alle Projekt-Tags der Zeile, andere Tags bleiben."""
    d = doc("T #projekt/Erbe\n- [ ] a #projekt/X #keller #Projekt/Y   \n")
    after = set_project(d, tgt(1, "- [ ] a #projekt/X #keller #Projekt/Y   "), "Umzug", "projekt")
    assert after == b"T #projekt/Erbe\n- [ ] a #keller #projekt/Umzug   \n"
    removed = set_project(parse_document(after), tgt(1, "- [ ] a #keller #projekt/Umzug   "), None, "projekt")
    assert removed == b"T #projekt/Erbe\n- [ ] a #keller   \n"
    with pytest.raises(ValueError):
        set_project(d, tgt(1, "- [ ] a #projekt/X #keller #Projekt/Y   "), "mit Leerzeichen", "projekt")


def test_add_todo_at_note_end_and_as_child() -> None:
    """Neues Todo ans Notizende bzw. als letztes Kind mit passender Einrückung."""
    base = "T\n- [ ] a\n  - [ ] a1\n- [ ] b\n\n---\n\nZweite\n"
    end = add_todo(doc(base), 0, "neu")
    assert end.decode().split("\n")[:5] == ["T", "- [ ] a", "  - [ ] a1", "- [ ] b", "- [ ] neu"]
    child = add_todo(doc(base), 0, "kind", parent=tgt(1, "- [ ] a"))
    assert child.decode().split("\n")[:4] == ["T", "- [ ] a", "  - [ ] a1", "  - [ ] kind"]
    first_child = add_todo(doc(base), 0, "unter b", parent=tgt(3, "- [ ] b"))
    assert "  - [ ] unter b" in first_child.decode()
    with pytest.raises(ValueError):
        add_todo(doc(base), 0, "zwei\nzeilen")


def test_append_note_rules() -> None:
    """Anhängen: Trenner mit Leerzeilen; leere Datei/Frontmatter ohne Trenner; Umbruch ergänzt."""
    assert append_note(doc("A\n- x"), "Neu\n- y") == b"A\n- x\n\n---\n\nNeu\n- y\n"
    assert append_note(doc("A\r\n\r\n\r\n"), "N") == b"A\r\n\r\n---\r\n\r\nN\r\n"
    assert append_note(doc(""), "  \nN\n\n") == b"N\n"
    assert append_note(doc("---\na: 1\n---\n"), "N") == b"---\na: 1\n---\nN\n"


def test_replace_note_text_changes_only_that_note() -> None:
    """Rohtext-Ersatz ändert genau den Notizinhalt, nichts außerhalb."""
    text = "A\n- x\n\n---\n\nB\n- y\n"
    after = replace_note_text(doc(text), ("B", "- y"), "B neu\n- [ ] z")
    assert after == b"A\n- x\n\n---\n\nB neu\n- [ ] z\n"


def test_replace_note_text_refuses_changed_boundaries() -> None:
    """Grenzen verschoben (Trenner entfernt) oder Inhalt doppelt → NoteNotFoundError, nie raten."""
    merged = doc("A\n- x\nB\n- y\n")
    with pytest.raises(NoteNotFoundError):
        replace_note_text(merged, ("B", "- y"), "neu")
    twice = doc("B\n\n---\n\nB\n")
    with pytest.raises(NoteNotFoundError):
        replace_note_text(twice, ("B",), "neu")


@pytest.mark.parametrize("original, expected", [
    (("A",), b"B\n\n---\n\nC\n"),
    (("B",), b"A\n\n---\n\nC\n"),
    (("C",), b"A\n\n---\n\nB\n"),
])
def test_delete_note_removes_one_separator(original: tuple[str, ...], expected: bytes) -> None:
    """Löschen entfernt die Notiz und genau einen angrenzenden Trenner, Naht sauber."""
    assert delete_note(doc("A\n\n---\n\nB\n\n---\n\nC\n"), original) == expected


def test_unsupported_encoding_is_never_written() -> None:
    """Nicht unterstütztes Encoding → jede Schreib-Op verweigert."""
    bad = parse_document(b"T \xe4\n- [ ] a\n")
    with pytest.raises(UnsupportedEncodingError):
        set_done(bad, tgt(1, "- [ ] a"), True)
    with pytest.raises(UnsupportedEncodingError):
        append_note(bad, "N")


def test_apply_edits_insert_after_line_without_newline() -> None:
    """Einfügen hinter der letzten Zeile ohne Umbruch: Zustand „ohne Schluss-Umbruch“ bleibt."""
    source = SourceText.from_bytes(b"a\r\nb")
    assert apply_edits(source, [LineEdit(2, 2, ("c",))]) == b"a\r\nb\r\nc"


def test_resolve_block_requires_unique_sequence() -> None:
    """Blockziele brauchen eine eindeutige exakte Zeilenfolge."""
    source = SourceText.from_bytes(b"x\n- a\n  - b\n- a\n  - b\n")
    with pytest.raises(StaleTargetError):
        resolve_block(source, BlockTarget("x.md", 0, ("- a", "  - b")))
    assert resolve_block(source, BlockTarget("x.md", 3, ("- a", "  - b"))) == 3
    assert resolve_line(source, Target("x.md", 0, "x")) == 0
