"""W7 Phase 6: verwendete Tags, Suche und Einfügen (UI-neutral)."""

from pathlib import Path

import pytest

from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings
from merkweiser.app.tag_index import INVALID_PATTERN, filter_tags, used_tags
from merkweiser.app.text_tools import insert_tag, insert_tag_name
from merkweiser.core.query import Filter
from tests.fakes import FakeClock


@pytest.fixture
def service(tmp_path: Path) -> NotesService:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-14.md").write_text("Elternabend #Schule\n- [ ] Brief\n- [ ] Raum #raum\n\n"
                                        "Code\n- `#nichtig` im Code\n", encoding="utf-8")
    (root / "2026-01-15.md").write_text("Heute #schule\n- [ ] a #Raum\n- [ ] b #raum #zeta\n", encoding="utf-8")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    return svc


def test_counts_like_search_spelling_and_order(service) -> None:
    tags = used_tags(service)
    names = [name for name, _count in tags]
    assert "nichtig" not in names  # in Code kein Tag
    for name, count in tags:
        assert count == len(service.search(Filter(tags=(name,))))  # Konvention von ``tag_check``: Einträge
    assert names[:2] == ["Schule", "raum"]  # 6 Einträge (geerbt) vor 3; häufigste Schreibweise, Gleichstand alphabetisch
    assert tags[-1] == ("zeta", 1)


def test_cache_follows_own_and_external_changes(service) -> None:
    first = used_tags(service)
    assert used_tags(service) is first  # unverändert → Zwischenspeicher
    service.append_note("Neu #frisch\n- [ ] x")
    assert ("frisch", 2) in used_tags(service)
    (service.root / "2026-01-14.md").write_text("Nur noch\n- [ ] #anders y\n", encoding="utf-8")
    names = [n for n, _c in used_tags(service)]
    assert ("anders", 1) in used_tags(service) and "schule" in names and "Schule" not in names  # Schreibweise neu


def test_filter_regex_invalid_and_empty() -> None:
    tags = [("Schule", 6), ("raum", 3), ("Raumplan", 1)]
    assert filter_tags(tags, "") == (tags, "")
    assert filter_tags(tags, "#^raum$") == ([("raum", 3)], "")
    assert filter_tags(tags, "SCH") == ([("Schule", 6)], "")
    assert filter_tags(tags, "raum(") == ([], INVALID_PATTERN)
    assert filter_tags([("x(1", 1)], "X(") == ([("x(1", 1)], INVALID_PATTERN)  # Teilstring statt Regex


@pytest.mark.parametrize("text, start, end, name, expected", [
    ("Thema\n- [ ] Brief", 9, 9, "schule", ("Thema\n- [ ] Brief #schule", 25)),           # Caret → Zeilenende
    ("- [ ] Brief ", 2, 2, "schule", ("- [ ] Brief #schule", 19)),                      # kein doppeltes Leerzeichen
    ("- [ ] Brief Schule", 12, 18, "schule", ("- [ ] Brief #Schule", 19)),              # Wort am Zeilenende → an Ort und Stelle
    ("- [ ] Schule Brief", 6, 12, "schule", ("- [ ] Schule Brief #schule", 26)),        # mitten in der Zeile → ans Ende
    ("- [ ] Brief Schule", 12, 18, "raum", ("- [ ] Brief Schule #raum", 24)),           # anderer Tag → ans Ende
    ("- [ ] Brief #Schule", 2, 2, "schule", ("- [ ] Brief #Schule", 2)),                # schon da → unverändert
    ("- [ ] `#schule` x", 2, 2, "schule", ("- [ ] `#schule` x #schule", 25)),           # in Code zählt nicht
    ("a\nb c\nd", 2, 6, "t", ("a\nb c #t\nd", 8)),                                      # mehrzeilig: erste Zeile
    ("- [ ] Brief Sch", 12, 15, "schule", ("- [ ] Brief Sch #schule", 23)),             # Teilwort ≠ Tag → ans Ende
])
def test_insert_tag_name(text, start, end, name, expected) -> None:
    new_text, new_start, new_end = insert_tag_name(text, start, end, name)
    assert (new_text, new_start) == expected and new_start == new_end


def test_insert_tag_name_without_position_and_old_insert_tag_unchanged() -> None:
    assert insert_tag_name("x", None, None, "t") == ("x", None, None)
    assert insert_tag("a b", 2, 3) == ("a #b", 3, 4)  # Desktop/Tests: altes Verhalten bleibt
    assert insert_tag("a", 1, 1) == ("a #", 3, 3)
