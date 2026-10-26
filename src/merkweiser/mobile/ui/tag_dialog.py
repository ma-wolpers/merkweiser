"""Vor dem Herauslösen eines Todos warnen und optional einen gemeinsamen Tag anbieten (Mobile).

Ablauf beim Tipp auf „verschieben …“ (``show_move_flow``):

* Ist das Todo das **alleinige** seiner Notiz, wandert die ganze Notiz; es geht
  direkt zur Datumswahl.
* Sonst erscheint der Tag-Dialog: Hinweis, Eingabefeld (Tag ohne ``#``),
  Schalter „als Projekt“ und die Knöpfe „Abbrechen“, „Mit Tag verschieben“ und
  „Einfach so verschieben“, bzw. „Mit bestehendem Tag verschieben“, wenn Todo und
  Überpunkt schon ein gemeinsames Projekt haben.

Der Dialog **schreibt nichts**: Der gewählte Tag geht an die Datumswahl weiter.
Geschrieben wird erst in ``NotesService.move_todo`` nach allen Prüfungen.
Die Prüfung der Eingabe steckt UI-neutral in ``app.views.tag_check``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.notes_service import MoveTag
from ...app.views import tag_check
from ...core.move_plan import MoveContext
from ...core.patch import Target
from .move_dialog import show_move_dialog

if TYPE_CHECKING:
    from .app import MobileApp

HINT = "Diese Notiz hat weitere Todos. Mit einem gemeinsamen Tag findest du sie wieder."


async def show_move_flow(app: "MobileApp", target: Target) -> None:
    """Startet das Verschieben: direkt zur Datumswahl oder erst der Tag-Dialog.

    Der Tag-Dialog erscheint nur, wenn die Notiz weitere Todos hat **und** das
    Todo noch keinen Tag erbt (``MoveContext.needs_tag_dialog``, W7).

    Args:
        app: Die laufende App.
        target: Adresse des Todos.
    """
    context = await app.act(lambda s: s.move_info(target))
    if context is None:  # Fehler hat ``act`` bereits gemeldet
        return
    if context.needs_tag_dialog:
        app.page.show_dialog(tag_dialog(app, target, context))
    else:
        show_move_dialog(app, target)


def tag_dialog(app: "MobileApp", target: Target, context: MoveContext) -> ft.AlertDialog:
    """Baut den Tag-Dialog.

    Args:
        app: Die laufende App.
        target: Adresse des Todos.
        context: Ergebnis von ``NotesService.move_info``.

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    prefix = app.settings.project_prefix
    field = ft.TextField(label="Tag (ohne #)", autofocus=True)
    project = ft.Switch(label="als Projekt", value=False)
    message = ft.Text("", size=12)
    with_tag = ft.Button("Mit Tag verschieben", disabled=True)
    shared = context.shared_projects
    plain = f"Mit bestehendem Tag verschieben (#{prefix}/{shared[0]})" if shared else "Einfach so verschieben"

    def check():
        return tag_check(field.value or "", bool(project.value), prefix, context,
                         lambda criteria: len(app.service.search(criteria)))

    async def changed(_e) -> None:
        result = check()
        message.value = result.message
        message.color = ft.Colors.ERROR if result.message and not result.ok else None
        with_tag.disabled = not result.ok
        message.update()
        with_tag.update()

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    async def move_plain(_e) -> None:
        app.page.pop_dialog()
        show_move_dialog(app, target)

    async def move_tagged(_e) -> None:
        if not check().ok:
            return
        app.page.pop_dialog()
        show_move_dialog(app, target, MoveTag(field.value or "", bool(project.value)))

    field.on_change = changed
    project.on_change = changed
    with_tag.on_click = move_tagged
    return ft.AlertDialog(modal=True, title="Todo herauslösen?", scrollable=True,
                          content=ft.Column([ft.Text(HINT), field, project, message], tight=True),
                          actions=[ft.TextButton("Abbrechen", on_click=cancel),
                                   ft.TextButton(plain, on_click=move_plain), with_tag])
