"""Selbsttest der Install-Primitive je Vault (PLAN.md, „Plattform-Tabelle“).

Beim Öffnen eines Vaults wird geprüft, welche Variante „ohne Überschreiben
installieren“ (Invariante I) dort **tatsächlich** funktioniert. Geprüft wird
über ``FsOps(mode).rename_no_replace``, also genau den Codepfad, den das
Schreiben später nimmt. Reihenfolge (stärkste zuerst):

1. ``atomic``: Windows ``os.rename`` bzw. POSIX ``os.link`` + ``unlink``.
2. ``noreplace``: ``renameat2(RENAME_NOREPLACE)`` (Android-Shared-Storage
   verbietet Hardlinks, erlaubt aber diesen Syscall; Befund S1 vom 2026-10-21).
3. ``excl``: ``O_EXCL``-Fallback, nur **eingeschränkt** (GRENZE A1–A3).

Eine Variante gilt nur, wenn sie (a) auf ein freies Ziel umbenennt und (b) bei
belegtem Ziel ``FileExistsError`` wirft, ohne Quelle oder Ziel zu verändern.

Die Probedateien heißen ``.mw-probe-<zufall>.mw-<x>``: Punkt-Dateien ignoriert
der Scan, und die empfohlene ``.stignore``-Zeile ``.*.mw-*`` hält sie aus
Syncthing heraus. Sie werden in jedem Fall wieder entfernt.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from .fsops import FsOps

#: Anzeigetext der Schreibgarantie je Variante (Einstellungen, Startbanner).
GUARANTEE = {
    "atomic": "voll",
    "noreplace": "voll",
    "excl": "eingeschränkt (A1–A3)",
}


class VaultNotWritableError(OSError):
    """Im Vault funktioniert nicht einmal exklusives Anlegen."""


def probe_install_mode(folder: Path) -> str:
    """Ermittelt die stärkste funktionierende Install-Variante für ``folder``.

    Args:
        folder: Vault-Ordner (die Probe läuft auf demselben Dateisystem).

    Returns:
        ``"atomic"``, ``"noreplace"`` oder ``"excl"``.

    Raises:
        VaultNotWritableError: Weder eine atomare Variante noch ``O_EXCL``
            funktioniert (z. B. Ordner schreibgeschützt).
    """
    stem = f".mw-probe-{secrets.token_hex(4)}"
    paths = {key: folder / f"{stem}.mw-{key}" for key in ("a", "b", "c")}
    try:
        if not _excl_works(paths["a"]):
            raise VaultNotWritableError(f"In {folder} lässt sich nicht exklusiv anlegen.")
        for mode in ("atomic", "noreplace"):
            if _no_overwrite_works(FsOps(mode), paths):
                return mode
        return "excl"
    finally:
        for path in paths.values():
            _discard(path)


def _excl_works(path: Path) -> bool:
    """Prüft ``O_EXCL``: freier Pfad wird angelegt, belegter wirft ``FileExistsError``.

    Args:
        path: Probedatei (danach wieder entfernt).

    Returns:
        ``True``, wenn beides zutrifft.
    """
    fs = FsOps("excl")
    try:
        fs.create_exclusive(path, b"a")
    except OSError:
        return False
    try:
        fs.create_exclusive(path, b"x")
    except FileExistsError:
        return path.read_bytes() == b"a"
    except OSError:
        return False
    finally:
        _discard(path)
    return False


def _no_overwrite_works(fs: FsOps, paths: dict[str, Path]) -> bool:
    """Prüft ``fs.rename_no_replace`` auf freiem und auf belegtem Ziel.

    Args:
        fs: Kandidat mit fester Install-Variante.
        paths: Probedateien ``a``, ``b``, ``c`` (vorher frei, danach entfernt).

    Returns:
        ``True``, wenn das freie Ziel atomar entsteht und das belegte Ziel
        ``FileExistsError`` auslöst, ohne Quelle oder Ziel zu verändern.
    """
    a, b, c = paths["a"], paths["b"], paths["c"]
    try:
        fs.create_exclusive(a, b"a")
        fs.create_exclusive(b, b"b")
        fs.rename_no_replace(a, c)
        if os.path.lexists(a) or c.read_bytes() != b"a":
            return False
        try:
            fs.rename_no_replace(b, c)
        except FileExistsError:
            return b.read_bytes() == b"b" and c.read_bytes() == b"a"
        return False
    except OSError:
        return False
    finally:
        for path in paths.values():
            _discard(path)


def _discard(path: Path) -> None:
    """Entfernt eine eigene Probedatei, falls vorhanden (Fehler werden ignoriert).

    Args:
        path: Probedatei (nur ``.mw-probe-…``, nie Nutzerdaten).
    """
    try:
        os.unlink(path)
    except OSError:
        pass
