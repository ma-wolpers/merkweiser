"""Unabhängige Verlustprüfung eines Merge-Ergebnisses (PLAN.md, „Verlustprüfung“).

Prüft **nicht** die Merge-Entscheidungen nach, sondern ob das Ergebnis die
Garantie „kein unerlaubter Verlust“ einhält. Grundlage ist die Zuordnung
Eingabe-Vorkommen → Ausgabezeile mit Zertifikat, die der Merger liefert.
Die Ausrichtung wird für Anker- und Regionsprüfungen **selbst neu berechnet**.

Geprüft wird:

1. Je Seite injektiv: Zwei Vorkommen derselben Seite fallen nie zusammen.
2. Je Seite monoton: Die Reihenfolge jeder Seite bleibt erhalten.
3. Viele-zu-eins nur seitenübergreifend und nur mit ``ANKER`` oder
   ``IDENTISCH``; ``IDENTISCH`` nur für byte-gleiche Zeilen an gleicher
   Position in derselben, gleich langen Region zwischen denselben Ankern.
   Gleicher Text allein beweist nichts.
4. Byte-Gleichheit Eingabe = Ausgabe, außer bei ``R1``/``R2``, die gegen die
   Regel selbst geprüft werden.
5. Vollständigkeit: Union – jedes A- und B-Vorkommen ist in der Ausgabe oder
   einem Hunk. diff3 – ein fehlendes A/B-Vorkommen ist nur erlaubt, wenn
   seine Region auf dieser Seite gleich der Basis ist (die Gegenseite hat
   geändert).
6. Keine erfundenen Zeilen: jede Ausgabezeile hat ein Urbild.

Ein Verstoß liefert eine Fehlerbeschreibung; der Aufrufer stuft dann zum
Konflikt herab.
"""

from __future__ import annotations

from typing import Sequence

from .align import Region, align
from .model import A, B, BASE, Cert, Hunk, MergeResult, Occ, OutLine, status_rule


def verify(result: MergeResult, a: Sequence[str], b: Sequence[str],
           base: Sequence[str] | None = None) -> list[str]:
    """Prüft ein Merge-Ergebnis gegen die Eingaben.

    Args:
        result: Ergebnis von ``merge3`` bzw. ``merge2``.
        a: Hauptdatei.
        b: Andere Seite.
        base: Basis (nur bei diff3).

    Returns:
        Liste der Verstöße; leer heißt „bestanden“.
    """
    seqs = {A: a, B: b, BASE: base or ()}
    regions = align([base, a, b] if result.three_way and base is not None else [a, b])
    sides = [BASE, A, B] if result.three_way else [A, B]
    where = _region_index(regions, sides)
    errors: list[str] = []
    seen: dict[str, list[int]] = {A: [], B: []}
    for segment in result.segments:
        if isinstance(segment, Hunk):
            seen[A].extend(range(*segment.a_range))
            seen[B].extend(range(*segment.b_range))
            continue
        errors.extend(_check_line(segment, seqs, regions, where))
        for occ in segment.sources:
            if occ.side in seen:
                seen[occ.side].append(occ.index)
    for side in (A, B):
        indices = seen[side]
        if len(indices) != len(set(indices)):
            errors.append(f"{side}: Vorkommen mehrfach zugeordnet")
        if indices != sorted(indices):
            errors.append(f"{side}: Reihenfolge verletzt")
        for missing in sorted(set(range(len(seqs[side]))) - set(indices)):
            if not (result.three_way and _unchanged_from_base(side, missing, regions, where, seqs)):
                errors.append(f"{side}{missing}: Zeile fehlt {seqs[side][missing]!r}")
    return errors


def _region_index(regions: tuple[Region, ...], sides: list[str]) -> dict[tuple[str, int], tuple[int, int]]:
    """Ordnet jedem Vorkommen (Seite, Index) seine Region und Position darin zu."""
    index: dict[tuple[str, int], tuple[int, int]] = {}
    for r_no, region in enumerate(regions):
        for side, (start, end) in zip(sides, region.ranges):
            for i in range(start, end):
                index[(side, i)] = (r_no, i - start)
    return index


