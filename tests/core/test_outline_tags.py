"""Tests für Notizbaum (outline) und Tag-Vererbung (tags) nach FORMAT.md."""

from merkweiser.core.blocks import analyze
from merkweiser.core.inline import TodoStatus
from merkweiser.core.outline import NodeKind, Outline, build_outline
from merkweiser.core.source import SourceText
from merkweiser.core.tags import compute_tags


def outline_of(text: str, note_index: int = 0) -> tuple[Outline, list[str]]:
    """Hilfsfunktion: Notizbaum einer Notiz plus Zeilentexte."""
    source = SourceText.from_bytes(text.encode())
    layout = analyze(source.lines)
    return build_outline(source.lines, layout, layout.notes[note_index]), [l.text for l in source.lines]


def describe(text: str) -> list[tuple[str, str, str, list[str]]]:
    """Hilfsfunktion: (Art, erste Zeile, Text der Elternzeile, effektive Tags) je Knoten."""
    outline, lines = outline_of(text)
    tags = compute_tags(outline)
    out = []
    for node in outline.nodes:
        first = lines[node.lines[0]] if node.lines else "<implizit>"
        parent = outline.nodes[node.parent] if node.parent is not None else None
        parent_text = (lines[parent.lines[0]] if parent and parent.lines else "<implizit>") if parent else "-"
        out.append((node.kind.value, first, parent_text, sorted(tags[node.index].effective)))
    return out


CONCEPT_EXAMPLE = """Notiz-Thema (worum geht es?)

- teilpunkt

  - [ ] offenes todo des Teilpunkts

    - [ ] offenes teil-todo

- ==teilpunkt==

- [ ] offenes todo

  - [ ] offenes teil-todo

- [ ] ==offenes dringendes todo==

weiteres Thema zur gleichen Notiz

- [x] erledigtes todo

- [ ] todo mit tag #tagname
"""


def test_concept_example_structure() -> None:
    """Das Konzeptbeispiel ergibt zwei Themen mit der erwarteten Verschachtelung."""
    rows = describe(CONCEPT_EXAMPLE)
    assert [r[0] for r in rows].count("topic") == 2
    pairs = [(r[1].strip(), r[2].strip()) for r in rows if r[0] == "item"]
    assert pairs == [
        ("- teilpunkt", "Notiz-Thema (worum geht es?)"),
        ("- [ ] offenes todo des Teilpunkts", "- teilpunkt"),
        ("- [ ] offenes teil-todo", "- [ ] offenes todo des Teilpunkts"),
        ("- ==teilpunkt==", "Notiz-Thema (worum geht es?)"),
        ("- [ ] offenes todo", "Notiz-Thema (worum geht es?)"),
        ("- [ ] offenes teil-todo", "- [ ] offenes todo"),
        ("- [ ] ==offenes dringendes todo==", "Notiz-Thema (worum geht es?)"),
        ("- [x] erledigtes todo", "weiteres Thema zur gleichen Notiz"),
        ("- [ ] todo mit tag #tagname", "weiteres Thema zur gleichen Notiz"),
    ]


def test_concept_example_status_and_urgency() -> None:
    """Status und Dringlichkeit der Konzept-Todos."""
    outline, lines = outline_of(CONCEPT_EXAMPLE)
    by_text = {lines[n.lines[0]].strip(): n.item for n in outline.items()}
    assert by_text["- [ ] ==offenes dringendes todo=="].urgent
    assert by_text["- [x] erledigtes todo"].status is TodoStatus.DONE
    assert by_text["- ==teilpunkt=="].status is TodoStatus.NONE


def test_topic_tag_inherited_and_ended_by_next_topic() -> None:
    """Konzept: Thema-Tag gilt für folgende Punkte, ein neues Thema ohne Tag beendet ihn."""
    text = ("Notiz-Thema mit einem tag #tagname\n- teilpunkt\n- [ ] offenes todo\n"
            "- [ ] todo mit zusätzlichem tag #anderertagname\n"
            "anderes Thema zur gleichen Notiz ohne den Tag\n- teilpunkt ohne den Tag\n")
    rows = {r[1]: r[3] for r in describe(text)}
    assert rows["- [ ] offenes todo"] == ["tagname"]
    assert rows["- [ ] todo mit zusätzlichem tag #anderertagname"] == ["anderertagname", "tagname"]
    assert rows["- teilpunkt ohne den Tag"] == []


def test_uni_example_from_concept() -> None:
    """Konzept: ``Thema #uni`` → das Todo trägt effektiv ``uni``."""
    rows = {r[1]: r[3] for r in describe("Thema #uni\n\n- Teilpunkt\n\n- [ ] Todo\n")}
    assert rows["- [ ] Todo"] == ["uni"]


def test_explanation_paragraph_belongs_to_topic() -> None:
    """Absatz vor dem ersten Punkt ist Erläuterung, nach Punkten ein neues Thema."""
    text = "Elternabend #schule\n\nVorher Raum klären #raum\n\n- [ ] Beamer\nweiteres Thema\n- [ ] Kopien\n"
    outline, lines = outline_of(text)
    topics = [n for n in outline.nodes if n.kind is NodeKind.TOPIC]
    assert [len(t.lines) for t in topics] == [2, 1]
    rows = {r[1]: r[3] for r in describe(text)}
    assert rows["- [ ] Beamer"] == ["raum", "schule"]
    assert rows["- [ ] Kopien"] == []


