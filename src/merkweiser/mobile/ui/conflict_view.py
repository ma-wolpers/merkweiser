"""Seite „Konflikte“ (Einstellungen → Konflikte): Fälle mit notizweiser Entscheidung, darunter die Auto-Merges.

Jeder Fall zeigt:

* welche Datei betroffen ist und woher die Konfliktversion stammt,
* bei fehlender Hauptdatei eine Erklärung (und ob die Version leer ist),
* die notizweise Auswahl (``note_choice_view``, W8); bei ``BUSY`` nur den
  Zeilenvergleich: rot = nur in der Hauptdatei, grün = nur in der
  Konfliktversion, ohne Farbe = in beiden gleich.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.conflict_views import case_headline, conflict_diff, conflict_origin, line_diff
from ...core.cleanup import is_empty_version
from ...core.conflicts import CaseKind
from .diff_box import diff_box
from .note_choice_view import note_choice_controls

if TYPE_CHECKING:
    from .app import MobileApp

#: Erklärung bei fehlender Hauptdatei (Fallart „Hauptdatei fehlt“).
MAIN_DELETED_HINT = ("Die Hauptdatei fehlt (gelöscht oder umbenannt). Wähle, welche Notizen dieser Version "
                     "wiederhergestellt werden, oder verwirf die Version – Verworfenes bleibt unter Backups.")


def conflicts_view(app: "MobileApp") -> list[ft.Control]:
    """Baut die Liste aller offenen Konfliktfälle.

    Args:
        app: Die laufende App (mit geöffnetem ``service``).

    Returns:
        Controls für den Tab-Inhalt.
    """
    cases = app.service.conflicts()
    if not cases:
        controls: list[ft.Control] = [ft.Text("Keine offenen Konflikte.")]
    else:
        controls = [ft.Text("Rot (−) steht nur in der Hauptdatei, grün (+) nur in der Konfliktversion.", size=12)]
    for case in cases:
        controls.append(ft.Divider())
        controls += _case_controls(app, case, cases)
    return controls + _automerge_controls(app)


def _automerge_controls(app: "MobileApp") -> list[ft.Control]:
    """Abschnitt „Automatisch zusammengeführt“ mit Vergleich, „Rückgängig“ und „Ausblenden“.

    Ein rückgängig gemachter Eintrag zeigt das an; seine Konfliktdatei steht
    dann oben als offener Fall und wird nie wieder automatisch zusammengeführt.
    Ausgeblendete Einträge erscheinen nicht mehr (ihr Backup bleibt bis zum Ende
    der Aufbewahrung).

    Args:
        app: Die laufende App.

    Returns:
        Controls des Abschnitts (leer, wenn es keine sichtbaren Auto-Merges gibt).
    """
    entries = app.service.automerges()
    if not entries:
        return []
    ids = [entry.op_id for entry in entries]

    async def hide_all(_e) -> None:
        await app.act(lambda s: s.hide_automerges(ids))

    controls: list[ft.Control] = [
        ft.Divider(thickness=3),
        ft.Row([ft.Text("Automatisch zusammengeführt", weight=ft.FontWeight.BOLD, expand=True),
                ft.TextButton("Alle ausblenden", on_click=hide_all)]),
        ft.Text("Rot (−) stand vorher in der Hauptdatei, grün (+) ist durch das Zusammenführen dazugekommen.",
                size=12)]
    for entry in entries:
        when = entry.created.astimezone().strftime("%d.%m. %H:%M")
        controls += [ft.Divider(), ft.Text(f"{entry.relpath} – {when}", weight=ft.FontWeight.BOLD),
                     diff_box(line_diff(entry.before, entry.after)), _entry_actions(app, entry)]
    return controls


def _entry_actions(app: "MobileApp", entry) -> ft.Control:
    """Knöpfe eines Auto-Merge-Eintrags: „Rückgängig“ (falls noch möglich) und „Ausblenden“.

    Args:
        app: Die laufende App.
        entry: ``AutoMergeEntry``.

    Returns:
        Zeile mit Knöpfen bzw. Hinweis „Rückgängig gemacht“.
    """
    async def undo(_e) -> None:
        await app.act(lambda s: s.undo_automerge(entry.op_id))

    async def hide(_e) -> None:
        await app.act(lambda s: s.hide_automerges([entry.op_id]))

    if entry.undone == "erledigt":
        first: ft.Control = ft.Text("Rückgängig gemacht – die Konfliktversion steht wieder oben.", size=12,
                                    italic=True, expand=True)
    else:
        first = ft.Button("Rückgängig", on_click=undo,
                          tooltip="Hauptdatei wie vorher, Konfliktversion wieder als offener Fall")
    return ft.Row([first, ft.TextButton("Ausblenden", on_click=hide)], wrap=True)


def _case_controls(app: "MobileApp", case, cases) -> list[ft.Control]:
    """Kopf und Entscheidungsteil eines Falls.

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
        ft.Text(case_headline(case), size=12),
    ]
    if case.main_bytes is None:
        controls.append(ft.Text(MAIN_DELETED_HINT, size=12))
        if is_empty_version(case.conflict_bytes):
            controls.append(ft.Text("Diese Konfliktversion ist leer.", size=12, italic=True))
    if case.kind is CaseKind.BUSY:
        return controls + [diff_box(conflict_diff(case))]
    return controls + note_choice_controls(app, case, cases)
