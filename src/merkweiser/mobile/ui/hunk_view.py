"""Abschnittsweise Konfliktauflösung (Mobile): eine Wahl je Hunk eines diff3-Merges.

Für ``MANUAL``-Fälle mit Merge (``case.merge`` hat Hunks) zeigt jeder
Abschnitt die letzte gemeinsame Zeile davor, die Zeilen der Hauptdatei (rot)
und der Konfliktversion (grün) sowie die Optionen aus PLAN.md: Hauptdatei,
Konfliktversion, „Beide“ (nur wenn ``Hunk.offers_both``) und „Bearbeitet“.

Vorausgewählt ist „Hauptdatei“; das Bearbeiten-Feld ist mit deren Zeilen
vorbefüllt. BAUSTELLE(Vorschläge): Vorschläge aus der Beobachtungs-Historie
gibt es noch nicht (siehe ``ARCHITEKTUR.md``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.conflict_views import HUNK_PICK_LABELS, hunk_result
from .frontmatter_choices import fm_decisions
from ...core.conflicts import HunkPick
from ...core.merge.model import Hunk, OutLine
from .style import DIFF_ADDED, DIFF_REMOVED

if TYPE_CHECKING:
    from .app import MobileApp


def hunk_controls(app: "MobileApp", case) -> list[ft.Control]:
    """Abschnitte mit Auswahl und Knopf „Auswahl übernehmen“.

    Args:
        app: Die laufende App.
        case: ``MANUAL``-Fall mit Merge und vorhandener Hauptdatei.

    Returns:
        Controls (leer, wenn der Fall keine Abschnitte hat).
    """
    if case.merge is None or not case.merge.hunks or case.main_bytes is None:
        return []
    picks: list[list] = []
    controls: list[ft.Control] = [ft.Text("Abschnittsweise entscheiden", weight=ft.FontWeight.BOLD)]
    before = ""
    number = 0
    for segment in case.merge.segments:
        if isinstance(segment, OutLine):
            before = segment.text
            continue
        number += 1
        state = [HunkPick.HAUPT, "\n".join(segment.a_lines)]
        picks.append(state)
        controls += _hunk_block(number, before, segment, state)

    async def apply(_e) -> None:
        chosen, decisions = [(pick, text) for pick, text in picks], dict(fm_decisions(app, case))
        await app.act(lambda s: s.resolve(case, *hunk_result(case, chosen, decisions)))

    controls.append(ft.Button("Auswahl übernehmen", on_click=apply))
    return controls


def _hunk_block(number: int, before: str, hunk: Hunk, state: list) -> list[ft.Control]:
    """Anzeige und Auswahl eines Abschnitts.

    Args:
        number: Laufende Nummer (ab 1).
        before: Letzte gemeinsame Zeile davor (Orientierung) oder ``""``.
        hunk: Der Abschnitt.
        state: Veränderliche Wahl ``[HunkPick, Text]`` dieses Abschnitts.

    Returns:
        Controls des Abschnitts.
    """
    field = ft.TextField(value=state[1], multiline=True, min_lines=2, visible=False, label="Bearbeiteter Text")

    def edited(e) -> None:
        state[1] = e.control.value or ""

    field.on_change = edited

    def chosen(e) -> None:
        state[0] = HunkPick(e.control.value)
        field.visible = state[0] is HunkPick.BEARBEITET
        field.update()

    options = [ft.Radio(value=pick.value, label=label) for pick, label in HUNK_PICK_LABELS
               if pick is not HunkPick.BEIDE or hunk.offers_both]
    return [
        ft.Text(f"Abschnitt {number}" + (f" (nach „{before}“)" if before.strip() else ""), size=12),
        _lines_box(hunk.a_lines, "− ", DIFF_REMOVED),
        _lines_box(hunk.b_lines, "+ ", DIFF_ADDED),
        ft.RadioGroup(content=ft.Row(options, wrap=True), value=HunkPick.HAUPT.value, on_change=chosen),
        field,
    ]


def _lines_box(lines: tuple[str, ...], prefix: str, color) -> ft.Control:
    """Zeilen einer Seite farbig hinterlegt; leere Seite als Hinweis „(gelöscht)“.

    Args:
        lines: Zeilen der Seite.
        prefix: ``"− "`` oder ``"+ "``.
        color: Hintergrundfarbe.

    Returns:
        Ein Container.
    """
    texts = [prefix + line for line in lines] or [prefix + "(gelöscht)"]
    return ft.Container(content=ft.Column([ft.Text(t, size=12, font_family="monospace") for t in texts], spacing=0),
                        bgcolor=color, padding=4)
