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
