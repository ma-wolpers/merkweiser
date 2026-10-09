"""Flet-Einstieg (Shim) des Spikes, Muster wie namenfit-mobile ``src/main.py``."""

from merkweiser.mobile.spike_app import main

if __name__ == "__main__":
    import flet as ft

    ft.run(main)
