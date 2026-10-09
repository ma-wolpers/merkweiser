"""Spike S1/S2: minimale Flet-Oberfläche zum Ausführen des Primitive-Selbsttests.

Wegwerfcode. Bewusst nur Aufrufe, die gegen Flet 0.86.5 nachgeprüft wurden:
``ft.FilePicker().get_directory_path()`` (Service, nur konstruieren),
``ft.StoragePaths().get_application_support_directory()``, ``ft.SafeArea``,
``ft.Button``, ``ft.TextField``. Der Bericht wird zusätzlich als Datei in den
Testordner geschrieben, damit er per Syncthing auf den PC gelangt (das
belegt zugleich die Syncthing-Übernahme).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import flet as ft

from merkweiser.core.primitives_probe import run_probe

DEFAULT_DIR = "/storage/emulated/0/MerkweiserSpike"


def _all_files_access_state() -> str:
    """Fragt per pyjnius ab, ob „Zugriff auf alle Dateien“ erteilt ist.

    Returns:
        Lesbarer Status, oder warum er nicht ermittelt werden konnte.
    """
    try:
        from jnius import autoclass  # nur auf Android vorhanden
        env = autoclass("android.os.Environment")
        return f"isExternalStorageManager={env.isExternalStorageManager()}"
    except Exception as exc:
        return f"pyjnius nicht nutzbar: {type(exc).__name__}: {exc}"


def _open_all_files_settings() -> str:
    """Öffnet die Android-Einstellungsseite für „Zugriff auf alle Dateien“.

    Returns:
        Ergebnis bzw. Fehlerbeschreibung (Spike-Befund).
    """
    try:
        from jnius import autoclass
        intent_cls = autoclass("android.content.Intent")
        settings = autoclass("android.provider.Settings")
        uri = autoclass("android.net.Uri")
        # Die Activity-Klasse von serious_python ist nicht verifiziert; die
        # aktuelle Application reicht mit FLAG_ACTIVITY_NEW_TASK zum Starten.
        ctx = autoclass("android.app.ActivityThread").currentApplication()
        intent = intent_cls(settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
        intent.setData(uri.parse("package:" + ctx.getPackageName()))
        intent.addFlags(intent_cls.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(intent)
        return "Einstellungsseite geöffnet"
    except Exception as exc:
        return f"Konnte Einstellungen nicht öffnen: {type(exc).__name__}: {exc}"


def _storage_access_state(test_dir: Path) -> list[str]:
    """Ermittelt den Zugriff auf den geteilten Speicher ohne pyjnius.

    Ohne „Zugriff auf alle Dateien“ darf eine App unter Android 11+ im Wurzel-
    verzeichnis des geteilten Speichers weder auflisten noch anlegen. Die
    Prüfung unterscheidet also zuverlässig „Berechtigung fehlt“ von anderen
    Fehlern, auch wenn ``isExternalStorageManager`` nicht abfragbar ist.

    Args:
        test_dir: Gewählter Testordner.

    Returns:
        Befundzeilen für den Bericht.
    """
    root = Path("/storage/emulated/0")
    lines = []
    for label, path in (("root", root), ("testordner", test_dir)):
        lines.append(f"{label}: exists={path.exists()} R={os.access(path, os.R_OK)} "
                     f"W={os.access(path, os.W_OK)}")
    try:
        lines.append(f"listdir(root): {len(os.listdir(root))} Einträge")
    except Exception as exc:
        lines.append(f"listdir(root): {type(exc).__name__}: {exc}")
    return lines


async def main(page: ft.Page) -> None:
    """Baut die Spike-Oberfläche auf.

    Args:
        page: Von Flet übergebene Seite.
    """
    page.title = "Merkweiser Spike S1/S2"
    page.scroll = ft.ScrollMode.AUTO
    folder = ft.TextField(label="Testordner", value=DEFAULT_DIR)
    out = ft.Text(selectable=True, size=12)
    picker = ft.FilePicker()
    try:
        app_data = Path(await ft.StoragePaths().get_application_support_directory())
    except Exception as exc:
        app_data = None
        out.value = f"StoragePaths fehlgeschlagen: {exc}"

    async def pick(_e) -> None:
        path = await picker.get_directory_path(dialog_title="Testordner wählen")
        out.value = f"get_directory_path -> {path!r}"
        if path:
            folder.value = path
        page.update()

    def perm(_e) -> None:
        out.value = _all_files_access_state() + "\n" + _open_all_files_settings()
        page.update()

    def run(_e) -> None:
        test_dir = Path(folder.value or DEFAULT_DIR)
        lines = [_all_files_access_state(), *_storage_access_state(test_dir)]
        try:
            if not test_dir.is_dir():
                lines.append(f"Testordner fehlt, lege an: {test_dir}")
                test_dir.mkdir(parents=True, exist_ok=True)
            lines += run_probe(test_dir, app_data)
        except Exception as exc:
            lines.append(f"FEHLER: {type(exc).__name__}: {exc}")
        name = f"mw-spike-bericht-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        # Bericht bevorzugt in den (synchronisierten) Testordner, sonst in den
        # App-Speicher, damit ein Befund nie verloren geht.
        for target in (test_dir, app_data):
            if target is None:
                continue
            try:
                (Path(target) / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
                lines.append(f"Bericht geschrieben: {Path(target) / name}")
                break
            except Exception as exc:
                lines.append(f"Bericht nach {target} fehlgeschlagen: {type(exc).__name__}: {exc}")
        out.value = "\n".join(lines)
        page.update()

    page.add(ft.SafeArea(content=ft.Column([
        ft.Text("Merkweiser Spike S1/S2 (nur synthetische Testdateien)", weight=ft.FontWeight.BOLD),
        ft.Text("Öffnet „Alle-Dateien-Zugriff“ keine Einstellungsseite: Einstellungen → Apps → "
                "Merkweiser Spike → Berechtigungen → Dateien → „Verwaltung aller Dateien zulassen“. "
                "Als Testordner den per Syncthing geteilten SyncSpike-Ordner wählen.", size=12),
        folder,
        ft.Row([ft.Button("Ordner wählen", on_click=pick),
                ft.Button("Alle-Dateien-Zugriff", on_click=perm),
                ft.Button("Test starten", on_click=run)], wrap=True),
        out,
    ])))
