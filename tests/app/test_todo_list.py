"""W7 Phase 5: Tab „Todos“ – Filter-Standard, Abschnitte, Zusammenfassung (UI-neutral)."""

from pathlib import Path

import pytest

from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings
from merkweiser.app.todo_list import DEFAULT_FILTER, changed_count, filter_summary, tag_list, todo_sections
from tests.fakes import FakeClock

FILES = {  # FakeClock: heute = 2026-01-15
    "2026-01-13.md": "Alt #schule\n- [ ] alt normal\n- [ ] ==alt gelb==\n- [x] ==🔴alt rot erledigt==\n",
    "2026-01-15.md": "Heute\n- [ ] heute normal\n- [ ] ==🔴heute rot==\n- [x] heute erledigt\n",
    "2026-01-16.md": "Morgen #schule\n- [ ] morgen normal\n- [ ] ==morgen gelb==\n",
    "2026-01-20.md": "Später\n- [ ] ==🔴später rot==\n",
}


@pytest.fixture
def service(tmp_path: Path) -> NotesService:
    root = tmp_path / "vault"
    root.mkdir()
    for name, text in FILES.items():
        (root / name).write_text(text, encoding="utf-8")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    return svc


def view(svc: NotesService, **changes) -> list[tuple[str, list[str]]]:
    state = {**DEFAULT_FILTER, **changes}
    return [(title, [row.text for row in rows]) for title, rows in todo_sections(svc, state)]


def test_default_hides_the_future_and_separates_today_from_the_past(service) -> None:
    assert view(service) == [("Sehr dringend (1)", ["==🔴heute rot=="]),
                             ("Heute (1)", ["heute normal"]),
                             ("Frühere Tage (2)", ["==alt gelb==", "alt normal"])]


def test_future_only_and_both(service) -> None:
    assert view(service, zeitraum="zukünftig") == [("Sehr dringend (1)", ["==🔴später rot=="]),
                                                   ("Zukünftig (2)", ["==morgen gelb==", "morgen normal"])]
    assert [title for title, _rows in view(service, zeitraum="beides")] == [
        "Sehr dringend (2)", "Zukünftig (2)", "Heute (1)", "Frühere Tage (2)"]
    assert view(service, zeitraum="beides")[0][1] == ["==🔴heute rot==", "==🔴später rot=="]


@pytest.mark.parametrize("status, expected", [
    ("erledigt", [("Heute (1)", ["heute erledigt"]), ("Frühere Tage (1)", ["==🔴alt rot erledigt=="])]),
    ("alle", [("Sehr dringend (1)", ["==🔴heute rot=="]), ("Heute (2)", ["heute normal", "heute erledigt"]),
              ("Frühere Tage (3)", ["==alt gelb==", "alt normal", "==🔴alt rot erledigt=="])]),
])
def test_done_red_todos_stay_visible_in_their_day(service, status, expected) -> None:
    assert view(service, status=status) == expected


def test_tags_and_empty_result(service) -> None:
    assert view(service, tags="#schule", zeitraum="beides") == [
        ("Zukünftig (2)", ["==morgen gelb==", "morgen normal"]), ("Frühere Tage (2)", ["==alt gelb==", "alt normal"])]
    assert view(service, tags="gibtsnicht") == []


def test_summary_badge_and_tag_parsing() -> None:
    assert filter_summary(dict(DEFAULT_FILTER)) == "offen · bis heute" and changed_count(dict(DEFAULT_FILTER)) == 0
    state = {"status": "alle", "zeitraum": "beides", "tags": "#schule  elternabend", "oder": True}
    assert filter_summary(state) == "alle · alle Tage · #schule #elternabend · ODER" and changed_count(state) == 4
    assert changed_count({"status": "offen", "tags": "   "}) == 0  # fehlender Zeitraum = Standard
    assert tag_list("#a  b # #") == ("a", "b")
