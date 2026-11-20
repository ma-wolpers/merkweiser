"""Tests für die Notiz-Zuordnung zweier Fassungen (``core/merge/notes.py``, W8)."""

from merkweiser.core.merge.model import Cert
from merkweiser.core.merge.notes import STATUS_MASK, Row, body_notes, note_rows, pair_notes, status_key


def notes(text: str):
    """Rumpf aus Text (Zeilen durch ``\\n``)."""
    return body_notes(text.split("\n"))


def pairs(a: str, b: str):
    """Zuordnung zweier Texte als Liste von Paaren."""
    return pair_notes(notes(a), notes(b))


def test_body_notes_spans_and_gaps() -> None:
    """Notizen trennen Leerzeilen und ``---``; Lücken enthalten genau die Trennzeilen."""
    body = notes("A\n- [ ] a\n\n---\n\nB\n\nC")
    assert body.spans == ((0, 2), (5, 6), (7, 8))
    assert body.gap(0) == () and body.gap(1) == ("", "---", "") and body.gap(2) == ("",) and body.gap(3) == ()


def test_leading_separator_is_not_frontmatter() -> None:
    """Ein ``---`` am Rumpfanfang (Kopf schon abgetrennt) ist Trenner, kein Frontmatter."""
    body = notes("---\nA\n---\nB")
    assert body.spans == ((1, 2), (3, 4))


def test_status_key_masks_only_checkbox_status() -> None:
    assert status_key("- [x] a") == status_key("- [ ] a") == f"- [{STATUS_MASK}] a"
    assert status_key("- [-] a") == f"- [{STATUS_MASK}] a"  # W9: verpasst ist ein Todo-Zustand
    assert status_key("- [/] a") == "- [/] a" and status_key("Text [x]") == "Text [x]"


def test_todo_in_code_block_is_not_masked() -> None:
    body = notes("```\n- [ ] code\n```")
    assert body.keys == ("```", "- [ ] code", "```")


def test_identical_notes_anchor_and_status_only_pairs() -> None:
    """L0 identisch, L1 nur Häkchen verschieden."""
    assert pairs("A\n\nT\n- [ ] x", "A\n\nT\n- [x] x") == [(0, 0), (1, 1)]


def test_same_topic_pairs_changed_note() -> None:
    """L2: gleiche Themenzeile → zugeordnet, auch wenn der Rest anders ist."""
    assert pairs("Einkauf\n- Milch\n\nArbeit", "Einkauf\n- Brot\n\nArbeit") == [(0, 0), (1, 1)]


def test_one_to_one_leftover_needs_shared_line() -> None:
    """L3: übrig gebliebene 1×1-Lücke nur mit gemeinsamer Zeile; sonst getrennt (A zuerst)."""
    assert pairs("X\n\nalt\n- gemeinsam\n\nZ", "X\n\nneu\n- gemeinsam\n\nZ") == [(0, 0), (1, 1), (2, 2)]
    assert pairs("X\n\nalt\n\nZ", "X\n\nneu\n\nZ") == [(0, 0), (1, None), (None, 1), (2, 2)]


def test_duplicates_pair_in_order() -> None:
    """Doppelte Notizen: die gleiche Randnotiz paart, die übrige ist einseitig."""
    assert pairs("X\n\nX", "X") == [(0, 0), (1, None)]
    assert pairs("X", "X\n\nX") == [(0, 0), (None, 1)]


def test_moved_note_is_one_sided_on_both_sides() -> None:
    """GRENZE(Notizwahl): verschobene Notiz → nur A plus nur B."""
    assert pairs("M\n\nA\n\nB", "A\n\nB\n\nM") == [(0, None), (1, 0), (2, 1), (None, 2)]


def test_every_note_exactly_once_and_monotonic() -> None:
    """Jede Notiz genau einmal, je Seite aufsteigend, deterministisch."""
    a, b = "A\n\nB\n- [ ] b\n\nC\n\nD", "B\n- [x] b\n\nE\n\nA\n\nD"
    first = pairs(a, b)
    assert first == pairs(a, b)
    left = [i for i, _ in first if i is not None]
    right = [j for _, j in first if j is not None]
    assert left == sorted(left) == list(range(4)) and right == sorted(right) == list(range(4))


def test_note_rows_mark_status_pairs_and_gaps() -> None:
    """Zeilenabschnitte: gleich, R1 (Todo-Wahl), R2 ([x]/[X]), Lücke."""
    a_lines = ("T", "- [ ] a", "- [x] b", "alt")
    b_lines = ("T", "- [x] a", "- [X] b", "neu", "dazu")
    rows = note_rows(a_lines, [status_key(l) for l in a_lines], b_lines, [status_key(l) for l in b_lines])
    assert rows == (Row(("T",), ("T",)), Row(("- [ ] a",), ("- [x] a",), Cert.R1),
                    Row(("- [x] b",), ("- [X] b",), Cert.R2), Row(("alt",), ("neu", "dazu")))
    assert rows[0].same and not rows[3].same
