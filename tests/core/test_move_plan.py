"""Tests für die Move-Planung (Block, materialisierte Tags, Zielnotiz, exakter Quellnachweis)."""

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.move_plan import insert_moved, plan_move, remove_moved_source
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
    """Hilfsfunktion: Move des eingerückten Todos „Kapitel schreiben“."""
    return plan_move(parse_document(SOURCE.encode()), Target("2026-10-08.md", 3, "  - [ ] Kapitel schreiben #text"))


def test_plan_takes_subtree_and_materializes_inherited_tags() -> None:
    """Teilbaum samt Fortsetzung; Wurzel auf Ebene 0; geerbte Tags explizit (außen → innen)."""
    move = plan()
    assert move.source_block.expected_lines == (
        "  - [ ] Kapitel schreiben #text", "    - [ ] Abschnitt 1", "    weiter")
    assert move.moved_lines == (
        "- [ ] Kapitel schreiben #text #w #uni #projekt/Bachelor", "  - [ ] Abschnitt 1", "  weiter")


def test_moved_todo_keeps_effective_tags_in_target() -> None:
    """Nach dem Einfügen hat das Todo im Ziel dieselben effektiven Tags."""
    target = parse_document(insert_moved(parse_document(b""), plan(), "2026-10-08"))
    root = [n for n in target.notes[0].outline.items() if "Kapitel" in target.line_text(n.lines[0])][0]
    assert target.notes[0].tags[root.index].effective >= {"w", "uni", "text", "projekt/bachelor"}


def test_insert_creates_or_reuses_moved_note() -> None:
    """Fehlt die Notiz „Verschoben aus …“, wird sie angehängt; sonst wird sie wiederverwendet."""
    first = insert_moved(parse_document(b"Heute\n- [ ] x\n"), plan(), "2026-10-08")
    assert first.decode().endswith("---\n\nVerschoben aus [[2026-10-08]]\n- [ ] Kapitel schreiben #text #w #uni "
                                   "#projekt/Bachelor\n  - [ ] Abschnitt 1\n  weiter\n")
    second = insert_moved(parse_document(first), plan(), "2026-10-08")
    assert second.decode().count("Verschoben aus [[2026-10-08]]") == 1
    assert second.decode().count("Kapitel schreiben") == 2


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
