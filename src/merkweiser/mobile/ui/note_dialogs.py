"""Notiz bearbeiten und löschen (Mobile): Knopfleiste je Notiz und die zugehörigen Dialoge.

Beide Aktionen adressieren die Notiz über ``NoteRef`` (Inhaltszeilen beim
Öffnen, keine IDs) und laufen über ``NotesService``:

* **Bearbeiten** ersetzt den Notiztext (``replace_note_text``). Hat sich die
  Notiz inzwischen verändert und ist nicht mehr eindeutig auffindbar, landet
  die bearbeitete Fassung als eigene Konfliktdatei; ``MobileApp.act`` meldet das.
* **Löschen** entfernt die Notiz samt einem angrenzenden Trenner
  (``delete_note``) erst nach Rückfrage. Die vorherige Datei bleibt als Backup
  im Op-Verzeichnis (Aufbewahrung laut Einstellungen).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app.views import NoteRef

if TYPE_CHECKING:
    from .app import MobileApp


def note_actions(app: "MobileApp", ref: NoteRef) -> ft.Control:
    """Knopfleiste „Bearbeiten“/„Löschen“ unter einer Notiz.

    Args:
        app: Die laufende App.
        ref: Adresse und Text der Notiz zum Zeitpunkt der Anzeige.

    Returns:
        Eine rechtsbündige Zeile mit zwei Symbolknöpfen.
    """
    async def edit(_e) -> None:
        app.page.show_dialog(_edit_dialog(app, ref))

    async def delete(_e) -> None:
        app.page.show_dialog(_delete_dialog(app, ref))

    return ft.Row([ft.IconButton(icon=ft.Icons.EDIT, on_click=edit, tooltip="Notiz bearbeiten"),
                   ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, on_click=delete, tooltip="Notiz löschen")],
                  alignment=ft.MainAxisAlignment.END)


def _edit_dialog(app: "MobileApp", ref: NoteRef) -> ft.AlertDialog:
    """Dialog mit dem Rohtext der Notiz; „Speichern“ ersetzt den Notizinhalt.

    Args:
        app: Die laufende App.
        ref: Die Notiz.

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    field = ft.TextField(value=ref.text, multiline=True, min_lines=4, max_lines=14, autofocus=True)
    hint = ft.Text("", size=12, color=ft.Colors.ERROR)

    async def save(_e) -> None:
        text = field.value or ""
        if not text.strip():
            hint.value = "Der Text ist leer. Zum Entfernen bitte „Löschen“ verwenden."
            hint.update()
            return
        app.page.pop_dialog()
        if text != ref.text:
            await app.act(lambda s: s.replace_note_text(ref.relpath, ref.planned_raw, ref.original, text))

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    return ft.AlertDialog(modal=True, title="Notiz bearbeiten", content=ft.Column([field, hint], tight=True),
                          actions=[ft.TextButton("Abbrechen", on_click=cancel), ft.Button("Speichern", on_click=save)])


def _delete_dialog(app: "MobileApp", ref: NoteRef) -> ft.AlertDialog:
    """Rückfrage vor dem Löschen mit einem Auszug der Notiz.

    Args:
        app: Die laufende App.
        ref: Die Notiz.

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    preview = ref.text if len(ref.text) <= 200 else ref.text[:200] + " …"

    async def confirm(_e) -> None:
        app.page.pop_dialog()
        await app.act(lambda s: s.delete_note(ref.relpath, ref.original))

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    return ft.AlertDialog(modal=True, title="Notiz löschen?",
                          content=ft.Column([ft.Text(preview, size=12, italic=True),
                                             ft.Text("Die vorherige Fassung bleibt als Backup erhalten.", size=12)],
                                            tight=True),
                          actions=[ft.TextButton("Abbrechen", on_click=cancel),
                                   ft.Button("Löschen", on_click=confirm, color=ft.Colors.ERROR)])
