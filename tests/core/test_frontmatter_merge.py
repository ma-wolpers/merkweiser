"""Tests für den frontmatter-bewussten Merge (W6, PLAN-SPAETERE-SCHRITTE.md S5/S2/Y5/Y7)."""

from pathlib import Path

from merkweiser.app.conflict_views import Choice, conflict_result
from merkweiser.core import conflict_files as cf
from merkweiser.core.conflicts import CaseKind, auto_merge
from merkweiser.core.merge.frontmatter import StampConflict, merge_frontmatter, split
from merkweiser.core.undo_merge import plan_undo
from tests.core.test_conflicts import CONF, MAIN, Env

S1 = b"messung_start: 2026-01-01T08:00:00+01:00\nmessung_taetigkeit: Orga\n"
S2 = b"messung_start: 2026-01-01T09:30:00+01:00\nmessung_taetigkeit: Orga\n"
S3 = b"messung_start: 2026-01-01T09:30:00+01:00\nmessung_taetigkeit: Kurs\n"
BODY = b"Thema\n- [ ] a\n"


def fm(*parts: bytes) -> bytes:
    return b"---\n" + b"".join(parts) + b"---\n" + BODY


def case(tmp_path: Path, main: bytes, conflict: bytes):
    env = Env(tmp_path)
    env.put(MAIN, main)
    env.put(CONF, conflict)
    [found] = env.cases()
    return env, found


def test_regression_minutes_are_never_duplicated(tmp_path: Path) -> None:
    """Befund der Erkundung: Union machte aus 90/120 zwei Zeilen. Jetzt: AUTO mit dem Maximum, eine Zeile."""
    env, found = case(tmp_path, fm(b"zeit_Orga: 90\n"), fm(b"zeit_Orga: 120\n"))
    assert found.kind is CaseKind.AUTO
    auto_merge(env.writer, env.store, found)
    env.settle()
    assert env.get(MAIN) == fm(b"zeit_Orga: 120\n")


def test_foreign_keys_merge_per_key_and_bodies_union(tmp_path: Path) -> None:
    env, found = case(tmp_path, b"---\ntags: [a]\nzeit_Orga: 5\n---\nThema\n- [ ] a\n",
                      b"---\nzeit_Kurs: 7\nautor: x\n---\nThema\n- [ ] a\n- [ ] b\n")
    assert found.kind is CaseKind.AUTO
    auto_merge(env.writer, env.store, found)
    env.settle()
    assert env.get(MAIN) == b"---\ntags: [a]\nzeit_Orga: 5\nzeit_Kurs: 7\nautor: x\n---\nThema\n- [ ] a\n- [ ] b\n"


def test_different_foreign_values_need_a_decision(tmp_path: Path) -> None:
    _env, found = case(tmp_path, fm(b"tags: [a]\n"), fm(b"tags: [b]\n"))
    assert found.kind is CaseKind.MANUAL and found.reason == "unterschiedliche Eigenschaften"
    assert conflict_result(found, Choice.BEIDE, {0: "b"}) == fm(b"tags: [b]\n")


def test_one_sided_stamp_always_asks(tmp_path: Path) -> None:
    """Ohne Basis: Stempel nur auf einer Seite → Nachfrage „weiterlaufen / verwerfen“."""
    _env, found = case(tmp_path, fm(b"zeit_Orga: 5\n", S1), fm(b"zeit_Orga: 60\n"))
    assert found.kind is CaseKind.MANUAL and found.reason == "laufende Messungen"
    [conflict] = found.frontmatter.conflicts
    assert [code for code, _ in conflict.options()] == ["weiter", "verwerfen"]
    assert found.frontmatter.resolve({0: "verwerfen"}) == ("---", "zeit_Orga: 60", "---")
    assert found.frontmatter.resolve({0: "weiter"})[2:4] == ("messung_start: 2026-01-01T08:00:00+01:00",
                                                              "messung_taetigkeit: Orga")


def test_two_stamps_same_and_different_activity() -> None:
    """Gleiche Tätigkeit: später oder früher. Verschiedene: später oder „früher endet“ mit Buchung."""
    same = merge_frontmatter(split(fm(S1))[0], split(fm(S2))[0]).conflicts[0]
    assert [c for c, _ in same.options()] == ["spaeter", "frueher"]
    merged = merge_frontmatter(split(fm(b"zeit_Orga: 10\n", S1))[0], split(fm(S3))[0])
    [conflict] = merged.conflicts
    assert isinstance(conflict, StampConflict) and [c for c, _ in conflict.options()] == ["spaeter", "frueher_endet"]
    lines = merged.resolve({0: "frueher_endet"})
    assert "zeit_Orga: 100" in lines and "messung_taetigkeit: Kurs" in lines  # 10 + 90 Minuten, Kurs läuft
    assert "messung_taetigkeit: Orga" not in merged.resolve({0: "spaeter"})


def test_stamp_record_is_never_mixed() -> None:
    """Y5: Start von A und Tätigkeit von B werden nie kombiniert; ein halber Stempel ist beschädigt."""
    half = fm(b"messung_start: 2026-01-01T08:00:00+01:00\n")
    merged = merge_frontmatter(split(fm(S1))[0], split(half)[0])
    [conflict] = merged.conflicts
    assert [c for c, _ in conflict.options()] == ["a", "verwerfen"]
    assert merge_frontmatter(split(fm(S1))[0], split(fm(S1))[0]).conflicts == []


