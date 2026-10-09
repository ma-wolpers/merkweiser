"""Spike S2: Platzhalter für das Desktop-Paket.

Importiert absichtlich ``tkinter``, um zu prüfen, dass ein im ``src/``
liegendes, aber auf Android nie importiertes Desktop-Paket den APK-Build
nicht stört.
"""

import tkinter  # noqa: F401  (S2-Prüfung, auf Android nie importiert)
