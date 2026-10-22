"""Tests für die Move-Planung (Fälle, materialisierte Tags, Zielwahl, Zusammenführen, exakte Quelle)."""

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.move_plan import NEW, insert_moved, moved_chunks, plan_move, plan_target, remove_moved_source
from merkweiser.core.patch import StaleTargetError, Target

SOURCE = """# Woche #w
Thema #uni #projekt/Bachelor
- [ ] Teil
  - [ ] Kapitel schreiben #text
    - [ ] Abschnitt 1
    weiter
  - [ ] anderes
- [ ] danach
"""


def plan():
    """Hilfsfunktion: Move des eingerückten Todos „Kapitel schreiben“ (Notiz hat weitere Todos)."""
    return plan_move(parse_document(SOURCE.encode()), Target("2026-10-08.md", 3, "  - [ ] Kapitel schreiben #text"))


def moved(source: str, line_no: int, target_text: str = "") -> bytes:
    """Hilfsfunktion: plant den Move eines Todos und fügt ihn in ``target_text`` ein."""
    move = plan_move(parse_document(source.encode()), Target("a.md", line_no, source.splitlines()[line_no]))
    dst = parse_document(target_text.encode())
    return insert_moved(dst, move, plan_target(dst, move))


def test_plan_takes_subtree_and_materializes_only_tags_the_topic_does_not_carry() -> None:
    """Teilbaum samt Fortsetzung, Wurzel auf Ebene 0; Thema wird mitgenommen, seine Tags nicht doppelt geschrieben.

    ``#w`` steht in der Themenzeile; ``#uni``/``#projekt/Bachelor`` stehen in der Erläuterung, die nicht
    mitwandert, und werden deshalb an das Todo geschrieben.
    """
    move = plan()
    assert move.mode == "todo" and move.topic == "# Woche #w"
    assert move.source_block.expected_lines == (
        "  - [ ] Kapitel schreiben #text", "    - [ ] Abschnitt 1", "    weiter")
    assert move.moved_lines == (
        "- [ ] Kapitel schreiben #text #uni #projekt/Bachelor", "  - [ ] Abschnitt 1", "  weiter")


def test_moved_todo_keeps_effective_tags_in_target() -> None:
    """Nach dem Einfügen hat das Todo im Ziel dieselben effektiven Tags (Thema + materialisierte)."""
    target = parse_document(insert_moved(parse_document(b""), plan(), NEW))
    assert target.line_text(0) == "# Woche #w"
    root = [n for n in target.notes[0].outline.items() if "Kapitel" in target.line_text(n.lines[0])][0]
    assert target.notes[0].tags[root.index].effective >= {"w", "uni", "text", "projekt/bachelor"}


def test_todo_is_appended_to_the_only_note_with_the_same_topic() -> None:
    """Gleiches Thema im Ziel → unten anhängen (ohne Themenkopie); sonst neue Notiz mit Thema."""
    target = "Heute\n- [ ] x\n\n# Woche #w\n- [ ] alt\n\nDanach\n"
    merged = insert_moved(parse_document(target.encode()), plan(), plan_target(parse_document(target.encode()), plan()))
    assert merged.decode() == ("Heute\n- [ ] x\n\n# Woche #w\n- [ ] alt\n- [ ] Kapitel schreiben #text #uni "
                               "#projekt/Bachelor\n  - [ ] Abschnitt 1\n  weiter\n\nDanach\n")
    fresh = insert_moved(parse_document(b"Heute\n- [ ] x\n"), plan(), NEW)
    assert fresh.decode().endswith("- [ ] x\n\n# Woche #w\n- [ ] Kapitel schreiben #text #uni #projekt/Bachelor\n"
                                   "  - [ ] Abschnitt 1\n  weiter\n")


def test_duplicate_target_topic_is_never_guessed() -> None:
    """Zwei Notizen mit gleichem Thema im Ziel → keine Wahl, neue Notiz."""
    target = parse_document(b"# Woche #w\n- [ ] a\n\n# Woche #w\n- [ ] b\n")
    assert plan_target(target, plan()) == NEW


def test_empty_topic_is_not_copied_and_tag_topic_merges() -> None:
    """Leeres Thema: keine Themenkopie, Tags an das Todo; Tag-Thema führt mit genau einer Zielnotiz zusammen."""
    plain = "...\n- [ ] eins\n- [ ] zwei\n"
    assert moved(plain, 1, "...\n- [ ] dort\n").decode() == "...\n- [ ] dort\n\n- [ ] eins\n"
    tagged = "#schule\n- [ ] eins\n- [ ] zwei\n"
    assert moved(tagged, 1, "#schule\n- [ ] dort\n").decode() == "#schule\n- [ ] dort\n- [ ] eins #schule\n"
    assert moved(tagged, 1, "Anderes\n").decode() == "Anderes\n\n- [ ] eins #schule\n"


