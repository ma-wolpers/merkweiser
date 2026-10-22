"""Integrationstests für NotesService und Settings (synthetischer Vault)."""

from datetime import date
from pathlib import Path

import pytest

from merkweiser.app.notes_service import MoveTag, NotesService, ProjectConflictError, SameDayMoveError
from merkweiser.app.settings import Settings, load_settings, save_settings
from merkweiser.core.patch import Target
from merkweiser.core.query import Filter, StatusFilter, TextQuery
from tests.fakes import FakeClock


def service(tmp_path: Path) -> NotesService:
    """Hilfsfunktion: Service auf leerem synthetischem Vault (heute = 2026-01-15)."""
    root = tmp_path / "vault"
    root.mkdir(exist_ok=True)
    return NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())


def settle(svc: NotesService) -> None:
    """Quarantänen ablaufen lassen."""
    svc.clock.advance(121)
    svc.poll()


def test_start_auto_merges_syncthing_conflict(tmp_path: Path) -> None:
    """Start: Wiederherstellung, Scan, dann Auto-Merge des Konzeptbeispiels."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "2026-01-01.md").write_bytes(b"Notiz\n- [ ] A\n- [ ] B\n")
    (root / "2026-01-01.sync-conflict-20260101-120000-ABCDEFG.md").write_bytes(b"Notiz\n- [ ] A\n- [ ] C\n")
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    report = svc.start()
    settle(svc)
    assert len(report.automerges) == 1
    assert (root / "2026-01-01.md").read_bytes() == b"Notiz\n- [ ] A\n- [ ] B\n- [ ] C\n"
    assert svc.conflicts() == []


def test_append_note_creates_today_and_then_appends(tmp_path: Path) -> None:
    """Neue Notiz: Tagesdatei wird angelegt; zweite Notiz mit Trenner angehängt."""
    svc = service(tmp_path)
    svc.start()
    svc.append_note("Erste\n- [ ] a")
    settle(svc)
    svc.append_note("Zweite")
    settle(svc)
    assert (svc.root / "2026-01-15.md").read_bytes() == b"Erste\n- [ ] a\n\nZweite\n"
    assert [f.relpath for f in svc.day(date(2026, 1, 15))] == ["2026-01-15.md"]


def test_search_and_set_done_roundtrip(tmp_path: Path) -> None:
    """Todo per Suche finden, erledigen, danach im Filter „erledigt“ wiederfinden."""
    svc = service(tmp_path)
    (svc.root / "2026-01-02.md").write_bytes(b"Uni #uni\n- [ ] Lernen\n")
    svc.start()
    [hit] = svc.search(Filter(text=TextQuery("lernen"), nur_todos=True))
    svc.set_done(Target(hit.relpath, hit.line_no, hit.text), True)
    settle(svc)
    done = svc.search(Filter(status=StatusFilter.ERLEDIGT))
    assert [h.text for h in done] == ["- [x] Lernen"] and done[0].tags == ("uni",)


def test_replace_note_text_external_change_elsewhere_is_applied(tmp_path: Path) -> None:
    """Externe Änderung an einer anderen Notiz: Rohtext-Ersatz wird trotzdem angewendet."""
    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    planned = b"A\n- x\n\n---\n\nB\n- y\n"
    path.write_bytes(planned)
    svc.start()
    path.write_bytes(b"A\n- x\n- extern\n\n---\n\nB\n- y\n")
    svc.replace_note_text("2026-01-02.md", planned, ("B", "- y"), "B neu")
    settle(svc)
    assert path.read_bytes() == b"A\n- x\n- extern\n\n---\n\nB neu\n"


def test_replace_note_text_changed_note_becomes_own_conflict(tmp_path: Path) -> None:
    """Notiz extern geändert: getippter Text geht nicht verloren → eigene Konfliktdatei mit Basis."""
    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    planned = b"A\n- x\n\n---\n\nB\n- y\n"
    path.write_bytes(planned)
    svc.start()
    path.write_bytes(b"A\n- x\n\n---\n\nB\n- y extern\n")
    result = svc.replace_note_text("2026-01-02.md", planned, ("B", "- y"), "B mein Text")
    assert result.state == "CONFLICTED"
    conflict = svc.root / result.conflicts[0]
    assert b"B mein Text" in conflict.read_bytes() and conflict.name.startswith("2026-01-02.sync-conflict-")
    assert path.read_bytes() == b"A\n- x\n\n---\n\nB\n- y extern\n"
    assert len(svc.conflicts()) == 1


def test_move_todo_via_service(tmp_path: Path) -> None:
    """Verschieben über die Fassade nutzt die Schreibziel-Regel; das Thema wandert mit (ohne Verschiebe-Kopfzeile)."""
    svc = service(tmp_path)
    (svc.root / "2026-01-02.md").write_bytes(b"T #t\n- [ ] weg\n- [ ] bleibt\n")
    svc.start()
    result = svc.move_todo(Target("2026-01-02.md", 1, "- [ ] weg"), date(2026, 1, 20))
    settle(svc)
    assert result.state == "DONE"
    assert (svc.root / "2026-01-20.md").read_text(encoding="utf-8") == "T #t\n- [ ] weg\n"


def test_move_to_the_same_day_is_rejected_before_any_write(tmp_path: Path) -> None:
    """Gleiches Quell- und Zieldatum → SameDayMoveError; Dateien und App-Daten (Ops) bleiben unverändert."""
    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    path.write_bytes(b"T #t\n- [ ] weg\n- [ ] bleibt\n")
    svc.start()
    ops_before = svc.store.all_ids()
    with pytest.raises(SameDayMoveError):
        svc.move_todo(Target("2026-01-02.md", 1, "- [ ] weg"), date(2026, 1, 2))
    assert path.read_bytes() == b"T #t\n- [ ] weg\n- [ ] bleibt\n"
    assert svc.store.all_ids() == ops_before
    assert sorted(p.name for p in svc.root.iterdir()) == ["2026-01-02.md"]


def test_settings_roundtrip_and_validation(tmp_path: Path) -> None:
    """Einstellungen liegen in den App-Daten; ungültige Werte werden abgelehnt."""
    save_settings(tmp_path, Settings(vault="X", project_prefix="p", retention_days=7))
    assert load_settings(tmp_path) == Settings(vault="X", project_prefix="p", retention_days=7)
    assert load_settings(tmp_path / "leer") == Settings()
    with pytest.raises(ValueError):
        Settings(pattern="%Y.md").validated()
    with pytest.raises(ValueError):
        Settings(project_prefix="mit leer").validated()


def test_unwritable_vault_opens_read_only(tmp_path: Path, monkeypatch) -> None:
    """Plan „No-Go“: ohne sichere Schreibweise schreibgeschützt öffnen, lesen geht, schreiben wird abgelehnt."""
    from merkweiser.app import notes_service as ns
    from merkweiser.core.fs_probe import VaultNotWritableError

    def refuse(_root):
        raise VaultNotWritableError("simuliert")

    monkeypatch.setattr(ns, "probe_install_mode", refuse)
    root = tmp_path / "vault"
    root.mkdir()
    raw = b"Notiz\n- [ ] A\n"
    (root / "2026-01-15.md").write_bytes(raw)
    (root / "2026-01-15.sync-conflict-20260115-120000-ABCDEFG.md").write_bytes(b"Notiz\n- [ ] A\n- [ ] B\n")
    svc = ns.NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    report = svc.start()
    assert svc.read_only and svc.write_guarantee == "keine (schreibgeschützt)" and report.automerges == []
    [day] = svc.day(date(2026, 1, 15))
    assert day.has_conflict
    with pytest.raises(ns.ReadOnlyVaultError):
        svc.append_note("neu")
    with pytest.raises(ns.ReadOnlyVaultError):
        svc.auto_merge_all()
    svc.poll()
    assert (root / "2026-01-15.md").read_bytes() == raw and len(list(root.iterdir())) == 2


def test_move_with_tag_inserts_topic_and_resolves_the_target_again(tmp_path: Path) -> None:
    """Oberste Ebene, Notiz ohne Thema: Tag-Thema eingefügt, Ziel neu aufgelöst, Verschieben erfolgreich."""
    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    path.write_bytes(b"A\n\n- [ ] eins\n- [ ] zwei\n")
    svc.start()
    result = svc.move_todo(Target("2026-01-02.md", 2, "- [ ] eins"), date(2026, 1, 20), MoveTag("#x"))
    settle(svc)
    assert result.state == "DONE"
    assert path.read_text(encoding="utf-8") == "A\n\n#x\n- [ ] zwei\n"
    assert (svc.root / "2026-01-20.md").read_text(encoding="utf-8") == "- [ ] eins #x\n"


def test_move_subtodo_with_project_tags_todo_and_parent(tmp_path: Path) -> None:
    """Teiltodo mit Projekttag: Projekt an Todo und Überpunkt, das Thema wandert mit."""
    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    path.write_bytes(b"T\n- P\n  - [ ] teil\n  - [ ] anderes\n")
    svc.start()
    result = svc.move_todo(Target("2026-01-02.md", 2, "  - [ ] teil"), date(2026, 1, 20), MoveTag("umzug", True))
    settle(svc)
    assert result.state == "DONE"
    assert path.read_text(encoding="utf-8") == "T\n- P #projekt/umzug\n  - [ ] anderes\n"
    assert (svc.root / "2026-01-20.md").read_text(encoding="utf-8") == "T\n- [ ] teil #projekt/umzug\n"


@pytest.mark.parametrize("tag, day, error", [
    (MoveTag("neu", True), date(2026, 1, 20), ProjectConflictError),
    (MoveTag("zwei worte"), date(2026, 1, 20), ValueError),
    (MoveTag("x"), date(2026, 1, 2), SameDayMoveError),
])
def test_rejected_tag_moves_change_nothing(tmp_path: Path, tag: MoveTag, day: date, error: type) -> None:
    """Projektkonflikt, ungültiger Tag und gleiches Datum werden vor jedem Schreiben abgelehnt."""
    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    original = b"T\n- [ ] eins #projekt/alt\n- [ ] zwei\n"
    path.write_bytes(original)
    svc.start()
    ops_before = svc.store.all_ids()
    with pytest.raises(error):
        svc.move_todo(Target("2026-01-02.md", 1, "- [ ] eins #projekt/alt"), day, tag)
    assert path.read_bytes() == original and svc.store.all_ids() == ops_before
    assert sorted(p.name for p in svc.root.iterdir()) == ["2026-01-02.md"]


def test_crash_after_tag_write_leaves_only_extra_tags(tmp_path: Path, monkeypatch) -> None:
    """Absturz zwischen Tag-Schreiben und Move: nur zusätzliche Tags, kein Inhalt verloren."""
    import merkweiser.app.notes_service as module

    def crash(*_args, **_kwargs):
        raise RuntimeError("simulierter Absturz")

    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    path.write_bytes(b"T\n- [ ] eins\n- [ ] zwei\n")
    svc.start()
    monkeypatch.setattr(module, "move_todo", crash)
    with pytest.raises(RuntimeError):
        svc.move_todo(Target("2026-01-02.md", 1, "- [ ] eins"), date(2026, 1, 20), MoveTag("x"))
    settle(svc)
    assert path.read_text(encoding="utf-8") == "T #x\n- [ ] eins #x\n- [ ] zwei\n"


def test_failed_move_after_tag_reports_it(tmp_path: Path, monkeypatch) -> None:
    """Regulärer Fehler nach dem Tag-Schreiben → INCOMPLETE mit „Tag gesetzt …“, Daten konsistent."""
    import merkweiser.app.notes_service as module
    from merkweiser.core.patch import StaleTargetError

    def stale(*_args, **_kwargs):
        raise StaleTargetError("Todo nicht mehr eindeutig")

    svc = service(tmp_path)
    path = svc.root / "2026-01-02.md"
    path.write_bytes(b"T\n- [ ] eins\n- [ ] zwei\n")
    svc.start()
    monkeypatch.setattr(module, "move_todo", stale)
    result = svc.move_todo(Target("2026-01-02.md", 1, "- [ ] eins"), date(2026, 1, 20), MoveTag("x"))
    assert result.state == "INCOMPLETE" and result.hint.startswith("Tag gesetzt")
    settle(svc)
    assert path.read_text(encoding="utf-8") == "T #x\n- [ ] eins #x\n- [ ] zwei\n"
