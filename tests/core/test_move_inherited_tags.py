"""W7 Phase 2: Kein Tag-Dialog, wenn das Todo schon einen Tag erbt."""

from merkweiser.core.document import parse_document
from merkweiser.core.move_plan import move_context, plan_move
from merkweiser.core.patch import Target


def context(text: str, line: str):
    doc = parse_document(text.encode())
    return move_context(doc, Target("x.md", text.split("\n").index(line), line))


def test_inherited_from_topic_or_parent_item_skips_the_dialog() -> None:
    by_topic = context("Elternabend #schule\n- [ ] eins\n- [ ] zwei\n", "- [ ] zwei")
    assert by_topic.inherited_tags == ("schule",) and not by_topic.needs_tag_dialog
    by_parent = context("Thema\n- Planung #Umzug\n  - [ ] eins\n- [ ] zwei\n", "  - [ ] eins")
    assert by_parent.inherited_tags == ("Umzug",) and not by_parent.needs_tag_dialog


def test_without_inherited_tag_the_dialog_stays() -> None:
    plain = context("Thema\n- [ ] eins #eigen\n- [ ] zwei\n", "- [ ] eins #eigen")
    assert plain.inherited_tags == () and plain.needs_tag_dialog  # ein eigener Tag zählt nicht als geerbt
    sole = context("Thema\n- [ ] allein\n", "- [ ] allein")
    assert sole.sole_todo and not sole.needs_tag_dialog


def test_the_moved_todo_keeps_an_inherited_parent_tag_explicitly() -> None:
    text = "Thema\n- Planung #Umzug\n  - [ ] Kisten\n- [ ] zwei\n"
    doc = parse_document(text.encode())
    plan = plan_move(doc, Target("x.md", 2, "  - [ ] Kisten"))
    assert plan.moved_lines == ("- [ ] Kisten #Umzug",)
