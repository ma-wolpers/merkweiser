"""Tests für die Block-Erkennung (Frontmatter, Codeblöcke, Trenner, Notizen)."""

from merkweiser.core.blocks import FileLayout, Span, analyze
from merkweiser.core.source import SourceText


def layout(text: str) -> FileLayout:
    """Hilfsfunktion: Layout eines Textes."""
    return analyze(SourceText.from_bytes(text.encode()).lines)


def note_texts(text: str) -> list[list[str]]:
    """Hilfsfunktion: Inhaltszeilen jeder nicht leeren Notiz."""
    lines = text.split("\n")
    result = []
    for note in layout(text).notes:
        if note.content:
            result.append(lines[note.content.start:note.content.end])
    return result


def test_every_blank_line_and_every_separator_ends_a_note() -> None:
    """Formatänderung 2026-10-21: jede Leerzeile beendet eine Notiz; ``---`` trennt auch direkt unter Text."""
    text = "A\n- x\n\n---\n\nB\nÜberschrift\n---\nC\n\n- [ ] allein\n"
    assert note_texts(text) == [["A", "- x"], ["B", "Überschrift"], ["C"], ["- [ ] allein"]]


def test_separator_with_surrounding_spaces() -> None:
    """Leerraum um ``---`` ist erlaubt."""
    assert len(layout("A\n\n  ---  \nB\n").separators) == 1


def test_consecutive_separators_create_no_empty_note() -> None:
    """Zwei Trenner hintereinander sind nur Trenner; leere Notizen gibt es nicht."""
    result = layout("A\n\n---\n---\nB\n")
    assert result.separators == (2, 3)
    assert note_texts("A\n\n---\n---\nB\n") == [["A"], ["B"]]


def test_frontmatter_is_not_a_note() -> None:
    """Geschlossenes Frontmatter am Anfang gehört zu keiner Notiz."""
    result = layout("---\ntags: [a]\n---\nThema\n")
    assert result.frontmatter == Span(0, 3)
    assert result.separators == ()
    assert note_texts("---\ntags: [a]\n---\nThema\n") == [["Thema"]]


def test_frontmatter_closed_with_dots() -> None:
    """``...`` schließt Frontmatter ebenfalls."""
    assert layout("---\na: 1\n...\nX\n").frontmatter == Span(0, 3)


def test_unclosed_frontmatter_is_separator_at_note_start() -> None:
    """GRENZE: Nicht geschlossenes Frontmatter gilt als Trenner am Notizanfang."""
    result = layout("---\nThema\n")
    assert result.frontmatter is None
    assert result.separators == (0,)


def test_separator_inside_code_is_ignored() -> None:
    """``---`` in einem Codeblock trennt nicht."""
    text = "A\n```\n\n---\n```\nB\n"
    assert layout(text).separators == ()
    assert layout(text).fences == (Span(1, 5),)


def test_longer_fence_is_not_closed_by_shorter() -> None:
    """Ein ````-Block wird von ``` im Inneren nicht geschlossen."""
    text = "````\n```\n\n---\n```\n````\nB\n"
    result = layout(text)
    assert result.fences == (Span(0, 6),)
    assert result.separators == ()


def test_tilde_fence_needs_tilde_close() -> None:
    """Backticks schließen keinen Tilden-Block."""
    assert layout("~~~\n```\n~~~\nX\n").fences == (Span(0, 3),)


def test_unclosed_fence_runs_to_end_of_file() -> None:
    """Ein offener Codeblock reicht bis zum Dateiende."""
    result = layout("A\n```\n\n---\nB\n")
    assert result.fences == (Span(1, 5),)
    assert result.separators == ()


def test_backtick_fence_with_backtick_in_info_is_no_fence() -> None:
    """Eine Info-Zeichenkette mit Backtick macht die Zeile zu keinem Fence."""
    assert layout("``` a`b\n\n---\nX\n").fences == ()


def test_note_span_has_no_blank_margins() -> None:
    """Eine Notiz enthält nie Leerzeilen am Rand; Spanne und Inhalt sind gleich."""
    [note] = layout("\n\nA\nB\n\n").notes
    assert note.span == note.content == Span(2, 4)


def test_blank_line_inside_code_block_does_not_split() -> None:
    """Leerzeilen in einem Codeblock beenden die Notiz nicht."""
    assert note_texts("A\n```\nx\n\ny\n```\nB\n\nC\n") == [["A", "```", "x", "", "y", "```", "B"], ["C"]]


def test_empty_file_has_no_notes() -> None:
    """Eine leere bzw. nur aus Leerraum und Trennern bestehende Datei hat keine Notizen."""
    assert layout("").notes == () and layout("\n  \n---\n\n").notes == ()


def test_crlf_does_not_affect_separators() -> None:
    """CRLF-Dateien werden genauso zerlegt."""
    result = analyze(SourceText.from_bytes(b"A\r\n\r\n---\r\n\r\nB\r\n").lines)
    assert result.separators == (2,)
