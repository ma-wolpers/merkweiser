"""Tests für Vault-Scan, Konfliktnamen, Schreibziel, Snapshot und Dokument-Fassade."""

from datetime import date
from pathlib import Path

import pytest

from merkweiser.core.document import parse_document
from merkweiser.core.textfile import read_snapshot
from merkweiser.core.vault import (
    AmbiguousDayFile, DayPattern, PatternError, parse_conflict_name, scan, write_target,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def make_vault(root: Path, files: list[str]) -> Path:
    """Hilfsfunktion: legt synthetische Dateien an (Inhalt = Pfad)."""
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")
    return root


@pytest.mark.parametrize("name, expected", [
    ("2026-10-08.md", date(2026, 10, 8)),
    ("2026-10-08 Elternabend.md", None),
    ("x2026-10-08.md", None),
    ("2026-02-30.md", None),
    ("2026-10-08.txt", None),
])
def test_default_pattern_matches_whole_name(name: str, expected: date | None) -> None:
    """Nur der ganze Dateiname zählt; ungültige Daten werden ignoriert."""
    assert DayPattern().parse(name) == expected


def test_custom_pattern_roundtrip() -> None:
    """Eigenes Muster: Formatieren und Parsen sind invers."""
    pattern = DayPattern("Tag %d.%m.%Y.md")
    assert pattern.format(date(2026, 1, 5)) == "Tag 05.01.2026.md"
    assert pattern.parse("Tag 05.01.2026.md") == date(2026, 1, 5)


@pytest.mark.parametrize("bad", ["%Y-%m.md", "%Y-%m-%d-%d.md", "%Y/%m/%d.md", "%Y-%m-%d-%H.md"])
def test_invalid_patterns(bad: str) -> None:
    """Fehlende, doppelte oder fremde Platzhalter und Ordner sind verboten."""
    with pytest.raises(PatternError):
        DayPattern(bad)


@pytest.mark.parametrize("relpath, main, nested, own, decided", [
    ("a/2026-10-08.sync-conflict-20261008-101500-ABCDEFG.md", "a/2026-10-08.md", False, False, False),
    ("2026-10-08.sync-conflict-20261008-101500-AAAAAAA.sync-conflict-20261009-080000-BBBBBBB.md",
     "2026-10-08.md", True, False, False),
    ("2026-10-08.sync-conflict-20261008-101500-MERKWEISERK7Q2ZD3A.md", "2026-10-08.md", False, True, False),
    ("2026-10-08.sync-conflict-20261008-101500-ABCDEFGMWENTSCHIEDEN.md", "2026-10-08.md", False, False, True),
])
def test_conflict_names(relpath: str, main: str, nested: bool, own: bool, decided: bool) -> None:
    """Hauptdatei ohne alle Segmente; verschachtelt, eigen und entschieden werden erkannt."""
    conflict = parse_conflict_name(relpath)
    assert conflict is not None
    assert (conflict.main_relpath, conflict.nested, conflict.own, conflict.decided) == (main, nested, own, decided)


def test_conflict_stamp_is_outermost_segment() -> None:
    """Bei verschachtelten Konflikten zählt der äußerste Zeitstempel."""
    name = "x.sync-conflict-20261008-101500-AAAAAAA.sync-conflict-20261009-080000-BBBBBBB.md"
    conflict = parse_conflict_name(name)
    assert conflict is not None and (conflict.stamp, conflict.device) == ("20261009-080000", "BBBBBBB")


def test_non_markdown_conflicts_are_ignored() -> None:
    """Konfliktdateien anderer Typen gehen Merkweiser nichts an (GRENZE)."""
    assert parse_conflict_name(".obsidian/app.sync-conflict-20260410-102239-ZR3GOFG.json") is None


def test_scan_finds_days_duplicates_and_conflicts(tmp_path: Path) -> None:
    """Rekursiv, versteckte Ordner und Dateien werden übersprungen, Konflikte getrennt."""
    make_vault(tmp_path, [
        "2026-10-08.md", "Archiv/2026-10-08.md", "2026-10-09.md", "2026-10-09 Notiz.md",
        "2026-10-08.sync-conflict-20261008-101500-ABCDEFG.md",
        ".obsidian/2026-10-10.md", ".2026-10-08.md.mw-x.tmp", "Sonstiges.md",
    ])
    index = scan(tmp_path, DayPattern())
    assert index.day_files == {date(2026, 10, 8): ("2026-10-08.md", "Archiv/2026-10-08.md"),
                               date(2026, 10, 9): ("2026-10-09.md",)}
    assert list(index.duplicates()) == [date(2026, 10, 8)]
    assert [c.main_relpath for c in index.conflicts] == ["2026-10-08.md"]


def test_write_target_rules(tmp_path: Path) -> None:
    """Eine Datei → diese; keine → kanonisch; mehrere → kanonisch oder Abbruch."""
    pattern = DayPattern()
    make_vault(tmp_path, ["Archiv/2026-10-01.md", "2026-10-02.md", "A/2026-10-02.md", "A/2026-10-03.md",
                          "B/2026-10-03.md"])
    index = scan(tmp_path, pattern)
    assert write_target(index, pattern, date(2026, 10, 1)) == "Archiv/2026-10-01.md"
    assert write_target(index, pattern, date(2026, 10, 4)) == "2026-10-04.md"
    assert write_target(index, pattern, date(2026, 10, 2)) == "2026-10-02.md"
    with pytest.raises(AmbiguousDayFile):
        write_target(index, pattern, date(2026, 10, 3))


def test_snapshot_compares_content_not_time(tmp_path: Path) -> None:
    """Gleichheit richtet sich nur nach dem Inhalt."""
    path = tmp_path / "x.md"
    path.write_bytes(b"a\r\n")
    snap = read_snapshot(path)
    assert snap.raw == b"a\r\n" and snap.size == 3
    assert snap.same_content(b"a\r\n") and not snap.same_content(b"a\n")


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("*.md")))
def test_fixture_corpus_roundtrip(fixture: str) -> None:
    """Jede Fixture: Parsen und unverändert Serialisieren ist byte-identisch."""
    raw = (FIXTURES / fixture).read_bytes()
    assert parse_document(raw).source.to_bytes() == raw


def test_realistic_fixture_semantics() -> None:
    """Die realistische Fixture: Frontmatter, zwei Notizen, Code ohne Todos, Tags vererbt."""
    doc = parse_document((FIXTURES / "realistic.md").read_bytes())
    assert doc.layout.frontmatter is not None
    notes = [n for n in doc.notes if not n.note.is_empty]
    assert len(notes) == 2
    first = notes[0]
    todos = [n for n in first.outline.items() if n.item and n.item.is_todo]
    assert len(todos) == 4
    assert all("Testprojekt" in first.tags[t.index].effective_projects for t in todos)
    second = notes[1]
    texts = [doc.line_text(n.lines[0]) for n in second.outline.items()]
    assert texts == ["- [ ] mit Bild ![[bild.png]]"]
    assert "woche" in second.tags[second.outline.items()[0].index].effective
