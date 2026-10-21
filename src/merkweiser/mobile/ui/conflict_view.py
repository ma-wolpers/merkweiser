"""Tab „Konflikte“: Hauptdatei und Konfliktversion im Vergleich, Entscheidung per Knopf.

Jeder Fall zeigt:

* welche Datei betroffen ist und woher die Konfliktversion stammt,
* einen Zeilenvergleich (``conflict_diff``): rot = nur in der Hauptdatei,
  grün = nur in der Konfliktversion, ohne Farbe = in beiden gleich,
* Knöpfe mit einer Zeile Erklärung, was danach im Ordner steht.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.views import Choice, conflict_diff, conflict_origin, conflict_result
from ...core.conflicts import CaseKind

if TYPE_CHECKING:
    from .app import MobileApp

#: Darstellung je Vergleichsseite: (Präfix, Hintergrund).
_SIDE_STYLE = {
    "haupt": ("− ", ft.Colors.RED_100),
    "konflikt": ("+ ", ft.Colors.GREEN_100),
    "beide": ("  ", None),
    "ausgelassen": ("", None),
}

#: Knöpfe der einfachen Entscheidung: (Wahl, Beschriftung, Erklärung).
_CHOICES = (
    (Choice.HAUPTDATEI, "Hauptdatei behalten", "Rote Zeilen bleiben, grüne werden verworfen."),
    (Choice.KONFLIKTVERSION, "Konfliktversion übernehmen", "Grüne Zeilen ersetzen die roten."),
    (Choice.BEIDE, "Zusammenführen", "Alle Zeilen aus beiden Fassungen landen in der Hauptdatei."),
)


def conflicts_view(app: "MobileApp") -> list[ft.Control]:
    """Baut die Liste aller offenen Konfliktfälle.

    Args:
        app: Die laufende App (mit geöffnetem ``service``).

    Returns:
        Controls für den Tab-Inhalt.
    """
    cases = app.service.conflicts()
    if not cases:
        return [ft.Text("Keine offenen Konflikte.")]
    controls: list[ft.Control] = [ft.Text(
        "Rot (−) steht nur in der Hauptdatei, grün (+) nur in der Konfliktversion.", size=12)]
    for case in cases:
        controls.append(ft.Divider())
        controls += _case_controls(app, case, cases)
    return controls


def _case_controls(app: "MobileApp", case, cases) -> list[ft.Control]:
    """Kopf, Vergleich und Entscheidungen eines Falls.

    Args:
        app: Die laufende App.
        case: Der Konfliktfall.
        cases: Alle Fälle (für Geschwister derselben Hauptdatei).

    Returns:
        Controls des Falls.
    """
    controls: list[ft.Control] = [
        ft.Text(case.conflict.main_relpath, weight=ft.FontWeight.BOLD),
        ft.Text(f"Konfliktversion {conflict_origin(case)}", size=12),
        ft.Text(f"{case.kind.value}: {case.reason}" if case.reason else case.kind.value, size=12),
    ]
    if case.main_bytes is None:
        controls.append(ft.Text("Die Hauptdatei fehlt; unten steht nur die Konfliktversion.", size=12))
    controls.append(_diff_box(case))
    if case.kind is not CaseKind.BUSY:
        controls += _choices(app, case, cases)
    return controls


def _diff_box(case) -> ft.Control:
    """Zeilenvergleich als Kasten mit farbig hinterlegten Abweichungen.

    Args:
        case: Der Konfliktfall.

    Returns:
        Ein Container mit einer Zeile je ``DiffRow``.
    """
    rows = conflict_diff(case)
    if all(row.side in ("beide", "ausgelassen") for row in rows):
        rows_controls = [ft.Text("Beide Fassungen sind inhaltlich gleich.", size=12, italic=True)]
    else:
        rows_controls = []
        for row in rows:
            prefix, color = _SIDE_STYLE[row.side]
            italic = row.side == "ausgelassen"
            rows_controls.append(ft.Container(content=ft.Text(prefix + row.text, size=12, italic=italic,
                                                              font_family="monospace"), bgcolor=color))
    return ft.Container(content=ft.Column(rows_controls, spacing=0), padding=6,
                        bgcolor=ft.Colors.SURFACE_CONTAINER)


def _choices(app: "MobileApp", case, cases) -> list[ft.Control]:
    """Entscheidungsknöpfe mit Erklärung; bei fehlender Hauptdatei nur „wiederherstellen“.

    Args:
        app: Die laufende App.
        case: Der Konfliktfall.
        cases: Alle Fälle (bei fehlender Hauptdatei bleiben Geschwister manuell).

    Returns:
        Knöpfe samt Erklärzeilen.
    """
    others = tuple(c.conflict.relpath for c in cases
                   if c.conflict.main_relpath == case.conflict.main_relpath and c is not case)

    def button(label: str, choice: Choice) -> ft.Control:
        async def decide(_e) -> None:
            result = conflict_result(case, choice)
            manual = others if case.kind is CaseKind.MAIN_DELETED else ()
            await app.act(lambda s: s.resolve(case, result, label, manual))
        return ft.Button(label, on_click=decide)

    if case.kind is CaseKind.MAIN_DELETED:
        return [button("Diese Version wiederherstellen", Choice.KONFLIKTVERSION)]
    controls: list[ft.Control] = []
    for choice, label, hint in _CHOICES:
        controls.append(ft.Row([button(label, choice), ft.Text(hint, size=11, expand=True)]))
    return controls
