"""Tests für Suche und Filter (Semantik identisch für Desktop und Mobile)."""

import os
from datetime import date
from pathlib import Path

import pytest

from merkweiser.core.doc_cache import DocumentCache
from merkweiser.core.document import parse_document
from merkweiser.core.inline import TodoStatus
from merkweiser.core.query import (
    Filter, InvalidQuery, StatusFilter, TagMode, TextMode, TextQuery, UrgentFilter, search,
)

DAY1 = """Uni #uni

Erläuterung #klausur

- [ ] Lernen
- [x] Anmelden
- [ ] ==Dringend abgeben==
- Notiz ohne Checkbox
- [-] abgebrochen

Umzug #projekt/Umzug
- [ ] Kisten packen #keller
"""

DAY2 = """Uni #uni
- [ ] Skript lesen
"""


def docs() -> list:
    """Synthetische Dokumente für zwei Tage."""
    return [("2026-01-01.md", date(2026, 1, 1), parse_document(DAY1.encode())),
            ("2026-01-02.md", date(2026, 1, 2), parse_document(DAY2.encode()))]


def texts(criteria: Filter) -> list[str]:
    """Hilfsfunktion: getrimmte Treffertexte."""
    return [hit.text.strip() for hit in search(docs(), criteria)]


def test_empty_filter_returns_all_visible_nodes() -> None:
    """Ohne Kriterien: alle Knoten außer impliziten Themen."""
    assert len(texts(Filter())) == 10


def test_todo_view_excludes_other_status_and_plain_items() -> None:
    """``nur_todos``: ``[-]`` und Punkte ohne Checkbox sind keine Todos."""
    assert texts(Filter(nur_todos=True)) == [
        "- [ ] Lernen", "- [x] Anmelden", "- [ ] ==Dringend abgeben==", "- [ ] Kisten packen #keller",
        "- [ ] Skript lesen"]


def test_status_and_urgency_imply_todos_and_combine() -> None:
    """Status und Dringlichkeit filtern nur Todos und werden UND-verknüpft."""
    assert texts(Filter(status=StatusFilter.ERLEDIGT)) == ["- [x] Anmelden"]
    assert texts(Filter(status=StatusFilter.OFFEN, dringend=UrgentFilter.JA)) == ["- [ ] ==Dringend abgeben=="]
    assert "- [x] Anmelden" not in texts(Filter(dringend=UrgentFilter.NEIN, status=StatusFilter.OFFEN))


def test_tags_use_effective_tags_with_and_or() -> None:
    """Effektive Tags (Thema + Erläuterung) mit UND bzw. ODER."""
    both = texts(Filter(tags=("uni", "klausur"), nur_todos=True))
    assert both == ["- [ ] Lernen", "- [x] Anmelden", "- [ ] ==Dringend abgeben=="]
    either = texts(Filter(tags=("#klausur", "keller"), tag_modus=TagMode.ODER, nur_todos=True))
    assert either == both + ["- [ ] Kisten packen #keller"]


def test_project_filter_uses_inherited_projects() -> None:
    """Projektfilter greift auch für geerbte Projekte, ohne Groß-/Kleinschreibung."""
    hits = search(docs(), Filter(projekt="umzug", nur_todos=True))
    assert [h.text for h in hits] == ["- [ ] Kisten packen #keller"]
    assert hits[0].inherited_projects == ("Umzug",)


def test_text_modes_are_explicit_and_identical_everywhere() -> None:
    """Teilstring (Standard, ohne Groß-/Kleinschreibung) und Regex als expliziter Modus."""
    assert texts(Filter(text=TextQuery("SKRIPT"))) == ["- [ ] Skript lesen"]
    assert texts(Filter(text=TextQuery("^- \\[x\\]", TextMode.REGEX))) == ["- [x] Anmelden"]
    assert texts(Filter(text=TextQuery("^- \\[x\\]"))) == []  # als Teilstring kein Treffer


def test_invalid_regex_raises() -> None:
    """Ungültiger Regex → ``InvalidQuery`` (UI zeigt Fehler, filtert nicht)."""
    with pytest.raises(InvalidQuery):
        search(docs(), Filter(text=TextQuery("(", TextMode.REGEX)))


def test_date_range_is_inclusive() -> None:
    """``von``/``bis`` sind inklusiv."""
    only_day2 = texts(Filter(von=date(2026, 1, 2), bis=date(2026, 1, 2), nur_todos=True))
    assert only_day2 == ["- [ ] Skript lesen"]


def test_hit_context_and_status() -> None:
    """Treffer tragen Kontextpfad, Status und effektive Tags."""
    hit = search(docs(), Filter(text=TextQuery("Lernen")))[0]
    assert hit.context == ("Uni #uni",)
    assert hit.status is TodoStatus.OPEN and hit.tags == ("klausur", "uni")


def test_document_cache_rereads_only_changed_files(tmp_path: Path) -> None:
    """Der Cache liest neu, sobald sich ``(mtime_ns, size)`` ändern."""
    path = tmp_path / "2026-01-01.md"
    path.write_bytes(b"T\n- [ ] a\n")
    cache = DocumentCache(tmp_path)
    first = cache.get("2026-01-01.md")
    assert cache.get("2026-01-01.md") is first
    path.write_bytes(b"T\n- [ ] a\n- [ ] b\n")
    os.utime(path, ns=(1, 2_000_000_000))
    assert len(cache.get("2026-01-01.md").notes[0].outline.items()) == 2
    path.unlink()
    with pytest.raises(FileNotFoundError):
        cache.get("2026-01-01.md")
