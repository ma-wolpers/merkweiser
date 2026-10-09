"""Tests für Ausrichtung, diff3, Union und die unabhängige Verlustprüfung."""

from dataclasses import replace

from merkweiser.core.merge.align import align
from merkweiser.core.merge.diff3 import merge3
from merkweiser.core.merge.model import A, B, Cert, Hunk, MergeResult, Occ, OutLine
from merkweiser.core.merge.union import merge2
from merkweiser.core.merge.verify import verify

BASE = ["Notiz", "", "- [ ] Aufgabe A"]


def m3(base, a, b) -> MergeResult:
    """Hilfsfunktion: diff3 plus bestandene Verlustprüfung."""
    result = merge3(base, a, b)
    assert verify(result, a, b, base) == []
    return result


def m2(a, b) -> MergeResult:
    """Hilfsfunktion: Union plus bestandene Verlustprüfung."""
    result = merge2(a, b)
    assert verify(result, a, b) == []
    return result


# --- Ausrichtung -----------------------------------------------------------------

def test_blank_and_repeated_lines_never_anchor_alone() -> None:
    """Leerzeilen und wiederholte Zeilen sind keine Anker; nur eindeutige Zeilen verankern."""
    regions = align([["x", "", "g", "g"], ["g", "", "x"]])
    syncs = [r.ranges for r in regions if r.sync]
    assert ((0, 1), (2, 3)) in syncs  # nur „x“ ist Anker


def test_alignment_covers_sequences_completely() -> None:
    """Die Ausrichtung deckt jede Folge lückenlos ab."""
    a, b = ["a", "b", "c", "d"], ["b", "x", "d", "e"]
    regions = align([a, b])
    for k, seq in enumerate((a, b)):
        covered = [i for r in regions for i in range(*r.ranges[k])]
        assert covered == list(range(len(seq)))


# --- diff3 ----------------------------------------------------------------------

def test_concept_example_merges_with_main_first() -> None:
    """Konzept: Basis + B auf Gerät 1 + C auf Gerät 2 → A, B, C automatisch."""
    result = m3(BASE, BASE + ["- [ ] Aufgabe B"], BASE + ["- [ ] Aufgabe C"])
    assert result.lines() == tuple(BASE + ["- [ ] Aufgabe B", "- [ ] Aufgabe C"])


def test_identical_change_of_base_line_taken_once() -> None:
    """Beide ändern dieselbe Basiszeile identisch (B → C) → einmal C, kein Konflikt."""
    result = m3(["A", "B"], ["A", "C"], ["A", "C"])
    assert result.lines() == ("A", "C")
    assert [s.cert for s in result.segments] == [Cert.ANKER, Cert.IDENTISCH]


def test_identical_insertion_taken_once() -> None:
    """Beide fügen am selben Anker dieselbe Zeile ein → einmal."""
    assert m3(["A", "B"], ["A", "X", "B"], ["A", "X", "B"]).lines() == ("A", "X", "B")


def test_one_sided_change_and_deletion() -> None:
    """Nur eine Seite ändert bzw. löscht → diese Seite gewinnt (erlaubt, Nutzeraktion)."""
    assert m3(["T", "a", "b"], ["T", "a", "b"], ["T", "b"]).lines() == ("T", "b")
    assert m3(["T", "a"], ["T", "a2"], ["T", "a"]).lines() == ("T", "a2")


def test_delete_versus_modify_is_conflict() -> None:
    """Löschung gegen Änderung derselben Zeile → Konflikt, beide Seiten im Hunk erhalten."""
    result = m3(["T", "a", "Z"], ["T", "Z"], ["T", "a geändert", "Z"])
    assert not result.clean
    hunk = result.hunks[0]
    assert hunk.a_lines == () and hunk.b_lines == ("a geändert",) and not hunk.offers_both


def test_different_changes_of_same_line_conflict() -> None:
    """Beide ändern dieselbe Zeile verschieden → Konflikt mit „beide“ als Option."""
    result = m3(["T", "a", "Z"], ["T", "a1", "Z"], ["T", "a2", "Z"])
    assert not result.clean and result.hunks[0].offers_both


def test_done_wins_in_diff3() -> None:
    """R1 auch im 3-Wege-Fall, wenn beide verschieden geändert haben."""
    result = m3(["T", "- [ ] x"], ["T", "- [x] x"], ["T", "- [X] x"])
    assert result.lines() == ("T", "- [x] x")
    assert result.segments[-1].cert is Cert.R2


# --- Union ----------------------------------------------------------------------

def test_union_concept_example_without_base_is_conflict() -> None:
    """Ohne Basis ist Einfügung von Umformulierung nicht unterscheidbar → Hunk mit „beide“."""
    result = m2(BASE + ["- [ ] Aufgabe B"], BASE + ["- [ ] Aufgabe C"])
    assert not result.clean
    assert result.hunks[0].a_lines == ("- [ ] Aufgabe B",) and result.hunks[0].offers_both


def test_union_one_sided_insertions_kept() -> None:
    """Einfügungen nur einer Seite werden übernommen."""
    assert m2(["T", "a", "Z"], ["T", "a", "neu", "Z"]).lines() == ("T", "a", "neu", "Z")


def test_union_deletion_comes_back_grenze() -> None:
    """GRENZE: Ohne Basis kommt eine einseitige Löschung zurück (lieber doppelt als verloren)."""
    assert m2(["T", "a", "b"], ["T", "b"]).lines() == ("T", "a", "b")


