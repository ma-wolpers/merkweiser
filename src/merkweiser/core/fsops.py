"""Dateisystem-Primitive des Tausch-Protokolls (PLAN.md, „Schreibprotokoll“).

Einzige Stelle, die plattformabhängige Dateioperationen kennt. Alle
Operationen laufen über ein ``FsOps``-Objekt, damit Tests an **jeder**
Protokollgrenze einen Prozessabbruch simulieren können (``crash_at``).

* ``create_exclusive``: legt eine Datei nur an, wenn sie nicht existiert
  (``O_CREAT|O_EXCL``), schreibt, ``fsync``.
* ``rename_no_replace``: atomares Umbenennen, das ein vorhandenes Ziel **nie**
  überschreibt. Windows: ``os.rename`` (schlägt bei vorhandenem Ziel fehl).
  POSIX: ``os.link`` + ``unlink`` (``link`` schlägt bei vorhandenem Ziel fehl).
  Fallback ``excl`` (nur Android-Shared-Storage ohne ``link``): Existenz
  prüfen, exklusiv anlegen, kopieren, Quelle löschen (GRENZE A1–A3).
* ``write_lock``: Windows-Schreibsperre (Handle mit verweigerter
  Schreib-Freigabe, Löschen erlaubt), solange das Protokoll läuft; auf POSIX
  wirkungslos (dort sichert die Quarantäne ab).
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import Callable, Iterator


class FileBusyError(OSError):
    """Ein anderer Prozess hält die Datei zum Schreiben geöffnet (Windows)."""


class SimulatedCrash(BaseException):
    """Nur in Tests: simulierter Prozessabbruch an einer benannten Grenze."""


class FsOps:
    """Echte Dateioperationen plus Haken für Fault-Injection.

    Args:
        install_mode: ``"atomic"`` (Rename/Link ohne Überschreiben) oder
            ``"excl"`` (Android-Fallback, eingeschränkt).
        crash_at: Nur Tests: wird mit dem Namen jeder Protokollgrenze
            aufgerufen und darf ``SimulatedCrash`` werfen.
    """

    def __init__(self, install_mode: str = "atomic", crash_at: Callable[[str], None] | None = None) -> None:
        if install_mode not in ("atomic", "excl"):
            raise ValueError(install_mode)
        self.install_mode = install_mode
        self._crash_at = crash_at or (lambda _point: None)

    def point(self, name: str) -> None:
        """Markiert eine Protokollgrenze (für simulierte Abbrüche in Tests).

        Args:
            name: Name der Grenze, z. B. ``"write:after_displace"``.
        """
        self._crash_at(name)

    def read_bytes(self, path: Path) -> bytes:
        """Liest eine Datei vollständig."""
        return path.read_bytes()

    def exists(self, path: Path) -> bool:
        """``True``, wenn der Pfad existiert."""
        return os.path.lexists(path)

    def create_exclusive(self, path: Path, data: bytes) -> None:
        """Legt eine Datei exklusiv an, schreibt und synchronisiert sie.

        Args:
            path: Zielpfad (darf nicht existieren).
            data: Inhalt.

        Raises:
            FileExistsError: Pfad existiert bereits.
        """
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o644)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)

    def rename_no_replace(self, src: Path, dst: Path) -> None:
        """Benennt atomar um, ohne ein vorhandenes Ziel zu überschreiben.

        Args:
            src: Quelle.
            dst: Ziel (darf nicht existieren).

        Raises:
            FileExistsError: Ziel existiert.
        """
        if self.install_mode == "excl":
            self.create_exclusive(dst, src.read_bytes())
            os.unlink(src)
        elif sys.platform == "win32":
            os.rename(src, dst)
        else:
            os.link(src, dst)
            os.unlink(src)
        self.fsync_dir(dst.parent)

    def remove(self, path: Path) -> None:
        """Entfernt eine Datei (nur nach den Regeln der Löschinvariante aufrufen)."""
        os.unlink(path)
        self.fsync_dir(path.parent)

    def fsync_dir(self, folder: Path) -> None:
        """Synchronisiert ein Verzeichnis, soweit die Plattform es erlaubt (Windows: nein)."""
        if sys.platform == "win32":
            return
        with contextlib.suppress(OSError):
            fd = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    @contextlib.contextmanager
    def write_lock(self, path: Path) -> Iterator[None]:
        """Hält während des Tauschs eine Schreibsperre (nur Windows).

        Args:
            path: Datei, die gleich verdrängt wird.

        Raises:
            FileBusyError: ein anderer Prozess hat die Datei zum Schreiben offen.
        """
        if sys.platform != "win32" or not path.exists():
            yield
            return
        handle = _win_open_deny_write(path)
        try:
            yield
        finally:
            _win_close(handle)


def _win_open_deny_write(path: Path) -> int:
    """Öffnet eine Datei unter Windows mit Freigabe nur für Lesen und Löschen.

    Args:
        path: Datei.

    Returns:
        Windows-Handle.

    Raises:
        FileBusyError: bei Sharing-Violation (Fremder hält Schreibzugriff).
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    # Nur Lesezugriff anfordern: Ein DELETE-Zugriff am eigenen Handle würde jedes
    # spätere ``open`` ohne FILE_SHARE_DELETE (z. B. Pythons ``open``) blockieren,
    # auch unser eigenes Lesen der verdrängten Datei. Für ``os.rename`` genügt,
    # dass dieses Handle das Löschen *erlaubt* (Share-Mode).
    generic_read, share_read, share_delete, open_existing = 0x80000000, 0x1, 0x4, 3
    handle = kernel32.CreateFileW(str(path), generic_read, share_read | share_delete,
                                  None, open_existing, 0, None)
    if handle == wintypes.HANDLE(-1).value:
        error = ctypes.get_last_error()
        if error == 32:  # ERROR_SHARING_VIOLATION
            raise FileBusyError(error, "Datei gerade in Benutzung", str(path))
        raise OSError(error, ctypes.FormatError(error), str(path))
    return handle


def _win_close(handle: int) -> None:
    """Schließt ein Windows-Handle."""
    import ctypes

    ctypes.WinDLL("kernel32").CloseHandle(handle)
