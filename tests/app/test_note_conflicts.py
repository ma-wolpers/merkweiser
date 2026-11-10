"""Tests für die notizweise Konfliktauflösung (``app/note_plan.py``, ``app/note_conflicts.py``, W8)."""

import pytest

from merkweiser.app.conflict_views import Choice, case_headline
from merkweiser.app.note_conflicts import edit_prefill, entry_diff, initial_choices, missing, note_result, quick_select
from merkweiser.app.note_plan import Kind, Pick, note_plan
from merkweiser.core.conflicts import CaseKind, ConflictCase
from merkweiser.core.merge.diff3 import merge3
from merkweiser.core.merge.frontmatter import merge_frontmatter, split
from merkweiser.core.vault import parse_conflict_name

CONF = "2026-01-01.sync-conflict-20260101-120000-ABCDEFG.md"


def case(main: bytes | None, conflict: bytes, kind: CaseKind = CaseKind.MANUAL, merge=None, fm=None,
         reason: str = "") -> ConflictCase:
    """Synthetischer Konfliktfall ohne Vault."""
    return ConflictCase(kind, parse_conflict_name(CONF), main, conflict, merge, reason, fm)


def start(main: bytes | None, conflict: bytes, **kwargs):
    """Plan und Startwahl eines Falls."""
    plan = note_plan(case(main, conflict, **kwargs))
    return plan, initial_choices(plan)


def test_quick_select_sides_are_byte_exact_even_with_bom_and_crlf() -> None:
    """„Hauptdatei behalten“/„Konfliktversion übernehmen“ liefern exakt die Bytes der Fassung."""
    main = b"\xef\xbb\xbfA\r\n- [ ] a\r\n\r\n---\r\n\r\nB\r\n"
    conflict = b"A\n- [x] a\n\nC"
    plan, choices = start(main, conflict)
    quick_select(plan, choices, Choice.HAUPTDATEI)
    assert note_result(plan, choices) == (main, "Hauptdatei behalten")
    quick_select(plan, choices, Choice.KONFLIKTVERSION)
    assert note_result(plan, choices) == (conflict, "Konfliktversion übernehmen")


def test_zusammenfuehren_keeps_both_and_marks_todos_done() -> None:
    """Schnellwahl „Zusammenführen“: Beide, einseitige übernehmen, Todos erledigt (R1)."""
    plan, choices = start(b"A\n- [ ] a\n\nB\n- x\n", b"A\n- [x] a\n\nB\n- y\n\nC\n")
    assert [e.kind for e in plan.entries] == [Kind.STATUS, Kind.GEAENDERT, Kind.NUR_KONFLIKT]
    quick_select(plan, choices, Choice.BEIDE)
    data, decision = note_result(plan, choices)
    assert data == b"A\n- [x] a\n\nB\n- x\n- y\n\nC\n"
    assert decision == "Notizweise – Notiz 2: Beide, Notiz 3: Übernehmen; Todos: 1 erledigt, 0 offen"


def test_todo_status_must_be_decided_and_keeps_spelling() -> None:
    """Keine Vorauswahl: ohne Entscheidung kein Ergebnis; erledigt übernimmt ``[X]`` byte-genau."""
    plan, choices = start(b"T\n- [ ] a\n", b"T\n- [X] a\n")
    [entry] = plan.entries
    assert entry.kind is Kind.STATUS and missing(plan, choices) == ["Todo „- [ ] a“: erledigt oder offen?"]
    with pytest.raises(ValueError):
        note_result(plan, choices)
    choices.todos[(0, entry.todos[0].row)] = True
    assert note_result(plan, choices)[0] == b"T\n- [X] a\n"
    choices.todos[(0, entry.todos[0].row)] = False
    assert note_result(plan, choices)[0] == b"T\n- [ ] a\n"


def test_todo_toggle_inside_changed_note_with_conflict_side() -> None:
    """Todo-Wahl gilt auch in einer geänderten Notiz; die übrigen Zeilen kommen aus der gewählten Seite."""
    plan, choices = start(b"T\n- [x] a\n- alt\n", b"T\n- [ ] a\n- neu\n")
    [entry] = plan.entries
    assert entry.kind is Kind.GEAENDERT and entry.suggested is None
    choices.picks[0] = Pick.KONFLIKT
    choices.todos[(0, entry.todos[0].row)] = True
    assert note_result(plan, choices)[0] == b"T\n- [x] a\n- neu\n"


def test_gaps_follow_the_file_the_notes_are_adjacent_in() -> None:
    """Übernommene Notiz zwischen zwei gleichen: Lücken der Konfliktversion; weggelassen: Hauptdatei."""
    main, conflict = b"A\n\n---\n\nB\n", b"A\n\n---\n\nX\n\nB\n"
    plan, choices = start(main, conflict)
    assert [e.kind for e in plan.entries] == [Kind.GLEICH, Kind.NUR_KONFLIKT, Kind.GLEICH]
    assert missing(plan, choices) == ["Notiz 1: Wahl fehlt"]
    choices.picks[1] = Pick.KONFLIKT
    assert note_result(plan, choices)[0] == conflict
    choices.picks[1] = Pick.HAUPT
    assert note_result(plan, choices)[0] == main


def test_mixed_choice_inserts_blank_line_between_unrelated_notes() -> None:
    """Notizen, die in keiner Fassung benachbart sind, trennt eine Leerzeile."""
    plan, choices = start(b"A\n\n---\n\nB\n", b"C\n\nD\n")
    assert [e.kind for e in plan.entries] == [Kind.NUR_HAUPT, Kind.NUR_HAUPT, Kind.NUR_KONFLIKT, Kind.NUR_KONFLIKT]
    choices.picks.update({0: Pick.HAUPT, 1: Pick.KONFLIKT, 2: Pick.HAUPT, 3: Pick.KONFLIKT})
    assert note_result(plan, choices)[0] == b"A\n\nD\n"


