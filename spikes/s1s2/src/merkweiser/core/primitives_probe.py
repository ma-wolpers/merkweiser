"""Spike S1/S2: Selbsttest der Dateisystem-Primitive des Tausch-Protokolls.

Wegwerfcode (Spike, nicht Teil des Produkts). Prüft in einem Testordner,
welche Primitive das Dateisystem tatsächlich atomar bzw. korrekt ausführt:
Lesen/Schreiben, atomarer Rename, Rename auf existierendes Ziel,
``os.link`` (No-Overwrite-Install auf POSIX), ``renameat2(RENAME_NOREPLACE)``
per Syscall, ``O_EXCL``-Anlegen, ``fsync`` auf Datei und Verzeichnis,
Stabilität von ``st_ino`` über Rename sowie ``fcntl.flock``.

Bewusst nur Standardbibliothek + ``ctypes``: genau dieselbe Prüfung soll
später als Start-Selbsttest im Core laufen können (Plan: Plattform-Tabelle).
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys
import time
from pathlib import Path

# Syscall-Nummern für renameat2 (nur Linux/Android relevant).
_SYS_RENAMEAT2 = {"aarch64": 276, "x86_64": 316, "armv7l": 382, "armv8l": 382}
_RENAME_NOREPLACE = 1
_AT_FDCWD = -100


def _try(report: list[str], name: str, func) -> object:
    """Führt einen Einzeltest aus und protokolliert Ergebnis oder Ausnahme.

    Args:
        report: Zeilenliste, an die das Ergebnis angehängt wird.
        name: Kurzname des Tests (erscheint im Bericht).
        func: Parameterlose Funktion; ihr Rückgabewert wird protokolliert.

    Returns:
        Den Rückgabewert von ``func`` oder ``None`` bei Ausnahme.
    """
    try:
        result = func()
        report.append(f"OK    {name}: {result!r}")
        return result
    except Exception as exc:  # Spike: jede Ausnahme ist ein Befund
        report.append(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        return None


def _renameat2_noreplace(src: Path, dst: Path) -> str:
    """Ruft ``renameat2(..., RENAME_NOREPLACE)`` per Syscall auf.

    Args:
        src: Quellpfad.
        dst: Zielpfad (darf nicht existieren, sonst EEXIST erwartet).

    Returns:
        ``"ok"`` bei Erfolg.

    Raises:
        OSError: mit errno des Syscalls (z. B. EEXIST, EINVAL, ENOSYS).
    """
    nr = _SYS_RENAMEAT2.get(platform.machine())
    if nr is None:
        raise OSError(0, f"keine renameat2-Nummer für {platform.machine()}")
    libc = ctypes.CDLL(None, use_errno=True)
    res = libc.syscall(nr, _AT_FDCWD, os.fsencode(src), _AT_FDCWD, os.fsencode(dst), _RENAME_NOREPLACE)
    if res != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return "ok"


def run_probe(test_dir: Path, app_data_dir: Path | None) -> list[str]:
    """Führt alle Primitive-Tests im Testordner aus.

    Legt ausschließlich Dateien mit Präfix ``mw-spike-`` an (synthetische
    Testdaten) und räumt sie am Ende wieder auf.

    Args:
        test_dir: Ordner im synchronisierten Speicher (z. B. Syncthing-Testordner).
        app_data_dir: App-privates Verzeichnis für den Lock-Test oder ``None``.

    Returns:
        Bericht als Zeilenliste.
    """
    r: list[str] = [
        f"Merkweiser Spike S1/S2 – {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"python={sys.version.split()[0]} platform={sys.platform} machine={platform.machine()}",
        f"test_dir={test_dir} app_data_dir={app_data_dir}",
    ]
    a, b, c = test_dir / "mw-spike-a.md", test_dir / "mw-spike-b.md", test_dir / "mw-spike-c.md"
    _try(r, "listdir", lambda: len(os.listdir(test_dir)))
    _try(r, "write_a", lambda: a.write_bytes(b"A\n"))
    _try(r, "read_a", lambda: a.read_bytes())
    _try(r, "write_b", lambda: b.write_bytes(b"B\n"))
    ino_before = _try(r, "ino_a", lambda: os.stat(a).st_ino)
    _try(r, "rename_a_to_c", lambda: os.rename(a, c))
    _try(r, "ino_c_equals_ino_a", lambda: os.stat(c).st_ino == ino_before)
    _try(r, "rename_c_onto_existing_b (POSIX: overwrite erwartet)", lambda: (os.rename(c, b), b.read_bytes())[1])
    _try(r, "os_replace_tmp_onto_b", lambda: (a.write_bytes(b"N\n"), os.replace(a, b), b.read_bytes())[2])
    _try(r, "link_b_to_a (No-Overwrite-Install)", lambda: (os.link(b, a), a.read_bytes())[1])
    _try(r, "link_onto_existing (EEXIST erwartet)", lambda: os.link(b, a))
    _try(r, "unlink_a", lambda: a.unlink())
    _try(r, "renameat2_noreplace_free", lambda: _renameat2_noreplace(b, a))
    _try(r, "write_b_again", lambda: b.write_bytes(b"B2\n"))
    _try(r, "renameat2_noreplace_occupied (EEXIST erwartet)", lambda: _renameat2_noreplace(b, a))

    def excl() -> str:
        fd = os.open(c, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, b"EXCL\n")
            os.fsync(fd)
            return f"ino={os.fstat(fd).st_ino}"
        finally:
            os.close(fd)

    # Testisolation: Unter Windows lässt der Rename-auf-existierend-Test ``c``
    # stehen; für den O_EXCL-Test muss der Pfad frei sein.
    c.unlink(missing_ok=True)
    _try(r, "o_excl_create_free", excl)
    _try(r, "o_excl_create_occupied (FileExistsError erwartet)", excl)
    _try(r, "ino_stable_after_reopen", lambda: os.stat(c).st_ino)

    def dir_fsync() -> str:
        fd = os.open(test_dir, os.O_RDONLY)
        try:
            os.fsync(fd)
            return "ok"
        finally:
            os.close(fd)

    _try(r, "dir_fsync", dir_fsync)
    if app_data_dir is not None:
        def flock() -> str:
            import fcntl
            lock = Path(app_data_dir) / "mw-spike.lock"
            with open(lock, "a+b") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
            return "ok"
        _try(r, "flock_app_data", flock)
    for p in (a, b, c):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    r.append("Ende.")
    return r
