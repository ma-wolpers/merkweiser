"""Zeilenbasierter, konservativer Merge (PLAN.md, Abschnitt „Merge“).

* ``align``: Ausrichtung mit eindeutigen Ankern (Patience-Prinzip).
* ``model``: gemeinsames Datenmodell (Zuordnung, Zertifikate, Hunks) und R1/R2.
* ``diff3``: 3-Wege-Merge mit verlässlicher Basis.
* ``union``: 2-Wege-Fallback ohne Basis.
* ``verify``: unabhängige Verlustprüfung über Zuordnung und Zertifikate.
"""