def test_own_conflict_with_base_resolves_stamp_by_diff3(tmp_path: Path) -> None:
    """B1: Mit Basis (eigene Konfliktdatei) ist „auf einer Seite gestoppt“ eindeutig – keine Nachfrage."""
    env = Env(tmp_path)
    before = fm(b"zeit_Orga: 5\n", S1)
    env.put(MAIN, before)
    env.writer.write(MAIN, before, fm(b"zeit_Orga: 65\n"))  # Merkweiser stoppt …
    env.put(MAIN, fm(b"zeit_Orga: 5\n", S1).replace(b"- [ ] a", b"- [x] a"))  # … während Obsidian abhakt
    env.settle()
    [found] = env.cases()
    assert found.kind is CaseKind.AUTO, found.reason
    lines = found.frontmatter.resolve()
    assert lines == ("---", "zeit_Orga: 65", "---")


def test_opaque_head_is_a_block_and_open_head_is_whole_file_only(tmp_path: Path) -> None:
    _env, found = case(tmp_path, b"---\n# k\na: 1\n---\n" + BODY, b"---\n# k\na: 2\n---\n" + BODY)
    assert found.reason == "Kopfbereich unterschiedlich"
    assert conflict_result(found, Choice.BEIDE, {0: "a"}).startswith(b"---\n# k\na: 1\n---\n")
    (tmp_path / "x").mkdir()
    _env2, opened = case(tmp_path / "x", b"---\nzeit_Orga: 1\n" + BODY, b"---\nzeit_Orga: 2\n" + BODY)
    assert opened.kind is CaseKind.MANUAL and "schließendes" in opened.reason and opened.merge is None


def test_known_rename_is_normalized_before_maximum() -> None:
    """S2: A hat nach dem Umbenennen Verwaltung 90, B (ohne Kenntnis) Orga 120 → Verwaltung 120; mit Zusammenführung 170."""
    renames = (("Orga", "Verwaltung"),)
    merged = merge_frontmatter(split(fm(b"zeit_Verwaltung: 90\n"))[0], split(fm(b"zeit_Orga: 120\n"))[0], None, renames)
    assert merged.resolve() == ("---", "zeit_Verwaltung: 120", "---")
    merged = merge_frontmatter(split(fm(b"zeit_Verwaltung: 140\n"))[0],
                               split(fm(b"zeit_Verwaltung: 50\nzeit_Orga: 120\n"))[0], None, renames)
    assert merged.resolve() == ("---", "zeit_Verwaltung: 170", "---")


# --- Rückgängig mit Kopf (Y7) -----------------------------------------------------------


def test_undo_reverts_minutes_when_untouched_and_keeps_foreign_change() -> None:
    plan = plan_undo(fm(b"zeit_Orga: 30\ntags: [a]\n"), fm(b"zeit_Orga: 60\ntags: [a]\n"),
                     fm(b"zeit_Orga: 60\ntags: [b]\n"))
    assert plan.action == "schreiben" and plan.data == fm(b"zeit_Orga: 30\ntags: [b]\n")


def test_undo_never_overwrites_younger_minutes_or_stamp() -> None:
    assert plan_undo(fm(b"zeit_Orga: 30\n"), fm(b"zeit_Orga: 60\n"), fm(b"zeit_Orga: 75\n")).action == "konflikt"
    assert plan_undo(fm(S1), fm(b"zeit_Orga: 90\n"), fm(b"zeit_Orga: 90\n", S2)).action == "konflikt"


def test_undo_conflict_file_with_head_keeps_sidecar(tmp_path: Path) -> None:
    """Bestehende Backup-Funktion mit Kopf: nicht eindeutig → Konfliktdatei mit Basis."""
    from merkweiser.core.backups import changes, undo_change
    env = Env(tmp_path)
    env.put(MAIN, fm(b"zeit_Orga: 30\n"))
    env.writer.write(MAIN, fm(b"zeit_Orga: 30\n"), fm(b"zeit_Orga: 60\n"))
    env.settle()
    env.put(MAIN, fm(b"zeit_Orga: 75\n"))
    [change] = [c for c in changes(env.store) if c.relpath == MAIN]
    assert undo_change(env.writer, env.store, change).action == "konflikt"
    [found] = env.cases()
    assert found.conflict_bytes == fm(b"zeit_Orga: 30\n")
    assert cf.read_sidecar(env.data, found.conflict.relpath, cf.sha1(found.conflict_bytes))
    # Ohne Herkunft „rueckgaengig“ hätte die Maximum-Regel 75 automatisch behalten und den Wunsch still verworfen.
    assert found.kind is CaseKind.MANUAL and found.reason == "unterschiedliche Eigenschaften"


def test_undo_conflict_is_never_automatic_even_if_merge_is_clean(tmp_path: Path) -> None:
    """Konfliktdatei aus Rückgängig ist immer eine Entscheidung (Herkunft im Sidecar)."""
    env = Env(tmp_path)
    env.put(MAIN, BODY)
    rel = env.writer.rel(cf.create_from_bytes(env.fs, env.root / MAIN, BODY + b"- [ ] b\n", env.clock))
    basis = env.store.create("konfliktbasis", {"relpath": MAIN}, {"vorher": BODY})
    basis.set_state("DONE")
    basis.release()
    cf.write_sidecar(env.data, rel, cf.sha1(BODY + b"- [ ] b\n"), MAIN, basis.id, cf.sha1(BODY), cf.UNDO_ORIGIN)
    [found] = env.cases()
    assert found.kind is CaseKind.MANUAL and "Rückgängig" in found.reason