def _check_line(line: OutLine, seqs: dict, regions: tuple[Region, ...],
                where: dict[tuple[str, int], tuple[int, int]]) -> list[str]:
    """Prüft Urbild, Zertifikat und Byte-Gleichheit einer Ausgabezeile.

    Args:
        line: Ausgabezeile.
        seqs: Eingabefolgen je Seite.
        regions: Neu berechnete Ausrichtung.
        where: Region und Offset je Vorkommen.

    Returns:
        Verstöße dieser Zeile.
    """
    sources = [o for o in line.sources if o.side in (A, B)]
    if not sources or any(not 0 <= o.index < len(seqs[o.side]) for o in sources):
        return [f"erfundene Zeile {line.text!r}"]
    texts = [seqs[o.side][o.index] for o in sources]
    if line.cert in (Cert.R1, Cert.R2):
        a_occ, b_occ = _pair(sources)
        rule = status_rule(seqs[A][a_occ.index], seqs[B][b_occ.index]) if a_occ and b_occ else None
        if rule != (line.cert, line.text) or not _same_slot(a_occ, b_occ, regions, where):
            return [f"ungültige {line.cert.value}-Ersetzung {line.text!r}"]
        return []
    if any(text != line.text for text in texts):
        return [f"Text weicht ab: {line.text!r}"]
    if len(sources) == 1:
        return [] if line.cert is Cert.UEBERNAHME else [f"Zertifikat passt nicht: {line.text!r}"]
    a_occ, b_occ = _pair(sources)
    if a_occ is None or b_occ is None:
        return [f"Viele-zu-eins auf einer Seite: {line.text!r}"]
    if line.cert is Cert.ANKER:
        ok = where.get((A, a_occ.index), (-1,))[0] == where.get((B, b_occ.index), (-2,))[0] \
            and regions[where[(A, a_occ.index)][0]].sync
        return [] if ok else [f"kein Anker: {line.text!r}"]
    if line.cert is Cert.IDENTISCH and _same_slot(a_occ, b_occ, regions, where):
        return []
    return [f"unbelegte Zusammenlegung: {line.text!r}"]


def _pair(sources: list[Occ]) -> tuple[Occ | None, Occ | None]:
    """Teilt Quellen in genau ein A- und ein B-Vorkommen auf (sonst ``None``)."""
    a_occ = [o for o in sources if o.side == A]
    b_occ = [o for o in sources if o.side == B]
    return (a_occ[0] if len(a_occ) == 1 else None), (b_occ[0] if len(b_occ) == 1 else None)


def _same_slot(a_occ: Occ | None, b_occ: Occ | None, regions: tuple[Region, ...],
               where: dict[tuple[str, int], tuple[int, int]]) -> bool:
    """``True``: beide Vorkommen in derselben Lücke, gleicher Offset, gleich lange Bereiche."""
    if a_occ is None or b_occ is None:
        return False
    a_pos, b_pos = where.get((A, a_occ.index)), where.get((B, b_occ.index))
    if a_pos is None or b_pos is None or a_pos != b_pos:
        return False
    region = regions[a_pos[0]]
    lengths = {e - s for s, e in region.ranges[-2:]}
    return not region.sync and len(lengths) == 1


def _unchanged_from_base(side: str, index: int, regions: tuple[Region, ...],
                         where: dict[tuple[str, int], tuple[int, int]], seqs: dict) -> bool:
    """diff3: Darf das Vorkommen fehlen? Nur wenn seine Region auf dieser Seite der Basis gleicht."""
    pos = where.get((side, index))
    if pos is None:
        return False
    region = regions[pos[0]]
    (os_, oe), (as_, ae), (bs, be) = region.ranges
    own = seqs[A][as_:ae] if side == A else seqs[B][bs:be]
    return not region.sync and list(own) == list(seqs[BASE][os_:oe])