def test_item_tags_inherited_along_indentation() -> None:
    """Tags des Eltern-Punkts gelten für eingerückte Kinder, nicht für Geschwister."""
    rows = {r[1].strip(): r[3] for r in describe("T\n- a #x\n  - b\n\t- c\n- d\n")}
    assert rows["- b"] == ["x"] and rows["- c"] == ["x"] and rows["- d"] == []


def test_heading_tags_cover_topics_until_same_level() -> None:
    """Überschrift-Tags gelten für alle Themen darunter bis zur gleichrangigen Überschrift."""
    text = "# Woche #w\n## Mo\nThema A\n- [ ] a\nThema B\n- [ ] b\n# Andere\n- [ ] c\n"
    rows = {r[1]: r[3] for r in describe(text)}
    assert rows["- [ ] a"] == ["w"] and rows["- [ ] b"] == ["w"] and rows["- [ ] c"] == []


def test_heading_ends_topic() -> None:
    """Eine Überschrift beendet das aktuelle Thema (keine Vererbung darüber hinaus)."""
    rows = {r[1]: r[3] for r in describe("Thema #t\n- a\n## Abschnitt\n- b\n")}
    assert rows["- b"] == []


def test_setext_heading() -> None:
    """``Text`` + ``===``/``---`` direkt darunter ist eine Überschrift."""
    outline, _ = outline_of("Titel #h\n===\nThema\n- x\nUnter\n---\n- y\n")
    headings = [n for n in outline.nodes if n.kind is NodeKind.HEADING]
    assert [h.level for h in headings] == [1, 2]
    rows = {r[1]: r[3] for r in describe("Titel #h\n===\nThema\n- x\n")}
    assert rows["- x"] == ["h"]


def test_items_before_first_topic_use_implicit_topic() -> None:
    """Punkte vor dem ersten Thema hängen an einem impliziten Thema ohne Tags."""
    outline, _ = outline_of("- [ ] a\nThema #t\n- [ ] b\n")
    assert outline.nodes[0].implicit and outline.nodes[0].kind is NodeKind.TOPIC
    rows = {r[1]: r[3] for r in describe("- [ ] a\nThema #t\n- [ ] b\n")}
    assert rows["- [ ] a"] == [] and rows["- [ ] b"] == ["t"]


def test_orphan_indented_item_becomes_root_item() -> None:
    """GRENZE: Eingerückter Punkt ohne Eltern hängt flach am Thema."""
    outline, lines = outline_of("Thema\n    - [ ] eingerückt\n")
    item = outline.items()[0]
    assert outline.nodes[item.parent].kind is NodeKind.TOPIC


def test_continuation_line_belongs_to_item() -> None:
    """Eingerückte Zeile direkt nach einem Punkt ist dessen Fortsetzung (inkl. Tags)."""
    outline, _ = outline_of("Thema\n- [ ] a\n  weiter #f\n")
    item = outline.items()[0]
    assert item.lines == (1, 2)
    assert compute_tags(outline)[item.index].explicit == {"f"}


def test_code_block_is_opaque_and_starts_no_topic() -> None:
    """Codeblock: keine Tags, keine Todos, kein neues Thema."""
    text = "Thema #t\n- a\n```\n- [ ] kein todo #nein\n```\n- [ ] b\n"
    outline, _ = outline_of(text)
    assert len(outline.items()) == 2
    assert [n.kind for n in outline.nodes].count(NodeKind.TOPIC) == 1
    rows = {r[1]: r[3] for r in describe(text)}
    assert rows["- [ ] b"] == ["t"]


def test_quote_table_embed_are_other() -> None:
    """Zitat, Tabelle und Embed-Zeile beginnen nie ein Thema."""
    outline, _ = outline_of("Thema\n- a\n> zitat\n| t |\n![[bild.png]]\n- b\n")
    kinds = [n.kind for n in outline.nodes]
    assert kinds.count(NodeKind.OTHER) == 3 and kinds.count(NodeKind.TOPIC) == 1


def test_projects_explicit_and_inherited() -> None:
    """Projekte erben wie Tags; ``inherited_projects`` trennt geerbte von expliziten."""
    outline, _ = outline_of("Umzug #projekt/Umzug\n- [ ] Kisten #projekt/Keller\n")
    tags = compute_tags(outline)
    item = outline.items()[0]
    assert tags[item.index].explicit_projects == ("Keller",)
    assert tags[item.index].effective_projects == ("Keller", "Umzug")
    assert tags[item.index].inherited_projects == ("Umzug",)


def test_tags_are_case_insensitive() -> None:
    """``#Uni`` und ``#uni`` sind derselbe Tag."""
    rows = {r[1]: r[3] for r in describe("Thema #Uni\n- [ ] a #UNI\n")}
    assert rows["- [ ] a #UNI"] == ["uni"]


def test_second_note_is_independent() -> None:
    """Tags enden an der Notizgrenze."""
    outline, lines = outline_of("Thema #t\n- a\n\n---\n\n- [ ] b\n", note_index=1)
    assert compute_tags(outline)[outline.items()[0].index].effective == frozenset()