def test_union_done_wins_and_capital_x_keeps_main() -> None:
    """R1: erledigt gewinnt; R2: ``[x]`` gegen ``[X]`` → Hauptdatei-Schreibweise."""
    assert m2(["T", "- [ ] x #t"], ["T", "- [x] x #t"]).lines() == ("T", "- [x] x #t")
    assert m2(["T", "- [X] x"], ["T", "- [x] x"]).lines() == ("T", "- [X] x")
    assert not m2(["T", "- [ ] x"], ["T", "- [x] y"]).clean  # Text verschieden → kein R1


def test_repeated_identical_lines_stay_separate() -> None:
    """Zwei gleiche Vorkommen einer Seite fallen nicht zusammen."""
    result = m2(["T", "- [ ] g", "- [ ] g"], ["T", "- [ ] g"])
    assert result.lines() == ("T", "- [ ] g", "- [ ] g")


def test_same_content_at_different_positions_not_merged() -> None:
    """Gleicher Inhalt an verschiedenen Stellen → keine Viele-zu-eins-Zuordnung."""
    result = m2(["x", "y", "dup"], ["dup", "x", "y"])
    assert result.lines() == ("dup", "x", "y", "dup")
    assert all(s.cert is not Cert.IDENTISCH for s in result.segments)


# --- verify gegen manipulierte Ergebnisse ---------------------------------------

def test_verify_rejects_dropped_line() -> None:
    """Fehlt eine Zeile ohne Begründung, schlägt die Prüfung an."""
    a, b = ["T", "a"], ["T", "a", "neu"]
    good = merge2(a, b)
    bad = MergeResult(good.segments[:-1], three_way=False)
    assert any("fehlt" in e for e in verify(bad, a, b))


def test_verify_rejects_invented_and_altered_lines() -> None:
    """Erfundene oder veränderte Zeilen werden erkannt."""
    a, b = ["T"], ["T"]
    good = merge2(a, b)
    invented = MergeResult(good.segments + (OutLine("neu", (), Cert.UEBERNAHME),), False)
    altered = MergeResult((replace(good.segments[0], text="X"),), False)
    assert verify(invented, a, b) and verify(altered, a, b)


def test_verify_rejects_collapsing_same_side_duplicates() -> None:
    """Zwei A-Vorkommen auf eine Ausgabezeile zu legen ist unzulässig."""
    a, b = ["T", "g", "g"], ["T"]
    collapsed = MergeResult((OutLine("T", (Occ(A, 0), Occ(B, 0)), Cert.ANKER),
                             OutLine("g", (Occ(A, 1), Occ(A, 2)), Cert.IDENTISCH)), False)
    assert verify(collapsed, a, b)


def test_verify_rejects_identical_claim_across_positions() -> None:
    """„IDENTISCH“ für gleichen Text an verschiedenen Stellen wird abgelehnt."""
    a, b = ["x", "y", "dup"], ["dup", "x", "y"]
    fake = MergeResult((OutLine("dup", (Occ(A, 2), Occ(B, 0)), Cert.IDENTISCH),
                        OutLine("x", (Occ(A, 0), Occ(B, 1)), Cert.ANKER),
                        OutLine("y", (Occ(A, 1), Occ(B, 2)), Cert.ANKER)), False)
    assert verify(fake, a, b)


def test_verify_rejects_fake_r1() -> None:
    """Eine als R1 ausgegebene Ersetzung mit anderem Text wird abgelehnt."""
    a, b = ["T", "- [ ] x"], ["T", "- [x] y"]
    fake = MergeResult((OutLine("T", (Occ(A, 0), Occ(B, 0)), Cert.ANKER),
                        OutLine("- [x] y", (Occ(A, 1), Occ(B, 1)), Cert.R1)), False)
    assert verify(fake, a, b)


def test_verify_accepts_hunks_as_preserved() -> None:
    """Zeilen in einem Hunk gelten als erhalten (Ergebnis ∪ Hunks)."""
    result = merge2(["T", "a1"], ["T", "a2"])
    assert isinstance(result.segments[-1], Hunk) and verify(result, ["T", "a1"], ["T", "a2"]) == []


def test_randomized_merges_never_lose_content() -> None:
    """Zufallsfolgen (fester Seed) mit Duplikaten und Leerzeilen: verify findet nie einen Verlust."""
    import random

    rng = random.Random(20261009)
    alphabet = ["a", "b", "c", "", "- [ ] t", "- [x] t", "- [X] t", "d"]

    def mutate(seq: list[str]) -> list[str]:
        out = list(seq)
        for _ in range(rng.randint(0, 3)):
            op = rng.choice(("ins", "del", "mod"))
            pos = rng.randint(0, len(out))
            if op == "ins":
                out.insert(pos, rng.choice(alphabet))
            elif out and pos < len(out):
                if op == "del":
                    del out[pos]
                else:
                    out[pos] = rng.choice(alphabet)
        return out

    for _ in range(3000):
        base = [rng.choice(alphabet) for _ in range(rng.randint(0, 6))]
        a, b = mutate(base), mutate(base)
        assert verify(merge3(base, a, b), a, b, base) == [], (base, a, b)
        assert verify(merge2(a, b), a, b) == [], (a, b)
