"""Diagnosebericht: Zustand von App und Notizordner als Textdatei (für Gerätetests).

Der Bericht enthält **keine Notizinhalte**, nur Metadaten: Version und
Plattform, Notizordner, Schreibvariante und -garantie, Anzahl der
Tagesdateien, Konfliktdateien (Namen), unvollständige Vorgänge (Op-ID, Art,
Zustand, Pfad), den letzten Startbericht und die letzten Statusmeldungen.

Er wird exklusiv angelegt (nie überschreiben) als
``merkweiser-diagnose-YYYYMMDD-HHMMSS.txt``, typischerweise in einem per
Syncthing geteilten Ordner außerhalb des Vaults.
"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .. import __version__
from .notes_service import NotesService, StartReport
from .settings import Settings


def build_report(settings: Settings, service: NotesService | None, report: StartReport | None,
                 messages: Iterable[tuple[datetime, str]], now: datetime,
                 extra: dict[str, str] | None = None) -> str:
    """Baut den Berichtstext.

    Args:
        settings: Aktuelle Einstellungen.
        service: Geöffneter Vault oder ``None`` (Einrichtung, Öffnen gescheitert).
        report: Startbericht des Vaults oder ``None``.
        messages: Letzte Statusmeldungen als ``(Zeitpunkt, Text)``, älteste zuerst.
        now: Erstellungszeitpunkt.
        extra: Zusätzliche Umgebungsangaben der Oberfläche (z. B. Flet-Version).

    Returns:
        Bericht als Text mit ``\\n``-Zeilenenden.
    """
    lines = [f"Merkweiser-Diagnose {now:%Y-%m-%d %H:%M:%S}",
             f"merkweiser={__version__} python={sys.version.split()[0]} "
             f"platform={sys.platform} machine={platform.machine()}"]
    lines += [f"{key}={value}" for key, value in (extra or {}).items()]
    lines += ["", "[Einstellungen]", f"vault={settings.vault}", f"pattern={settings.pattern}",
              f"project_prefix={settings.project_prefix}", f"poll_seconds={settings.poll_seconds}",
              f"retention_days={settings.retention_days}"]
    lines += ["", "[Notizordner]"] + _vault_lines(settings, service)
    lines += ["", "[Startbericht]"] + _start_lines(report)
    lines += ["", "[Letzte Meldungen]"] + ([f"{at:%H:%M:%S} {text}" for at, text in messages] or ["(keine)"])
    return "\n".join(lines) + "\n"


def write_report(folder: Path, text: str, now: datetime) -> Path:
    """Legt den Bericht exklusiv im Ordner an (bei Namensgleichheit mit Zähler).

    Args:
        folder: Zielordner (muss existieren).
        text: Berichtstext.
        now: Zeitpunkt für den Dateinamen.

    Returns:
        Pfad der neuen Datei.

    Raises:
        OSError: Ordner fehlt oder ist nicht beschreibbar.
    """
    stem = f"merkweiser-diagnose-{now:%Y%m%d-%H%M%S}"
    for number in range(100):
        path = folder / (f"{stem}.txt" if number == 0 else f"{stem}-{number}.txt")
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
        return path
    raise FileExistsError(f"Zu viele Berichte mit dem Namen {stem} in {folder}")


def _vault_lines(settings: Settings, service: NotesService | None) -> list[str]:
    """Zustand des Notizordners (oder warum er nicht geöffnet ist).

    Args:
        settings: Einstellungen (für den Pfad).
        service: Geöffneter Vault oder ``None``.

    Returns:
        Berichtszeilen.
    """
    if service is None:
        root = Path(settings.vault) if settings.vault else None
        state = "nicht eingestellt" if root is None else (
            f"nicht geöffnet (existiert={root.is_dir()}, "
            f"lesbar={os.access(root, os.R_OK)}, schreibbar={os.access(root, os.W_OK)})")
        return [f"status={state}"]
    index = service.index
    lines = [f"install_mode={service.fs.install_mode}", f"schreibgeschuetzt={service.read_only}",
             f"schreibgarantie={service.write_guarantee}",
             f"tagesdateien={sum(len(p) for p in index.day_files.values())}",
             f"konfliktdateien={len(index.conflicts)}"]
    lines += [f"  konflikt {c.relpath}" for c in index.conflicts]
    open_ops = [op_id for op_id in service.store.all_ids() if not service.store.is_final(op_id)]
    lines.append(f"unvollstaendige_vorgaenge={len(open_ops)}")
    for op_id in open_ops:
        manifest, state = service.store.read(op_id)
        lines.append(f"  op {op_id} art={manifest.get('art')} zustand={state.get('zustand')} "
                     f"pfad={manifest.get('relpath')}")
    lines.append(f"belegt={sorted(service.busy)}")
    return lines


def _start_lines(report: StartReport | None) -> list[str]:
    """Kurzfassung des Startberichts.

    Args:
        report: Startbericht oder ``None``.

    Returns:
        Berichtszeilen.
    """
    if report is None:
        return ["(kein Start)"]
    recovery = report.recovery
    return [f"wiederhergestellt={len(recovery.results)} nicht_ausgefuehrt={len(recovery.not_applied)} "
            f"verwaist={len(recovery.orphans)}",
            f"resolves={len(report.resolves)} moves={[m.state for m in report.moves]} "
            f"automerges={len(report.automerges)}"]
