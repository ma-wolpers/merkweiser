"""Notiz anlegen, bearbeiten und löschen (Mobile): Knopfleiste je Notiz und die Dialoge.

``editor_dialog`` ist der **einzige** Notiz-Editor: „Neue Notiz“ öffnet ihn
leer (``new_note_dialog`` → ``append_note``), „Bearbeiten“ mit dem Notiztext.

Bearbeiten und Löschen adressieren die Notiz über ``NoteRef`` (Inhaltszeilen beim
Öffnen, keine IDs) und laufen über ``NotesService``:

* **Bearbeiten** ersetzt den Notiztext (``replace_note_text``). Hat sich die
  Notiz inzwischen verändert und ist nicht mehr eindeutig auffindbar, landet
  die bearbeitete Fassung als eigene Konfliktdatei; ``MobileApp.act`` meldet das.
* **Löschen** entfernt die Notiz samt einem angrenzenden Trenner
  (``delete_note``) erst nach Rückfrage. Die vorherige Datei bleibt als Backup
  im Op-Verzeichnis (Aufbewahrung laut Einstellungen).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Awaitable, Callable

import flet as ft

from ...app.views import NoteRef
from .note_editor import editor_toolbar

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


def editor_dialog(app: "MobileApp", text: str, on_save: Callable[[str], Awaitable[None]],
                  empty_hint: str) -> ft.AlertDialog:
    """Der eine Notiz-Editor (SSOT für „Bearbeiten“ und „Neue Notiz“).

    Ohne Titel, damit mit offener Tastatur mehr Platz für das Feld bleibt;
    höchstens 9 Zeilen (danach scrollt das Feld), der Dialog selbst ist
    scrollbar, damit „Abbrechen“ und „Speichern“ erreichbar bleiben
    (Nutzerbefunde 2026-10-22).

    Args:
        app: Die laufende App.
        text: Anfangstext (leer für eine neue Notiz).
        on_save: Wird mit dem nicht leeren Text aufgerufen, nachdem der Dialog geschlossen ist.
        empty_hint: Meldung bei leerem Text (der Dialog bleibt dann offen).

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    field = ft.TextField(value=text, multiline=True, min_lines=3, max_lines=9, autofocus=True)
    hint = ft.Text("", size=12, color=ft.Colors.ERROR)

    async def save(_e) -> None:
        value = field.value or ""
        if not value.strip():
            hint.value = empty_hint
            hint.update()
            return
        app.page.pop_dialog()
        await on_save(value)

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    return ft.AlertDialog(modal=True, scrollable=True,
                          content=ft.Column([editor_toolbar(field), field, hint], tight=True),
                          actions=[ft.TextButton("Abbrechen", on_click=cancel), ft.Button("Speichern", on_click=save)])


def _edit_dialog(app: "MobileApp", ref: NoteRef) -> ft.AlertDialog:
    """Editor mit dem Rohtext der Notiz; „Speichern“ ersetzt den Notizinhalt (nur bei Änderung).

    Args:
        app: Die laufende App.
        ref: Die Notiz.

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    async def replace(text: str) -> None:
        if text != ref.text:
            await app.act(lambda s: s.replace_note_text(ref.relpath, ref.planned_raw, ref.original, text))

    return editor_dialog(app, ref.text, replace, "Der Text ist leer. Zum Entfernen bitte „Löschen“ verwenden.")


def new_note_dialog(app: "MobileApp", day: date) -> ft.AlertDialog:
    """Leerer Editor; „Speichern“ hängt die Notiz an die Tagesdatei von ``day`` an (legt sie bei Bedarf an).

    Args:
        app: Die laufende App.
        day: Tag der neuen Notiz.

    Returns:
        Der (noch nicht geöffnete) Dialog.
    """
    async def append(text: str) -> None:
        await app.act(lambda s: s.append_note(text, day))

    return editor_dialog(app, "", append, "Der Text ist leer.")


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
