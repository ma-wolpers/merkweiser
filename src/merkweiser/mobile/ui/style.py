"""Gemeinsame Farben der Mobile-Oberfläche (hell und dunkel lesbar).

Vergleichszeilen bekommen eine **halbtransparente Tönung** statt einer festen
Pastellfarbe: Feste Töne wie ``GREEN_100`` sind im Dark Mode unter der dort
hellen Schrift unlesbar (Gerätebefund 2026-10-21). Eine Tönung legt sich über
den jeweiligen Hintergrund, die Schrift behält ihre Themenfarbe. Die Präfixe
„−“/„+“ tragen die Bedeutung zusätzlich ohne Farbe.
"""

from __future__ import annotations

import flet as ft

#: Hintergrund für Zeilen nur in der Hauptdatei bzw. „vorher“.
DIFF_REMOVED = ft.Colors.with_opacity(0.25, ft.Colors.RED)

#: Hintergrund für Zeilen nur in der Konfliktversion bzw. „nachher“.
DIFF_ADDED = ft.Colors.with_opacity(0.25, ft.Colors.GREEN)

#: Schriftfarbe der Erläuterung unter einem Thema: deutlich schwächer als normaler
#: Text, aber als Tönung der Themen-Schriftfarbe hell und dunkel lesbar.
EXPLANATION = ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE)

#: Stern und Leiste je Dringlichkeitsstufe (``Urgency``-Wert → Symbol, Farbe, Tooltip).
#: Farbe ``None`` = Themenfarbe (farblos). Gelb und Rot sind hell und dunkel lesbar;
#: die Stufe steckt zusätzlich im Tooltip.
URGENCY_STYLE = {
    0: (ft.Icons.STAR_BORDER, None, "dringend markieren"),
    1: (ft.Icons.STAR, ft.Colors.AMBER, "dringend – nochmal tippen: sehr dringend"),
    2: (ft.Icons.STAR, ft.Colors.RED, "sehr dringend – nochmal tippen: nicht mehr dringend"),
}

#: Breite der farbigen Leiste links an offenen dringenden Todos.
URGENCY_BAR = 4