def test_untitled_note_with_several_todos_moves_the_todo_alone() -> None:
    """Notiz ohne Thema mit mehreren Todos: nur das Todo, ohne Thema, nie zusammengeführt."""
    assert moved("- [ ] eins\n- [ ] zwei\n", 0, "- [ ] dort\n").decode() == "- [ ] dort\n\n- [ ] eins\n"


def test_sole_todo_moves_the_whole_note_also_when_done_todos_are_inside() -> None:
    """Alleiniges Todo → ganze Notiz; abgehakte Todos außerhalb des Teilbaums zählen als weitere Todos."""
    sole = plan_move(parse_document(b"T\nInfo\n- Punkt\n- [ ] a\n  - [x] b\n"), Target("a.md", 3, "- [ ] a"))
    assert sole.mode == "notiz" and sole.moved_lines == ("T", "Info", "- Punkt", "- [ ] a", "  - [x] b")
    other = plan_move(parse_document(b"T\n- [ ] a\n- [x] b\n"), Target("a.md", 1, "- [ ] a"))
    assert other.mode == "todo"


def test_whole_note_merge_puts_explanation_before_the_first_item() -> None:
    """Ganze Notiz in Zielnotiz mit Listenpunkt: Erläuterung vor deren ersten Punkt, Rest unten, Thema nicht doppelt."""
    source = "T #x\nInfo 1\nInfo 2\n- [ ] neu\n  weiter neu\n"
    target = "T #x\nAlt-Info\n- [ ] alt\n  weiter alt\n\nB\n"
    assert moved(source, 3, target).decode() == (
        "T #x\nAlt-Info\nInfo 1\nInfo 2\n- [ ] alt\n  weiter alt\n- [ ] neu\n  weiter neu\n\nB\n")


def test_whole_note_merge_into_note_without_items_appends_at_its_end() -> None:
    """Zielnotiz ohne Listenpunkt: Erläuterung und Rest ans Ende dieser Notiz (vor der Leerzeile)."""
    assert moved("T\nInfo\n- [ ] neu\n", 2, "T\nNur Text\n\nB\n").decode() == "T\nNur Text\nInfo\n- [ ] neu\n\nB\n"


def test_whole_note_without_topic_is_appended_unchanged() -> None:
    """Ganze Notiz ohne Thema (bzw. mit reinem ``...``) wird nie zusammengeführt."""
    assert moved("- [ ] allein\n", 0, "- [ ] dort\n").decode() == "- [ ] dort\n\n- [ ] allein\n"
    assert moved("...\n- [ ] p\n", 1, "...\n- [ ] q\n").decode() == "...\n- [ ] q\n\n...\n- [ ] p\n"


def test_changed_target_note_is_not_searched_again() -> None:
    """Die gespeicherte Zielnotiz muss exakt wieder auffindbar sein; sonst StaleTargetError statt neuer Suche."""
    move = plan()
    target = parse_document(b"# Woche #w\n- [ ] alt\n")
    ziel = plan_target(target, move)
    with pytest.raises(StaleTargetError, match="Zielnotiz"):
        insert_moved(parse_document(b"# Woche #w\n- [ ] alt geaendert\n"), move, ziel)
    assert moved_chunks(move, ziel) == (move.moved_lines,)


def test_remove_source_only_with_exact_unique_block() -> None:
    """Quelle wird nur bei exaktem, eindeutigem Block verändert."""
    move = plan()
    removed = remove_moved_source(parse_document(SOURCE.encode()), move)
    assert "Kapitel" not in removed.decode() and "- [ ] anderes" in removed.decode()
    edited = SOURCE.replace("Abschnitt 1", "Abschnitt 1 geändert")
    with pytest.raises(StaleTargetError):
        remove_moved_source(parse_document(edited.encode()), move)
    duplicated = SOURCE + "\nNoch\n  - [ ] Kapitel schreiben #text\n    - [ ] Abschnitt 1\n    weiter\n"
    with pytest.raises(StaleTargetError):
        remove_moved_source(parse_document(duplicated.encode()), move)


def test_moving_a_whole_note_removes_its_blank_gap() -> None:
    """Ganze Notiz (z. B. ein Todo zwischen Leerzeilen): Die Quelle behält keine doppelte Leerzeile."""
    source = parse_document("A\n\n- [ ] allein\n\nB\n".encode())
    move = plan_move(source, Target("2026-10-08.md", 2, "- [ ] allein"))
    assert move.mode == "notiz"
    assert remove_moved_source(source, move) == "A\n\nB\n".encode()
