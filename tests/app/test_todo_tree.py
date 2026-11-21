"""Tests für den Zeilenbaum und die Faltregel einklappbarer Todos (W10)."""

from merkweiser.app.todo_tree import fold_key, fold_rows, flatten, hidden, outline_tree
from merkweiser.app.views import Row
from merkweiser.core.inline import TodoStatus, Urgency
from merkweiser.core.patch import Target

OPEN, DONE, MISSED = TodoStatus.OPEN, TodoStatus.DONE, TodoStatus.MISSED


def row(text: str, depth: int, status: TodoStatus | None = OPEN) -> Row:
    """Zeile (``status=None``: Punkt ohne Checkbox)."""
    return Row("todo" if status else "item", text, depth, status, Urgency.NONE, (), Target("t.md", 0, text))


def shown(folds) -> list[str]:
    """Texte, die eingeklappt sichtbar sind."""
    return [t for f in folds if f.pinned for t in (f.row.text, *shown(f.children))]


def test_outline_tree_round_trips() -> None:
    rows = [row("T", 0, None), row("a", 1), row("a1", 2), row("b", 1)]
    tree = outline_tree(rows)
    assert [f.row.text for f in tree] == ["T"] and [f.row.text for f in tree[0].children] == ["a", "b"]
    assert flatten(tree) == rows


def test_open_sub_todos_stay_done_missed_and_items_fold() -> None:
    """Offene Unter-Todos bleiben sichtbar; erledigte, verpasste und Punkte klappen ein."""
    rows = [row("Eltern", 0), row("offen", 1), row("erledigt", 1, DONE), row("verpasst", 1, MISSED),
            row("Punkt", 1, None)]
    (parent,) = fold_rows(rows)
    assert shown([parent]) == ["Eltern", "offen"] and hidden(parent) == 3
    assert [c.sub_todo for c in parent.children] == [True, True, True, False]


def test_open_todos_are_never_hidden() -> None:
    """Ein erledigtes Unter-Todo mit offenem Enkel bleibt sichtbar; der Enkel ist ein Unter-Todo über einen Punkt."""
    rows = [row("Eltern", 0), row("erledigt", 1, DONE), row("enkel", 2), row("Punkt", 1, None), row("unter Punkt", 2)]
    (parent,) = fold_rows(rows)
    assert shown([parent]) == ["Eltern", "erledigt", "enkel", "Punkt", "unter Punkt"]
    assert parent.children[1].children[0].sub_todo


def test_non_todo_parents_do_not_fold_and_keep_is_configurable() -> None:
    rows = [row("Punkt", 0, None), row("erledigt", 1, DONE), row("Todo", 0), row("x", 1, DONE)]
    folds = fold_rows(rows)
    assert hidden(folds[0]) == 0 and not folds[0].children[0].sub_todo
    assert hidden(folds[1]) == 1
    assert hidden(fold_rows(rows, frozenset({OPEN, DONE}))[1]) == 0


def test_nested_sub_todos_fold_on_each_level() -> None:
    rows = [row("A", 0), row("B", 1), row("B erledigt", 2, DONE), row("A erledigt", 1, DONE)]
    (a,) = fold_rows(rows)
    assert hidden(a) == 1 and hidden(a.children[0]) == 1 and shown([a]) == ["A", "B"]


def test_fold_key_ignores_the_checkbox_state() -> None:
    assert fold_key(row("Antrag", 0)) == fold_key(row("Antrag", 0, DONE)) == ("t.md", "Antrag")
