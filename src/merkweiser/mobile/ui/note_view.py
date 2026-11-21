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

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import flet as ft

from ...app.ordering import urgent_first
from ...app.tag_spans import text_parts
from ...app.todo_tree import OPEN_ONLY, Fold, fold_key, fold_rows, hidden
from ...app.views import NoteRef, Row, next_urgency, note_ref, note_rows
from ...core.document import Document, ParsedNote
from ...core.inline import TodoStatus, Urgency, strip_urgency
from .note_dialogs import note_actions
from .tag_dialog import show_move_flow
from .style import ACTION_ICON, ACTION_SIZE, EXPLANATION, MISSED_STYLE, MISSED_TEXT, URGENCY_BAR, URGENCY_STYLE, card

if TYPE_CHECKING:
    from .app import MobileApp

INDENT = 18
MARKER_WIDTH = 40
SUB_MARK = "↳"
"""Kennzeichen eines Unter-Todos (W10), steht in der Einrückungslücke vor der Checkbox."""
FOLD_CLOSED = "▸ {} weitere"
FOLD_OPEN = "▾ einklappen"
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
    column = ([header] if header is not None else []) + fold_view(app, rows) + [note_actions(app, ref, extra(ref) if extra else ())]
    return card(column)


def fold_view(app: "MobileApp", rows: Sequence[Row], keep: frozenset[TodoStatus] = OPEN_ONLY) -> list[ft.Control]:
    """Zeilen als Baum mit einklappbaren Todos (W10; Faltregel ``todo_tree.fold_rows``).

    Ein Teilbaum mit Kindern wird eine Spalte. Verborgene Kinder (nicht
    ``pinned``) stecken je in einer eigenen Spalte, deren Sichtbarkeit die
    Schalter-Zeile „▸ N weitere“ / „▾ einklappen“ unter den Kindern umschaltet –
    direkt per ``update()``, ohne Neuzeichnen. Standard ist eingeklappt; der
    Zustand liegt je Sitzung in ``app._folds`` (``todo_tree.fold_key``).

    Args:
        app: Die laufende App.
        rows: Zeilen in Anzeigereihenfolge (z. B. nach ``urgent_first``).
        keep: Todo-Zustände, die eingeklappt sichtbar bleiben.

    Returns:
        Ein Control je Wurzel.
    """
    expanded: set = app.__dict__.setdefault("_folds", set())
    return [_fold_control(app, fold, expanded) for fold in fold_rows(rows, keep)]


def _fold_control(app: "MobileApp", fold: Fold, expanded: set) -> ft.Control:
    """Ein Teilbaum (siehe ``fold_view``)."""
    row = note_row(app, fold.row, fold.sub_todo)
    if not fold.children:
        return row
    key, count = fold_key(fold.row), hidden(fold)
    folded: list[ft.Control] = []
    children: list[ft.Control] = []
    for child in fold.children:
        control = _fold_control(app, child, expanded)
        if not child.pinned:
            control = ft.Column([control], visible=key in expanded)
            folded.append(control)
        children.append(control)
    box = ft.Column([row, *children])
    if not count:
        return box
    label = ft.Text(size=12, color=EXPLANATION)

    def show(is_open: bool) -> None:
        label.value = FOLD_OPEN if is_open else FOLD_CLOSED.format(count)
        for control in folded:
            control.visible = is_open

    async def toggle(_e) -> None:
        expanded.symmetric_difference_update({key})
        show(key in expanded)
        box.update()

    show(key in expanded)
    box.controls.append(ft.Container(content=label, on_click=toggle,
                                     padding=ft.Padding.only(left=(fold.row.depth + 1) * INDENT)))
    return box


def note_row(app: "MobileApp", row: Row, sub_todo: bool = False) -> ft.Control:
    """Eine Notizzeile samt weiterer Zeilen (Erläuterung bzw. Fortsetzungen).

    Ein Unter-Todo (W10) bekommt ``SUB_MARK`` in der Einrückungslücke vor der
    Checkbox; Checkbox und Textkante bleiben dadurch an derselben Stelle.

    Args:
        app: Die laufende App.
        row: Anzeigezeile aus ``note_rows``.
        sub_todo: Todo mit einem Todo als Vorfahr (``todo_tree.Fold.sub_todo``).

    Returns:
        Ein Control, eingerückt nach ``row.depth``.
    """
    lead = INDENT if sub_todo and row.depth else 0
    pad = ft.Padding.only(left=row.depth * INDENT - lead)
    if row.kind == "topic":
        head = rich_text(app, row.text, italic=True, color=EXPLANATION) if row.empty_topic \
            else rich_text(app, row.text, weight=ft.FontWeight.BOLD)
        lines = [head]
        lines += [rich_text(app, line, color=EXPLANATION) for line in row.more]
        return ft.Container(content=ft.Column(lines, spacing=2), padding=pad)
    if row.kind == "todo":
        head = todo_line(app, row.text, row.status, row.urgency, row.target)
        if lead:
            head = ft.Row([ft.Container(content=ft.Text(SUB_MARK, color=EXPLANATION), width=lead,
                                        alignment=ft.Alignment.CENTER_RIGHT),
                           ft.Container(content=head, expand=True)], spacing=0)
    elif row.kind == "item":
        head = marked(ft.Text("•", size=18), rich_text(app, row.text))
    else:
        return ft.Container(content=ft.Text("\n".join((row.text, *row.more))), padding=pad)
    continuation = [ft.Container(content=rich_text(app, line), padding=ft.Padding.only(left=lead + MARKER_WIDTH))
                    for line in row.more]
    return ft.Container(content=ft.Column([head, *continuation], spacing=0), padding=pad)


