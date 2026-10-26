"""Tests für W1 (dringend zuerst), W2 (Tag-Stücke) und die Navigation je Tab (1.6)."""

from merkweiser.app.nav import Nav, PageRef
from merkweiser.app.ordering import by_rank, rank, urgent_first
from merkweiser.app.tag_spans import text_parts
from merkweiser.app.views import Row
from merkweiser.core.inline import Urgency


def row(text: str, depth: int, urgent: bool | Urgency = False, done: bool | None = False) -> Row:
    """Zeile mit Text, Tiefe und Todo-Zustand (``done=None``: kein Todo)."""
    level = Urgency(int(urgent))
    return Row("todo" if done is not None else "item", text, depth, done, level, (), None)


def texts(rows) -> list[str]:
    return [r.text for r in rows]


def test_urgent_subtrees_move_up_per_sibling_group_and_keep_children() -> None:
    """Dringender Teilbaum rückt in seiner Geschwistergruppe nach oben, Kinder bleiben dran und werden selbst sortiert."""
    rows = [row("Thema", 0, done=None), row("a", 1), row("a1", 2), row("b", 1, urgent=True),
            row("b1", 2), row("b2", 2, urgent=True), row("c", 1)]
    assert texts(urgent_first(rows)) == ["Thema", "b", "b2", "b1", "a", "a1", "c"]


def test_sorting_is_stable_and_ignores_done_urgent() -> None:
    """Gleiche Dringlichkeit behält die Reihenfolge; erledigte dringende Todos rücken nicht nach oben."""
    rows = [row("x", 0), row("erledigt", 0, urgent=True, done=True), row("y", 0, urgent=True),
            row("z", 0), row("w", 0, urgent=True)]
    assert texts(urgent_first(rows)) == ["y", "w", "x", "erledigt", "z"]
    assert rank(row("erledigt", 0, urgent=True, done=True)) == 0


def test_by_rank_keeps_relative_order() -> None:
    assert by_rank([1, 2, 3, 4, 5], lambda x: x % 2) == [1, 3, 5, 2, 4]
    assert by_rank("abcd", lambda c: {"c": 2, "b": 1}.get(c, 0)) == ["c", "b", "a", "d"]


def test_text_parts_marks_tags_like_the_parser() -> None:
    """Tags wie beim Parsen: Wortanfang, nicht nur Ziffern, nicht in Code; Stücke ergeben den Text."""
    text = "Elternabend #Schule und `#code` #123 #projekt/Bau."
    parts = text_parts(text)
    assert "".join(p for p, _ in parts) == text
    assert [(p, t) for p, t in parts if t] == [("#Schule", "schule"), ("#projekt/Bau", "projekt/bau")]
    assert text_parts("ohne") == [("ohne", None)]


def test_nav_keeps_stack_per_tab_across_switches() -> None:
    """Tag-Seite in Todos öffnen → Suche → zurück zu Todos: die Tag-Seite ist noch da."""
    nav = Nav(5)
    nav.select(1)
    nav.push(PageRef("tag", "schule"))
    nav.select(2)
    assert nav.top() is None
    nav.select(1)
    assert nav.top() == PageRef("tag", "schule")


def test_nav_back_only_affects_current_tab_and_falls_back_home() -> None:
    """Zurück: erst die Unterseite des aktuellen Tabs, dann zum Start-Tab, dort dem System."""
    nav = Nav(5)
    nav.push(PageRef("tag", "a"))
    nav.select(1)
    nav.push(PageRef("tag", "b"))
    nav.push(PageRef("tag", "c"))
    assert nav.back() and nav.top() == PageRef("tag", "b")
    assert nav.depth(0) == 1  # Stapel des Tabs „Tag“ unberührt
    assert nav.back() and nav.top() is None and nav.current == 1
    assert nav.back() and nav.current == 0 and nav.top() == PageRef("tag", "a")
    assert nav.back() and nav.top() is None
    assert not nav.back()


def test_nav_reselect_and_show_root() -> None:
    """Erneutes Wählen des aktiven Tabs und ``show_root`` springen zur Wurzel."""
    nav = Nav(5)
    nav.push(PageRef("tag", "a"))
    nav.select(0)
    assert nav.top() is None
    nav.select(2)
    nav.push(PageRef("tag", "x"))
    nav.show_root(2)
    assert nav.current == 2 and nav.depth() == 0
