"""Tests für die Vorschau kommender Routinen, vorzeitiges Abhaken und Benachrichtigung (W9 P5).

Synthetischer Vault, ``FakeClock`` (heute = Do, 15.01.2026).
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

from merkweiser.app.notify_content import content
from merkweiser.app.routine_preview import preview_rows
from merkweiser.app.routine_service import check_preview, run_due
from merkweiser.app.todo_list import DEFAULT_FILTER, criteria, todo_sections
from merkweiser.core.query import Filter, StatusFilter
from tests.app.test_routine_service import make, read

RULES = "## täglich\n- [ ] Mails\n\n## wöchentlich Fr #privat\n- [ ] ==🔴Einkauf==\n"
TODAY = date(2026, 1, 15)


def rows(service, **state):
    """Vorschauzeilen für einen Filterzustand des Todos-Tabs."""
    return preview_rows(service, criteria({**DEFAULT_FILTER, **state}, TODAY), TODAY)


def test_preview_window_and_range_filter(tmp_path: Path) -> None:
    """Nach dem Eintragen: keine Vorschau „bis heute“; „ab morgen“ 7 Tage, mit Thema als Kontext."""
    service = make(tmp_path, {"Routinen.md": RULES})
    service.start()
    assert rows(service) == []
    future = rows(service, zeitraum="zukünftig")
    assert [(r.day, r.text) for r in future if r.text == "Mails #wdh"][0] == ("2026-01-16", "Mails #wdh")
    assert {r.day for r in future} == {f"2026-01-{d}" for d in range(16, 23)}
    assert all(r.target is None and r.preview is not None for r in future)
    einkauf = [r for r in future if "Einkauf" in r.text]
    assert [r.day for r in einkauf] == ["2026-01-16"] and einkauf[0].context == "wöchentlich Fr"


def test_preview_uses_the_same_filters(tmp_path: Path) -> None:
    """Tags (geerbt), Status und Ampel filtern wie bei echten Todos."""
    service = make(tmp_path, {"Routinen.md": RULES})
    service.start()
    assert {r.text for r in rows(service, zeitraum="zukünftig", tags="privat")} == {"==🔴Einkauf== #privat #wdh"}
    assert rows(service, zeitraum="zukünftig", status="erledigt") == []
    assert len(rows(service, zeitraum="zukünftig", tags="wdh")) == 8


def test_red_preview_is_very_urgent_and_setting_limits_days(tmp_path: Path) -> None:
    """Rote Vorschau steht unter „Sehr dringend“; ``routine_preview_days`` begrenzt das Fenster."""
    service = make(tmp_path, {"Routinen.md": RULES})
    service.start()
    sections = dict(todo_sections(service, {**DEFAULT_FILTER, "zeitraum": "beides"}))
    assert [r.text for r in sections["Sehr dringend (1)"]] == ["==🔴Einkauf== #privat #wdh"]
    service.settings = replace(service.settings, routine_preview_days=1)
    assert {r.day for r in rows(service, zeitraum="zukünftig")} == {"2026-01-16"}


def test_not_yet_written_today_shows_as_preview(tmp_path: Path) -> None:
    """Heute noch nicht eingetragen (z. B. vor dem Durchlauf): heutige Instanzen erscheinen „bis heute“."""
    service = make(tmp_path, {"Routinen.md": RULES})
    assert [(r.day, r.text) for r in rows(service)] == [("2026-01-15", "Mails #wdh")]


def test_early_check_writes_done_and_hides_preview(tmp_path: Path) -> None:
    """Vorzeitig abhaken: ``[x]`` in die Datei des Tages unter dem Thema; Vorschau weg; Durchlauf ohne Duplikat."""
    service = make(tmp_path, {"Routinen.md": RULES})
    service.start()
    [friday] = [r for r in rows(service, zeitraum="zukünftig") if "Einkauf" in r.text]
    check_preview(service, friday.preview)
    assert read(service, "2026-01-16.md") == "wöchentlich Fr\n- [x] ==🔴Einkauf== #privat #wdh\n"
    assert not [r for r in rows(service, zeitraum="zukünftig") if "Einkauf" in r.text]
    service.clock.jump_wall(86400)
    run_due(service)
    assert read(service, "2026-01-16.md") == ("wöchentlich Fr\n- [x] ==🔴Einkauf== #privat #wdh\n\n"
                                              "täglich\n- [ ] Mails #wdh\n")


def test_notification_includes_planned_day_instances(tmp_path: Path) -> None:
    """Die Benachrichtigung für morgen enthält die noch nicht eingetragenen Instanzen von morgen."""
    service = make(tmp_path, {"Routinen.md": RULES})
    service.start()
    lines = content(service, date(2026, 1, 16)).lines
    assert "🔥 Einkauf #privat #wdh (16.01.)" in lines and "• Mails #wdh" in lines
    assert content(service, date(2026, 1, 16)).red == 1
    assert preview_rows(service, Filter(nur_todos=True, status=StatusFilter.OFFEN, bis=TODAY), TODAY, last=TODAY) == []


def test_preview_days_setting_is_validated() -> None:
    """``routine_preview_days``: 1 bis 31, Standard 7."""
    import pytest

    from merkweiser.app.settings import Settings
    assert Settings().routine_preview_days == 7 and Settings(routine_preview_days=31).validated()
    for bad in (0, 32):
        with pytest.raises(ValueError, match="Vorschau"):
            Settings(routine_preview_days=bad).validated()