def test_edited_note_strips_edges_and_empty_text_removes_it() -> None:
    plan, choices = start(b"A\n\nB\n- x\n", b"A\n\nB\n- y\n")
    choices.picks[1] = Pick.BEARBEITET
    choices.texts[1] = "\r\n\r\nB\r\n- x und y\r\n\r\n"
    assert note_result(plan, choices)[0] == b"A\n\nB\n- x und y\n"
    choices.texts[1] = "  \n"
    assert note_result(plan, choices)[0] == b"A\n"


def test_edit_prefill_defaults_to_both_sides() -> None:
    plan, choices = start(b"B\n- [ ] a\n- x\n", b"B\n- [x] a\n- y\n")
    assert edit_prefill(plan.entries[0], choices, 0) == "B\n- [ ] a\n- x\n- y"


def test_diff3_suggestion_preselects_deletion_but_not_contradiction() -> None:
    """Merge-Vorschlag: einseitig gelöschte Notiz → „Entfernen“; Notiz mit Hunk → keine Vorauswahl."""
    base = ["T", "- [ ] eins", "", "M", "", "X"]
    a = ["T", "- [ ] eins A", "", "M", "", "X"]
    b = ["T", "- [ ] eins B", "", "M"]
    merge = merge3(base, a, b)
    assert merge.hunks
    plan, choices = start("\n".join(a).encode() + b"\n", "\n".join(b).encode() + b"\n", merge=merge)
    assert [(e.kind, e.suggested) for e in plan.entries] == [
        (Kind.GEAENDERT, None), (Kind.GLEICH, None), (Kind.NUR_HAUPT, Pick.KONFLIKT)]
    assert missing(plan, choices) == ["Notiz 1: Wahl fehlt"]


def test_head_only_on_one_side_offers_head_entry() -> None:
    """Kopf nur in der Hauptdatei: Kopf-Eintrag; „Beide“ vorausgewählt, wenn der Fall einen Kopf-Merge hat."""
    main, conflict = b"---\ntags: [a]\n---\nA\n", b"A\n"
    plan, choices = start(main, conflict)
    assert plan.head is not None and plan.head.suggested is None and plan.entries[0].kind is Kind.GLEICH
    choices.head = Pick.KONFLIKT
    assert note_result(plan, choices)[0] == conflict
    fm = merge_frontmatter(split(main)[0], split(conflict)[0])
    plan, choices = start(main, conflict, fm=fm)
    assert choices.head is Pick.BEIDE and missing(plan, choices) == []
    assert note_result(plan, choices)[0] == main


def test_open_head_and_unsupported_encoding_allow_whole_file_only() -> None:
    plan, choices = start(b"---\nkaputt\nA\n", b"A\n")
    assert plan.whole_only and plan.entries == () and missing(plan, choices) == ["Ganze Fassung wählen"]
    with pytest.raises(ValueError):
        quick_select(plan, choices, Choice.BEIDE)
    quick_select(plan, choices, Choice.HAUPTDATEI)
    assert note_result(plan, choices)[0] == b"---\nkaputt\nA\n"
    assert note_plan(case(b"\xff\xfeA", b"A\n")).whole_only


def test_main_deleted_restores_selected_notes() -> None:
    """Hauptdatei fehlt: jede Notiz einzeln wiederherstellen; nichts gewählt → Hinweis auf „Verwerfen“."""
    conflict = b"A\n\n---\n\nB\n- [ ] b\n"
    plan, choices = start(None, conflict, kind=CaseKind.MAIN_DELETED)
    assert [(e.kind, e.suggested) for e in plan.entries] == [(Kind.NUR_KONFLIKT, None)] * 2
    choices.picks.update({0: Pick.HAUPT, 1: Pick.KONFLIKT})
    assert note_result(plan, choices)[0] == b"B\n- [ ] b\n"
    choices.picks[1] = Pick.HAUPT
    assert "Version verwerfen" in missing(plan, choices)[0]
    quick_select(plan, choices, Choice.KONFLIKTVERSION)
    assert note_result(plan, choices) == (conflict, "Version wiederhergestellt")


def test_same_content_with_other_line_endings_needs_no_decision() -> None:
    plan, choices = start(b"A\r\n- [ ] a\r\n", b"A\n- [ ] a\n")
    assert missing(plan, choices) == [] and note_result(plan, choices)[0] == b"A\r\n- [ ] a\r\n"


def test_entry_diff_shows_undecided_todo_as_question_mark() -> None:
    plan, _choices = start(b"T\n- [ ] a\n- x\n", b"T\n- [x] a\n- y\n")
    assert [(r.side, r.text) for r in entry_diff(plan.entries[0])] == [
        ("beide", "T"), ("beide", "- [?] a"), ("haupt", "- x"), ("konflikt", "- y")]


def test_moved_note_is_flagged() -> None:
    plan, _choices = start(b"M\n\nA\n\nB\n", b"A\n\nB\n\nM\n")
    assert [(e.kind, e.moved) for e in plan.entries] == [
        (Kind.NUR_HAUPT, True), (Kind.GLEICH, False), (Kind.GLEICH, False), (Kind.NUR_KONFLIKT, True)]


def test_case_headline_skips_reason_equal_to_label() -> None:
    assert case_headline(case(None, b"x", CaseKind.MAIN_DELETED, reason="Hauptdatei fehlt")) == "Hauptdatei fehlt"
    assert case_headline(case(b"a", b"x", reason="verschachtelte Konfliktdatei")) == \
        "Entscheidung nötig: verschachtelte Konfliktdatei"
