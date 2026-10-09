"""3-Wege-Merge mit **verlässlicher** Basis (PLAN.md, Tabelle „Mit verlässlicher Basis“).

Verlässlich ist eine Basis nur als Edit-Basis (``replace_note_text``) oder
als Sidecar-Basis eigener Konfliktdateien. Kandidaten aus der Historie
erzeugen höchstens Vorschläge und werden hier nie automatisch verwendet.

Je Lücke der Ausrichtung ``[Basis, A, B]``:

==========================================  ===================================
Fall                                        Ergebnis
==========================================  ===================================
nur eine Seite ändert                       diese Seite
beide ändern byte-gleich                    einmal übernehmen (IDENTISCH)
beide fügen Verschiedenes ein (Basis leer)  verlustfrei: A, dann B
alle Paare nur Statusunterschied            R1/R2
sonst (inkl. Löschung gegen Änderung)       Konflikt-Hunk
==========================================  ===================================
"""

from __future__ import annotations

from typing import Sequence

from .align import align
from .model import A, B, BASE, Cert, Hunk, MergeResult, Occ, OutLine, status_rule


def merge3(base: Sequence[str], a: Sequence[str], b: Sequence[str]) -> MergeResult:
    """Führt A (Hauptdatei) und B mit gemeinsamer Basis zusammen.

    Args:
        base: Verlässliche gemeinsame Vorfahrin.
        a: Hauptdatei bzw. eigene Seite, die bei Reihenfolgefragen zuerst kommt.
        b: Andere Seite.

    Returns:
        Ergebnis mit Zuordnungen, Zertifikaten und ggf. Hunks.
    """
    segments: list[OutLine | Hunk] = []
    for region in align([base, a, b]):
        (os_, oe), (as_, ae), (bs, be) = region.ranges
        if region.sync:
            segments.append(OutLine(a[as_], (Occ(BASE, os_), Occ(A, as_), Occ(B, bs)), Cert.ANKER))
            continue
        o_r, a_r, b_r = list(base[os_:oe]), list(a[as_:ae]), list(b[bs:be])
        if a_r == o_r:
            segments.extend(take(B, b_r, bs))
        elif b_r == o_r:
            segments.extend(take(A, a_r, as_))
        elif a_r == b_r:
            segments.extend(identical(a_r, as_, bs))
        elif not o_r and a_r and b_r:
            segments.extend(take(A, a_r, as_) + take(B, b_r, bs))
        else:
            segments.extend(status_pairs(a_r, b_r, as_, bs)
                            or [Hunk((as_, ae), (bs, be), (os_, oe), tuple(a_r), tuple(b_r))])
    return MergeResult(tuple(segments), three_way=True)


def take(side: str, lines: list[str], start: int) -> list[OutLine | Hunk]:
    """Übernimmt Zeilen einer Seite unverändert.

    Args:
        side: ``A`` oder ``B``.
        lines: Die Zeilen.
        start: Index der ersten Zeile in ihrer Folge.

    Returns:
        Ausgabezeilen mit Zertifikat ``UEBERNAHME``.
    """
    return [OutLine(text, (Occ(side, start + i),), Cert.UEBERNAHME) for i, text in enumerate(lines)]


def identical(lines: list[str], a_start: int, b_start: int) -> list[OutLine | Hunk]:
    """Übernimmt eine byte-gleiche Änderung beider Seiten genau einmal.

    Args:
        lines: Die (gleichen) Zeilen.
        a_start: Beginn der Region in A.
        b_start: Beginn der Region in B.

    Returns:
        Ausgabezeilen mit zwei Quellen und Zertifikat ``IDENTISCH``.
    """
    return [OutLine(text, (Occ(A, a_start + i), Occ(B, b_start + i)), Cert.IDENTISCH)
            for i, text in enumerate(lines)]


def status_pairs(a_r: list[str], b_r: list[str], a_start: int, b_start: int) -> list[OutLine | Hunk]:
    """Wendet R1/R2 an, wenn **jedes** Zeilenpaar der Region darunter fällt.

    Args:
        a_r: Region in A.
        b_r: Region in B.
        a_start: Beginn in A.
        b_start: Beginn in B.

    Returns:
        Ausgabezeilen oder eine leere Liste, wenn die Regel nicht für alle Paare gilt.
    """
    if len(a_r) != len(b_r) or not a_r:
        return []
    out: list[OutLine | Hunk] = []
    for i, (a_line, b_line) in enumerate(zip(a_r, b_r)):
        if a_line == b_line:
            out.append(OutLine(a_line, (Occ(A, a_start + i), Occ(B, b_start + i)), Cert.IDENTISCH))
            continue
        rule = status_rule(a_line, b_line)
        if rule is None:
            return []
        out.append(OutLine(rule[1], (Occ(A, a_start + i), Occ(B, b_start + i)), rule[0]))
    return out
