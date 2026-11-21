"""W10: Tab „Todos“ als Todo-Bäume – Unter-Todos stehen unter ihrem obersten Eltern-Todo (UI-neutral)."""

from pathlib import Path

from merkweiser.app.notes_service import NotesService
from merkweiser.app.notify_content import content
from merkweiser.app.settings import Settings
from merkweiser.app.todo_list import DEFAULT_FILTER, fold_keep, todo_sections
from merkweiser.core.inline import TodoStatus
from tests.fakes import FakeClock

TODAY = ("Heute\n- [x] Eltern erledigt\n  - [ ] offen unten\n  - Punkt\n    - [ ] ==🔴tief rot==\n"
         "- [ ] Wurzel\n  - [x] erledigt unten\n- [ ] allein\n")


def started(tmp_path: Path, text: str = TODAY) -> NotesService:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-15.md").write_text(text, encoding="utf-8")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    return svc


def sections(svc: NotesService, **changes):
    return todo_sections(svc, {**DEFAULT_FILTER, **changes})


def test_sub_todos_are_no_own_entries_and_done_roots_are_shown(tmp_path: Path) -> None:
    """Offene Unter-Todos einer erledigten Wurzel: ein Eintrag (die Wurzel); rotes Unter-Todo → „Sehr dringend“."""
    result = sections(started(tmp_path))
    assert [(title, [r.text for r in rows]) for title, rows in result] == [
        ("Sehr dringend (1)", ["Eltern erledigt"]), ("Heute (2)", ["Wurzel", "allein"])]
    tree = result[0][1][0].tree
    assert [(r.text, r.depth) for r in tree] == [
        ("Eltern erledigt", 0), ("offen unten", 1), ("Punkt", 1), ("==🔴tief rot==", 2)]
    assert result[0][1][0].status is TodoStatus.DONE


def test_root_with_only_done_children_lists_them_in_its_tree(tmp_path: Path) -> None:
    """Die Wurzel passt zum Filter, ihr erledigtes Kind nicht – es steht trotzdem im Baum (eingeklappt)."""
    heute = dict(sections(started(tmp_path)))["Heute (2)"]
    assert [r.text for r in heute[0].tree] == ["Wurzel", "erledigt unten"]
    assert heute[1].tree[0].text == "allein" and len(heute[1].tree) == 1


def test_filter_done_groups_done_sub_todos_under_their_open_root(tmp_path: Path) -> None:
    result = sections(started(tmp_path), status="erledigt")
    assert [r.text for _t, rows in result for r in rows] == ["Eltern erledigt", "Wurzel"]


def test_fold_keep_follows_the_status_filter() -> None:
    assert fold_keep(dict(DEFAULT_FILTER)) == {TodoStatus.OPEN}
    assert fold_keep({**DEFAULT_FILTER, "status": "verpasst"}) == {TodoStatus.OPEN, TodoStatus.MISSED}
    assert fold_keep({**DEFAULT_FILTER, "status": "alle"}) == {TodoStatus.OPEN, TodoStatus.DONE, TodoStatus.MISSED}


def test_notification_stays_a_flat_list(tmp_path: Path) -> None:
    """Nutzerentscheidung: Die Benachrichtigung zeigt Unter-Todos weiterhin einzeln."""
    lines = content(started(tmp_path), FakeClock().today()).lines
    assert any("tief rot" in line for line in lines) and any("offen unten" in line for line in lines)
