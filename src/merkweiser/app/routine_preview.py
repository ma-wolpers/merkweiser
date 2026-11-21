"""Vorschau kommender Routinen-Instanzen als Trefferzeilen (W9): nur lesend.

Eine Instanz, die noch in keiner Tagesdatei steht, erscheint im Tab „Todos“
(unter „Zukünftig“, bei Rot unter „Sehr dringend“) und in der
Morgen-Benachrichtigung ihres Tages. Damit Status-, Tag-, Ampel- und
Datumsfilter **genau dieselbe** Semantik haben wie bei echten Todos, wird je
Tag ein synthetisches Dokument gebaut, das so aussieht, wie die Instanzen
später in der Tagesdatei stehen würden (``Thema`` + ``- [ ] Text #wdh``), und
mit ``query.search`` gefiltert. Die Treffer werden über ihre Zeilennummer
ihrer ``Occurrence`` zugeordnet (``HitRow.preview``, ``target = None``).

Nicht angezeigt werden Instanzen, die schon in der Tagesdatei stehen (z. B.
vorzeitig abgehakt; ``routine_days.present``) und solche, deren Frist schon
vorbei ist. Fenster: ab dem Tag nach dem Merkpunkt (frühestens heute), bis
``routine_preview_days`` Tage voraus (bzw. bis ``last`` für die Benachrichtigung).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import TYPE_CHECKING

from ..core.document import parse_document
from ..core.inline import TodoStatus
from ..core.query import Filter, search
from ..core.routine_days import present
from ..core.routines import ROUTINES_FILE, Occurrence, occurrences
from .routine_service import load
from .views import HitRow, hit_rows

if TYPE_CHECKING:
    from .notes_service import NotesService


def preview_rows(service: "NotesService", criteria: Filter, today: date, last: date | None = None) -> list[HitRow]:
    """Vorschauzeilen für einen Filter.

    Args:
        service: Geöffneter Service.
        criteria: Derselbe Filter wie für die echten Todos.
        today: Heute (einmal aus ``service.clock`` gelesen).
        last: Letzter Tag (Benachrichtigung: der Auslösetag); ``None`` =
            ``today + settings.routine_preview_days``.

    Returns:
        Trefferzeilen mit ``preview`` gesetzt, nach Tag geordnet.
    """
    rf = load(service)
    if rf is None or not rf.sections:
        return []
    first = max(today, rf.until + timedelta(days=1)) if rf.until else today
    end = last if last is not None else today + timedelta(days=service.settings.routine_preview_days)
    rows: list[HitRow] = []
    day = first
    while day <= end:
        rows += _day_rows(service, criteria, today, day, occurrences(rf, day))
        day += timedelta(days=1)
    return rows


def _day_rows(service: "NotesService", criteria: Filter, today: date, day: date,
              occs: list[Occurrence]) -> list[HitRow]:
    """Vorschauzeilen eines Tages (siehe Moduldoku)."""
    documents = [file.document for file in service.day(day)]
    occs = [o for o in occs if not (o.expires and o.expires <= today)
            and not any(present(doc, o.topic, o.body) for doc in documents)]
    if not occs:
        return []
    lines: list[str] = []
    by_line: dict[int, Occurrence] = {}
    for topic in dict.fromkeys(o.topic for o in occs):
        lines += [""] if lines else []
        lines.append(topic)
        for occ in (o for o in occs if o.topic == topic):
            by_line[len(lines)] = occ
            lines.append(occ.line(TodoStatus.OPEN))
    doc = parse_document("\n".join(lines).encode("utf-8"), service.settings.project_prefix)
    hits = [hit for hit in search([(ROUTINES_FILE, day, doc)], criteria) if hit.line_no in by_line]
    return [replace(row, target=None, preview=by_line[hit.line_no]) for hit, row in zip(hits, hit_rows(hits))]
