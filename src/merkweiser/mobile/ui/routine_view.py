"""Routinen in der Mobile-Oberfläche (W9): Vorschauzeilen im Tab „Todos“.

Eine Vorschauzeile ist eine kommende Routinen-Instanz, die noch in keiner
Tagesdatei steht (``app.routine_preview``). Sie sieht aus wie ein Todo, ist
aber mit 🔁 markiert. Das Häkchen schreibt sie sofort als erledigt in die
Datei ihres Tages (``routine_service.check_preview``). Ampel-Stern, ⊘ und
Verschieben gibt es erst, wenn sie eingetragen ist; der Stern zeigt die Stufe
nur an. Das ist die einzige Stelle, an der die Oberfläche Vorschauzeilen
anders behandelt (``tabs._hit``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app import routine_service
from ...app.views import HitRow
from ...core.inline import strip_urgency
from .note_view import marked, rich_text, urgency_bar
from .style import EXPLANATION, URGENCY_STYLE

if TYPE_CHECKING:
    from .app import MobileApp

ROUTINE_MARK = "🔁"
"""Kennzeichen kommender Routinen-Instanzen (Vorschau)."""


def preview_line(app: "MobileApp", row: HitRow) -> ft.Control:
    """Vorschauzeile: Kopf „🔁 Datum · Rhythmus“, Checkbox zum vorzeitigen Abhaken, Text, Ampel nur als Anzeige.

    Args:
        app: Die laufende App.
        row: Trefferzeile mit ``row.preview`` (``row.target`` ist ``None``).

    Returns:
        Spalte aus Kopfzeile und Todo-Zeile.
    """
    occurrence = row.preview

    async def check(e) -> None:
        if e.control.value:
            await app.act(lambda s: routine_service.check_preview(s, occurrence))

    icon, color, _tooltip = URGENCY_STYLE[int(row.urgency)]
    head = ft.Text(f"{ROUTINE_MARK} {row.day} · {row.context}" if row.context else f"{ROUTINE_MARK} {row.day}",
                   size=11)
    checkbox = ft.Checkbox(value=False, on_change=check, visual_density=ft.VisualDensity.COMPACT,
                           tooltip="schon jetzt erledigen")
    line = marked(checkbox, rich_text(app, strip_urgency(row.text)), [
        ft.Icon(icon, color=color or EXPLANATION, tooltip="Routine – Ampel nach dem Eintragen änderbar"),
    ])
    return ft.Column([head, urgency_bar(line, row.urgency, True)], spacing=0)
