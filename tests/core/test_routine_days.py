"""Tests für die reine Planung von Routinen-Instanzen in Tagesdateien (W9, ``core/routine_days.py``)."""

from merkweiser.core.document import parse_document
from merkweiser.core.patch import Target
from merkweiser.core.routine_days import expire_lines, present, plan_day


def doc(text: str):
    """Dokument aus synthetischem Text."""
    return parse_document(text.encode())


def test_present_ignores_state_tags_urgency_and_case() -> None:
    """Jeder Todo-Zustand zählt; Tags, Ampel und Schreibung egal; nur unter dem passenden Thema."""
    day = doc("täglich\n- [-] ==🔴Mails  CHECKEN== #privat #wdh\n\nAnderes\n- [ ] Lesen #wdh\n```\n- [ ] Code\n```\n")
    assert present(day, "täglich", "Mails checken")
    assert not present(day, "täglich", "Lesen") and not present(day, "werktags", "Mails checken")


def test_plan_day_groups_per_topic_and_is_idempotent() -> None:
    """Fehlende Instanzen je Thema als Block; vorhandene bleiben; zweiter Lauf ändert nichts."""
    entries = [("täglich", "a", "- [ ] a #wdh"), ("werktags", "b", "- [ ] b #wdh"), ("täglich", "c", "- [ ] c #wdh")]
    first = plan_day(doc("Notiz\n- x\n\ntäglich\n- [x] a #wdh\n"), entries)
    assert first.decode() == "Notiz\n- x\n\ntäglich\n- [x] a #wdh\n- [ ] c #wdh\n\nwerktags\n- [ ] b #wdh\n"
    assert plan_day(parse_document(first), entries) == first


def test_expire_lines_skips_changed_targets() -> None:
    """Nur unveränderte offene Ziele werden ``[-]``; inzwischen abgehakte bleiben."""
    day = doc("täglich\n- [ ] a #wdh\n- [x] b #wdh\n")
    after = expire_lines(day, [Target("x.md", 1, "- [ ] a #wdh"), Target("x.md", 2, "- [ ] b #wdh")])
    assert after.decode() == "täglich\n- [-] a #wdh\n- [x] b #wdh\n"
