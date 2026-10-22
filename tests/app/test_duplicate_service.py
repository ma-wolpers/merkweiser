"""Tests für doppelte Notizen in App-Schicht und Mobile-Ansicht (W3)."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from merkweiser.app.duplicate_service import duplicates, keep
from merkweiser.app.interrupted import DISMISS, RETRY, action_label, apply_action, interrupted, open_issue_count
from merkweiser.app.notes_service import NotesService
from merkweiser.app.settings import Settings
from tests.fakes import FakeClock

NOTE = b"Gleich\n- [ ] a\n"


def service(tmp_path: Path) -> NotesService:
    root = tmp_path / "vault"
    root.mkdir()
    for day in ("2026-01-10", "2026-01-11", "2026-01-12"):
        (root / f"{day}.md").write_bytes(f"Nur {day}\n\n".encode() + NOTE)
    svc = NotesService(root, tmp_path / "app", Settings(vault=str(root)), FakeClock())
    svc.start()
    return svc


def settle(svc: NotesService) -> None:
    svc.clock.advance(121)
    svc.writer.finish_due()


def test_groups_are_counted_in_the_badge_and_cached(tmp_path: Path) -> None:
    svc = service(tmp_path)
    [group] = duplicates(svc)
    assert len(group.places) == 3 and open_issue_count(svc) == 1
    assert duplicates(svc)[0] is group  # unverändert → zwischengespeichert


def test_keep_newest_cleans_up_and_clears_the_badge(tmp_path: Path) -> None:
    svc = service(tmp_path)
    [group] = duplicates(svc)
    assert "2 Fundstelle(n) gelöscht" in keep(svc, group, 2)
    settle(svc)
    svc.rescan()
    assert duplicates(svc) == [] and open_issue_count(svc) == 0
    assert NOTE.decode() in (svc.root / "2026-01-12.md").read_text(encoding="utf-8")


def test_interrupted_cleanup_offers_recheck(tmp_path: Path) -> None:
    """Veränderte Fundstelle → unterbrochen; „Erneut prüfen“ bleibt sicher, „Verwerfen“ quittiert."""
    svc = service(tmp_path)
    [group] = duplicates(svc)
    (svc.root / "2026-01-10.md").write_bytes(b"Nur 2026-01-10\n\n" + NOTE + b"- [ ] neu\n")
    assert "2026-01-10.md" in keep(svc, group, 2)
    [entry] = interrupted(svc.store)
    assert entry.actions == (RETRY, DISMISS) and action_label(entry, RETRY) == "Erneut prüfen"
    assert "2026-01-10.md" in apply_action(svc, entry.op_id, RETRY)
    assert apply_action(svc, entry.op_id, DISMISS) == ""
    assert interrupted(svc.store) == []


def test_mobile_section_confirms_before_cleaning(tmp_path: Path) -> None:
    ft = pytest.importorskip("flet")
    from merkweiser.mobile.ui.duplicate_view import duplicate_controls
    svc = service(tmp_path)
    dialogs = []
    said = []

    async def act(action):
        return action(svc)

    app = SimpleNamespace(service=svc, act=act, say=lambda m, link=False: said.append(m), render=lambda: None,
                          page=SimpleNamespace(show_dialog=dialogs.append, pop_dialog=lambda: dialogs.pop()))
    controls = duplicate_controls(app)
    buttons = [b for row in controls if isinstance(row, ft.Row) for b in row.controls if isinstance(b, ft.TextButton)]
    labels = [b.content for b in buttons]
    assert labels.count("Diese behalten") == 3 and "Neueste behalten" in labels and "Älteste behalten" in labels
    oldest = next(b for b in buttons if b.content == "Älteste behalten")
    asyncio.run(oldest.on_click(None))
    asyncio.run(dialogs[-1].actions[1].on_click(None))
    assert said and "gelöscht" in said[0]
    settle(svc)
    assert NOTE.decode() in (svc.root / "2026-01-10.md").read_text(encoding="utf-8")
    assert NOTE.decode() not in (svc.root / "2026-01-12.md").read_text(encoding="utf-8")
