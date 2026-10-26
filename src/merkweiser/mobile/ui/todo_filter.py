"""Filter-Dialog des Tabs „Todos“ (W7): Status, Zeitraum, Tags, UND/ODER hinter einem Knopf.

Der Dialog arbeitet auf einer Kopie; erst „Anwenden“ übernimmt sie in den
Sitzungszustand. „Zurücksetzen“ setzt auf ``todo_list.DEFAULT_FILTER``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.todo_list import DEFAULT_FILTER, RANGE_LABELS, STATUS_LABELS, normalized

if TYPE_CHECKING:
    from .app import MobileApp


def filter_button(app: "MobileApp", state: dict, count: int) -> ft.IconButton:
    """Der Filter-Knopf mit Badge (Anzahl der vom Standard abweichenden Filter).

    Args:
        app: Die laufende App.
        state: Filterzustand der Sitzung.
        count: Badge-Zahl (``todo_list.changed_count``); 0 = kein Badge.

    Returns:
        Der Knopf; ein Tipp öffnet den Filter-Dialog.
    """
    async def open_dialog(_e) -> None:
        app.page.show_dialog(filter_dialog(app, state))

    return ft.IconButton(icon=ft.Icons.FILTER_LIST, tooltip="Filter", on_click=open_dialog,
                         badge=str(count) if count else None)


def filter_dialog(app: "MobileApp", state: dict) -> ft.AlertDialog:
    """Baut den Filter-Dialog.

    Args:
        app: Die laufende App.
        state: Filterzustand der Sitzung (wird erst bei „Anwenden“ bzw. „Zurücksetzen“ verändert).

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    draft = dict(normalized(state))
    status = ft.SegmentedButton(segments=[ft.Segment(value=key, label=label) for key, label in STATUS_LABELS.items()],
                                selected=[draft["status"]])
    span = ft.SegmentedButton(segments=[ft.Segment(value=key, label=label) for key, label in RANGE_LABELS.items()],
                              selected=[draft["zeitraum"]])
    tags = ft.TextField(label="Tags (Leerzeichen getrennt)", value=draft["tags"])
    either = ft.Switch(label="ODER statt UND", value=draft["oder"])

    def close_and_render(values: dict) -> None:
        state.clear()
        state.update(values)
        app.page.pop_dialog()
        app.render()

    async def apply(_e) -> None:
        close_and_render({"status": (status.selected or [draft["status"]])[0],
                          "zeitraum": (span.selected or [draft["zeitraum"]])[0],
                          "tags": (tags.value or "").strip(), "oder": bool(either.value)})

    async def reset(_e) -> None:
        close_and_render(dict(DEFAULT_FILTER))

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    content = ft.Column([ft.Text("Status"), status, ft.Text("Zeitraum"), span, tags, either],
                        tight=True, scroll=ft.ScrollMode.AUTO)
    return ft.AlertDialog(modal=True, title="Todos filtern", content=content,
                          actions=[ft.TextButton("Zurücksetzen", on_click=reset),
                                   ft.TextButton("Abbrechen", on_click=cancel),
                                   ft.TextButton("Anwenden", on_click=apply)])
