"""2-Wege-Merge ohne Basis (PLAN.md, „Ohne verlässliche Basis“), Normalfall bei Syncthing.

Je Lücke der Ausrichtung ``[A, B]``:

* nur in A bzw. nur in B → behalten (gilt als Einfügung),
* beidseitig verschieden → R1/R2, falls jedes Paar darunter fällt, sonst
  Konflikt-Hunk.

GRENZE (bewusst, getestet): Ohne Basis lässt sich eine Löschung auf einer
Seite nicht von einer Einfügung auf der anderen unterscheiden. Einseitige
Löschungen kommen deshalb zurück („lieber doppelt als verloren“).

Ebenso lässt sich „beide haben Verschiedenes eingefügt“ nicht von „eine
Seite hat umformuliert“ unterscheiden. Beides wird ein Konflikt-Hunk, dessen
Vorschlag (z. B. „beide“) die Konfliktauflösung vorauswählt.
"""

from __future__ import annotations

from typing import Sequence

from .align import align
from .diff3 import status_pairs, take
from .model import A, B, Cert, Hunk, MergeResult, Occ, OutLine


def merge2(a: Sequence[str], b: Sequence[str]) -> MergeResult:
    """Führt Hauptdatei A und Konfliktversion B ohne Basis zusammen.

    Args:
        a: Hauptdatei.
        b: Andere Version (z. B. Syncthing-Konfliktdatei).

    Returns:
        Ergebnis mit Zuordnungen, Zertifikaten und ggf. Hunks.
    """
    segments: list[OutLine | Hunk] = []
    for region in align([a, b]):
        (as_, ae), (bs, be) = region.ranges
        if region.sync:
            segments.append(OutLine(a[as_], (Occ(A, as_), Occ(B, bs)), Cert.ANKER))
            continue
        a_r, b_r = list(a[as_:ae]), list(b[bs:be])
        if not b_r:
            segments.extend(take(A, a_r, as_))
        elif not a_r:
            segments.extend(take(B, b_r, bs))
        else:
            segments.extend(status_pairs(a_r, b_r, as_, bs)
                            or [Hunk((as_, ae), (bs, be), None, tuple(a_r), tuple(b_r))])
    return MergeResult(tuple(segments), three_way=False)
