"""Dialog „Routine anlegen/bearbeiten“ (W9): Text, Ampel, Rhythmus, Frist, Pausen, Tags, aktiv.

Die Felder passen sich der Rhythmus-Art an (Wochentage nur bei wöchentlich
und alle n Wochen, Abstand und Starttag nur bei alle n Tagen/Wochen, …).
Darunter steht laufend „Nächste: …“ bzw. die Fehlermeldung des Formulars
(``routine_views.upcoming``, dieselbe Grammatik wie die Datei). Gespeichert
wird erst, wenn das Formular gültig ist (``routine_service.save_rule``).
„Heute schon eintragen“ gibt es nur für neue Regeln; vorbelegt, wenn sie
heute fällig ist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ...app import routine_service
from ...app.routine_views import KIND_LABELS, RuleForm, due_today, form_of, new_form, upcoming
from ...app.views import next_urgency
from ...core.edits import with_urgency
from ...core.inline import urgency
from ...core.patch import Target
from ...core.rhythm import WEEKDAYS, Kind, RhythmError
from ...core.routines import ROUTINES_FILE, RuleItem, Section
from .date_pick import open_date_picker
from .style import URGENCY_STYLE

if TYPE_CHECKING:
    from .app import MobileApp

_FIELDS_BY_KIND = {
    Kind.WOECHENTLICH: {"weekdays"}, Kind.WOCHEN: {"weekdays", "interval", "start"}, Kind.TAGE: {"interval", "start"},
    Kind.MONATLICH: {"month_days"}, Kind.JAEHRLICH: {"yearly"},
}
"""Welche Rhythmus-Felder je Art sichtbar sind (übrige Arten: keine)."""


def show_rule_dialog(app: "MobileApp", found: tuple[Section, RuleItem] | None = None) -> None:
    """Öffnet den Dialog für eine neue (``found=None``) oder vorhandene Regel.

    Args:
        app: Die laufende App.
        found: Abschnitt und Regel aus ``parse_routines`` bzw. ``routine_views.find_rule``.
    """
    today = app.service.clock.today()
    rf = routine_service.load(app.service)
    form = form_of(*found) if found else new_form(today)
    original = Target(ROUTINES_FILE, found[1].line_no, found[1].line) if found else None
    fields = _fields(form)
    today_switch = ft.Switch(label="Heute schon eintragen", value=due_today(form, rf, today), visible=found is None)
    hint = ft.Text(upcoming(form, rf, today), size=12)
    star = ft.IconButton(icon=URGENCY_STYLE[int(urgency(form.body))][0])

    def read() -> RuleForm:
        values = {name: control.value for name, control in fields.items() if hasattr(control, "value")}
        return RuleForm(body=values["body"] or "", kind=Kind(values["kind"]),
                        weekdays=tuple(int(v) for v in fields["weekdays"].selected or []),
                        interval=values["interval"] or "", start=form.start, month_days=values["month_days"] or "",
                        yearly=form.yearly, frist=values["frist"] or "", in_pauses=bool(values["in_pauses"]),
                        tags=values["tags"] or "", active=bool(values["active"]))

    def refresh(_e=None) -> None:
        current = read()
        visible = _FIELDS_BY_KIND.get(current.kind, set())
        for name in ("weekdays", "interval", "start", "month_days", "yearly"):
            fields[name].visible = name in visible
        fields["start"].content = f"ab {current.start:%d.%m.%Y}" if current.start else "Starttag wählen"
        fields["yearly"].content = f"am {current.yearly:%d.%m.}" if current.yearly else "Datum wählen"
        _icon, color, tooltip = URGENCY_STYLE[int(urgency(current.body))]
        star.icon, star.icon_color, star.tooltip = _icon, color, tooltip
        hint.value = upcoming(current, rf, today)
        app.page.update()

    async def cycle(_e) -> None:
        body = fields["body"].value or ""
        try:
            fields["body"].value = with_urgency(body, next_urgency(urgency(body)))
        except ValueError as exc:
            hint.value = str(exc)
        refresh()

    def picker(attribute: str, title: str):
        async def pick(_e) -> None:
            async def chosen(day) -> None:
                setattr(form, attribute, day)
                refresh()
            open_date_picker(app, getattr(form, attribute) or today, title, chosen)
        return pick

    async def save(_e) -> None:
        current = read()
        try:
            current.rhythm(), current.options(), current.line()
        except (RhythmError, ValueError) as exc:
            hint.value = str(exc)
            app.page.update()
            return
        app.page.pop_dialog()
        message = await app.act(lambda s: routine_service.save_rule(s, original, current, bool(today_switch.value)))
        if message:
            app.say(message)

    async def delete(_e) -> None:
        app.page.pop_dialog()
        message = await app.act(lambda s: routine_service.delete_rule_at(s, original))
        if message:
            app.say(message)

    async def cancel(_e) -> None:
        app.page.pop_dialog()

    star.on_click = cycle
    fields["start"].on_click = picker("start", "Starttag")
    fields["yearly"].on_click = picker("yearly", "Jährlich am")
    for name in ("kind", "weekdays", "interval", "month_days", "frist", "in_pauses", "body", "active"):
        control = fields[name]
        if isinstance(control, ft.Dropdown):
            control.on_select = refresh
        else:
            control.on_change = refresh
    content = ft.Column([ft.Row([fields["body"], star]), fields["kind"], fields["weekdays"], fields["interval"],
                         fields["start"], fields["month_days"], fields["yearly"], fields["frist"],
                         fields["in_pauses"], fields["tags"], fields["active"], today_switch, hint],
                        tight=True, scroll=ft.ScrollMode.AUTO)
    actions = ([ft.TextButton("Löschen", on_click=delete)] if found else []) + [
        ft.TextButton("Abbrechen", on_click=cancel), ft.TextButton("Speichern", on_click=save)]
    app.page.show_dialog(ft.AlertDialog(modal=True, scrollable=True, content=content, actions=actions,
                                        title="Routine bearbeiten" if found else "Neue Routine"))
    refresh()


def _fields(form: RuleForm) -> dict[str, ft.Control]:
    """Die Eingabefelder, vorbelegt aus dem Formular."""
    return {
        "body": ft.TextField(label="Todo", value=form.body, expand=True),
        "kind": ft.Dropdown(label="Rhythmus", value=form.kind.value,
                            options=[ft.DropdownOption(key=k.value, text=label) for k, label in KIND_LABELS.items()]),
        "weekdays": ft.SegmentedButton(allow_multiple_selection=True, allow_empty_selection=True,
                                       selected=[str(d) for d in form.weekdays], show_selected_icon=False,
                                       segments=[ft.Segment(value=str(i), label=ft.Text(name))
                                                 for i, name in enumerate(WEEKDAYS)]),
        "interval": ft.TextField(label="alle n (Tage bzw. Wochen)", value=form.interval,
                                 keyboard_type=ft.KeyboardType.NUMBER),
        "start": ft.TextButton("Starttag wählen"),
        "month_days": ft.TextField(label="Monatstage, z. B. 1, 15", value=form.month_days),
        "yearly": ft.TextButton("Datum wählen"),
        "frist": ft.TextField(label="Frist in Tagen (leer = bis zur nächsten Fälligkeit)", value=form.frist,
                              keyboard_type=ft.KeyboardType.NUMBER),
        "in_pauses": ft.Switch(label="auch in Pausen", value=form.in_pauses),
        "tags": ft.TextField(label="Tags für alle Todos dieses Rhythmus (optional)", value=form.tags),
        "active": ft.Switch(label="aktiv (aus = pausiert)", value=form.active),
    }
