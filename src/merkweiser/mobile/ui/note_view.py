"""Darstellung von Notizzeilen (Mobile): Thema, Erläuterung, Punkte, Todos, Fortsetzungen.

Layout (Nutzerwunsch vom 2026-10-21):

* **Thema** fett, die **Erläuterung** direkt darunter in deutlich schwächerer
  Schrift (``style.EXPLANATION``, hell und dunkel lesbar).
* **Todos und Listenpunkte** haben eine gleich breite Markerspalte (Checkbox
  bzw. „•“), damit ihre Texte auf derselben Kante stehen.
* **Fortsetzungen** stehen auf dieser Textkante unter ihrem Punkt.

Ein Tipp auf den Todo-Text hakt ab wie ein Tipp auf die Checkbox. „verschieben …“
startet ``tag_dialog.show_move_flow`` (Tag-Dialog nur bei weiteren Todos der Notiz).

W1/W2/W7 (PLAN-SPAETERE-SCHRITTE.md): Offene dringende Todos stehen je
Geschwistergruppe oben, Rot vor Gelb (``ordering.urgent_first``, nur Anzeige). Tags im Text
sind fett in der Primärfarbe und öffnen per Tipp die Tag-Seite
(``MobileApp.open_tag``); ``rich_text`` nutzt dafür ``TextSpan.on_click``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from ...app.ordering import urgent_first
from ...app.tag_spans import text_parts
from ...app.views import NoteRef, Row, next_urgency, note_ref, note_rows
from ...core.document import Document, ParsedNote
from ...core.inline import Urgency, strip_urgency
from .note_dialogs import note_actions
from .tag_dialog import show_move_flow
from .style import EXPLANATION, URGENCY_BAR, URGENCY_STYLE

if TYPE_CHECKING:
    from .app import MobileApp

INDENT = 18
MARKER_WIDTH = 40
TAG_STYLE = ft.TextStyle(weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY)


def note_card(app: "MobileApp", relpath: str, doc: Document, note: ParsedNote,
              header: ft.Control | None = None,
              extra: Callable[[NoteRef], list[ft.Control]] | None = None) -> ft.Control | None:
    """Eine ganze Notiz als Karte: Zeilen, Aktionsleiste (bearbeiten, löschen), optional ein Kopf.

    Genutzt vom Tab „Tag“ und von der Suche; die Targets stammen immer aus dem
    übergebenen, frisch gelesenen Dokument.

    Args:
        app: Die laufende App.
        relpath: Tagesdatei.
        doc: Dokument der Datei.
        note: Die Notiz.
        header: Optionaler Kopf über der Notiz (z. B. das Datum in der Suche).
        extra: Zusätzliche Aktionen aus der Notizadresse; nur die Notiz-Unterseite
            setzt sie („Notiz verschieben“, W7).

    Returns:
        Die Karte oder ``None`` bei einer Notiz ohne anzeigbare Zeilen.
    """
    rows = urgent_first(note_rows(relpath, doc, note))
    ref = note_ref(relpath, doc, note)
    if not rows or ref is None:
        return None
    column = ([header] if header is not None else []) + [note_row(app, r) for r in rows] + [note_actions(app, ref, extra(ref) if extra else ())]
    return ft.Container(content=ft.Column(column), padding=8, border_radius=8, bgcolor=ft.Colors.SURFACE_CONTAINER)


def note_row(app: "MobileApp", row: Row) -> ft.Control:
    """Eine Notizzeile samt weiterer Zeilen (Erläuterung bzw. Fortsetzungen).

    Args:
        app: Die laufende App.
        row: Anzeigezeile aus ``note_rows``.

    Returns:
        Ein Control, eingerückt nach ``row.depth``.
    """
    pad = ft.Padding.only(left=row.depth * INDENT)
    if row.kind == "topic":
        head = rich_text(app, row.text, italic=True, color=EXPLANATION) if row.empty_topic \
            else rich_text(app, row.text, weight=ft.FontWeight.BOLD)
        lines = [head]
        lines += [rich_text(app, line, color=EXPLANATION) for line in row.more]
        return ft.Container(content=ft.Column(lines, spacing=2), padding=pad)
    if row.kind == "todo":
        head = todo_line(app, row.text, row.done, row.urgency, row.target)
    elif row.kind == "item":
        head = _marked(ft.Text("•", size=18), rich_text(app, row.text))
    else:
        return ft.Container(content=ft.Text("\n".join((row.text, *row.more))), padding=pad)
    continuation = [ft.Container(content=rich_text(app, line), padding=ft.Padding.only(left=MARKER_WIDTH))
                    for line in row.more]
    return ft.Container(content=ft.Column([head, *continuation], spacing=0), padding=pad)


def todo_line(app: "MobileApp", text: str, done: bool | None, urgency: Urgency, target,
              open_note: Callable[[], None] | None = None) -> ft.Control:
    """Todo mit Checkbox, antippbarem Text und Schnellaktionen (Ampel-Stern, verschieben).

    Der Stern zeigt die Stufe (farblos, gelb, rot; ``style.URGENCY_STYLE``) und
    schaltet beim Tippen zur nächsten (``views.next_urgency``); geschrieben wird
    der Zielzustand. Offene gelbe bzw. rote Todos haben links eine farbige Leiste.

    Args:
        app: Die laufende App.
        text: Inhalt ohne Checkbox (Markierung wird für die Anzeige entfernt).
        done: Erledigt-Status.
        urgency: Angezeigte Dringlichkeitsstufe.
        target: Adresse des Todos.
        open_note: Nur im Tab „Todos“: öffnet die Unterseite mit der ganzen Notiz
            (zusätzlicher Knopf rechts, W7).

    Returns:
        Eine Zeile mit Markerspalte, Text und den Symbolknöpfen.
    """
    async def set_done(value: bool) -> None:
        await app.act(lambda s: s.set_done(target, value))

    async def toggle(e) -> None:
        await set_done(bool(e.control.value))

    async def tap(_e) -> None:
        await set_done(not done)

    async def cycle(_e) -> None:
        await app.act(lambda s: s.set_urgency(target, next_urgency(urgency)))

    async def move(_e) -> None:
        await show_move_flow(app, target)

    icon, color, tooltip = URGENCY_STYLE[int(urgency)]
    checkbox = ft.Checkbox(value=bool(done), on_change=toggle, visual_density=ft.VisualDensity.COMPACT)
    line = _marked(checkbox, ft.GestureDetector(content=rich_text(app, strip_urgency(text)), on_tap=tap), [
        ft.IconButton(icon=icon, icon_color=color, on_click=cycle, tooltip=tooltip),
        ft.IconButton(icon=ft.Icons.EVENT, on_click=move, tooltip="verschieben …"),
        *([ft.IconButton(icon=ft.Icons.ARTICLE_OUTLINED, on_click=lambda _e: open_note(), tooltip="Notiz öffnen")]
          if open_note else []),
    ])
    bar = color if urgency and done is False else None
    return ft.Container(content=line, border=ft.Border.only(left=ft.BorderSide(URGENCY_BAR, bar)) if bar else None)


def rich_text(app: "MobileApp", text: str, **style) -> ft.Text:
    """Text, dessen Tags antippbar sind (öffnen die Tag-Seite).

    Ohne Tags entsteht ein gewöhnliches ``ft.Text(text)``; mit Tags ein
    ``ft.Text(spans=…)``, in dem jeder Tag ein eigener ``TextSpan`` mit
    ``on_click`` ist. Der Handler greift erst beim Tippen auf ``app`` zu.

    Args:
        app: Die laufende App.
        text: Anzeigetext.
        **style: Weitere ``ft.Text``-Eigenschaften (z. B. ``weight``, ``color``).

    Returns:
        Das Text-Control.
    """
    parts = text_parts(text)
    if all(tag is None for _piece, tag in parts):
        return ft.Text(text, **style)

    def opener(tag: str):
        async def click(_e) -> None:
            app.open_tag(tag)
        return click

    spans = [ft.TextSpan(text=piece, style=TAG_STYLE, on_click=opener(tag)) if tag else ft.TextSpan(text=piece)
             for piece, tag in parts]
    return ft.Text(spans=spans, **style)


def _marked(marker: ft.Control, body: ft.Control, actions: list[ft.Control] | None = None) -> ft.Control:
    """Zeile aus fester Markerspalte, Text (füllt die Breite) und optionalen Knöpfen.

    Args:
        marker: Checkbox oder Aufzählungszeichen.
        body: Text bzw. antippbarer Text.
        actions: Symbolknöpfe am Zeilenende.

    Returns:
        Die Zeile; alle Texte beginnen bei ``MARKER_WIDTH``.
    """
    return ft.Row([ft.Container(content=marker, width=MARKER_WIDTH, alignment=ft.Alignment.CENTER),
                   ft.Container(content=body, expand=True), *(actions or [])],
                  spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