def todo_line(app: "MobileApp", text: str, status: TodoStatus, urgency: Urgency, target,
              open_note: Callable[[], None] | None = None) -> ft.Control:
    """Todo mit Checkbox, antippbarem Text und Schnellaktionen (Ampel-Stern, verpasst, verschieben).

    Der Stern zeigt die Stufe (farblos, gelb, rot; ``style.URGENCY_STYLE``) und
    schaltet beim Tippen zur nächsten (``views.next_urgency``); geschrieben wird
    der Zielzustand. Offene gelbe bzw. rote Todos haben links eine farbige Leiste.

    W9: Der ⊘-Knopf neben dem Stern schaltet zwischen verpasst und offen
    (von erledigt aus: verpasst). Die Checkbox kennt nur erledigt/offen; ein
    Tipp auf den Text erledigt ein offenes oder verpasstes Todo und öffnet ein
    erledigtes wieder. Verpasste Todos sind durchgestrichen und blass
    (``style.MISSED_TEXT``, ``EXPLANATION``) und haben keine Ampel-Leiste.

    Args:
        app: Die laufende App.
        text: Inhalt ohne Checkbox (Markierung wird für die Anzeige entfernt).
        status: Todo-Zustand (``OPEN``, ``DONE`` oder ``MISSED``).
        urgency: Angezeigte Dringlichkeitsstufe.
        target: Adresse des Todos.
        open_note: Nur im Tab „Todos“: öffnet die Unterseite mit der ganzen Notiz
            (zusätzlicher Knopf rechts, W7).

    Returns:
        Eine Zeile mit Markerspalte, Text und den Symbolknöpfen.
    """
    missed = status is TodoStatus.MISSED

    async def set_status(value: TodoStatus) -> None:
        await app.act(lambda s: s.set_status(target, value))

    async def toggle(e) -> None:
        await set_status(TodoStatus.DONE if e.control.value else TodoStatus.OPEN)

    async def tap(_e) -> None:
        await set_status(TodoStatus.OPEN if status is TodoStatus.DONE else TodoStatus.DONE)

    async def miss(_e) -> None:
        await set_status(TodoStatus.OPEN if missed else TodoStatus.MISSED)

    async def cycle(_e) -> None:
        await app.act(lambda s: s.set_urgency(target, next_urgency(urgency)))

    async def move(_e) -> None:
        await show_move_flow(app, target)

    icon, color, tooltip = URGENCY_STYLE[int(urgency)]
    miss_icon, miss_color, miss_tip = MISSED_STYLE[missed]
    checkbox = ft.Checkbox(value=status is TodoStatus.DONE, on_change=toggle, visual_density=ft.VisualDensity.COMPACT)
    label = rich_text(app, strip_urgency(text), style=MISSED_TEXT, color=EXPLANATION) if missed \
        else rich_text(app, strip_urgency(text))
    line = marked(checkbox, ft.GestureDetector(content=label, on_tap=tap), [
        action_button(icon, cycle, tooltip, color),
        action_button(miss_icon, miss, miss_tip, miss_color),
        action_button(ft.Icons.EVENT, move, "verschieben …"),
        *([action_button(ft.Icons.ARTICLE_OUTLINED, lambda _e: open_note(), "Notiz öffnen")] if open_note else []),
    ])
    return urgency_bar(line, urgency, status is TodoStatus.OPEN)


def action_button(icon, on_click, tooltip: str, color=None) -> ft.IconButton:
    """Kompakter Symbolknopf am Ende einer Todo-Zeile (einzige Stelle für Größe und Abstand, W10).

    Kleiner als der Flet-Standard (``style.ACTION_ICON``/``ACTION_SIZE``), damit
    vier Knöpfe neben dem Text Platz lassen.

    Args:
        icon: Symbol.
        on_click: Handler.
        tooltip: Tooltip (trägt die Bedeutung zusätzlich zur Farbe).
        color: Symbolfarbe oder ``None`` (Themenfarbe).

    Returns:
        Der Knopf.
    """
    return ft.IconButton(icon=icon, icon_color=color, on_click=on_click, tooltip=tooltip, icon_size=ACTION_ICON,
                         padding=ft.Padding.all(4), visual_density=ft.VisualDensity.COMPACT,
                         size_constraints=ft.BoxConstraints(min_width=ACTION_SIZE, min_height=ACTION_SIZE))


def urgency_bar(content: ft.Control, urgency: Urgency, is_open: bool) -> ft.Container:
    """Farbige Leiste links an offenen gelben bzw. roten Todos (einzige Stelle; auch für Vorschauzeilen, W9).

    Args:
        content: Die Todo-Zeile.
        urgency: Dringlichkeitsstufe.
        is_open: Nur offene Todos bekommen eine Leiste.

    Returns:
        Container um ``content``, mit Leiste in der Farbe aus ``style.URGENCY_STYLE``.
    """
    color = URGENCY_STYLE[int(urgency)][1] if urgency and is_open else None
    return ft.Container(content=content, border=ft.Border.only(left=ft.BorderSide(URGENCY_BAR, color)) if color else None)


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


def marked(marker: ft.Control, body: ft.Control, actions: list[ft.Control] | None = None) -> ft.Control:
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
