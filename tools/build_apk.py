"""Baut die Android-App signiert mit dem gemeinsamen Merkweiser-Keystore und legt sie nach ``SyncSpike/``.

Ohne eigene Signatur signiert ``flet build apk`` mit dem Debug-Schlüssel des
jeweiligen Rechners; Android lehnt dann ein Update von einem anderen Rechner ab
(„package conflicts with an existing package“). Deshalb signieren alle Rechner
mit demselben Keystore aus einem per Syncthing geteilten Ordner.

Signing-Ordner (``merkweiser.jks``, ``passwort.txt``): Umgebungsvariable
``MERKWEISER_SIGNING_DIR`` oder ``../../7thCloud/tools/merkweiser-signing``
relativ zum Repo. Pfad und Passwort gehen nur über die Umgebung an flet-cli
(``FLET_ANDROID_SIGNING_KEY_STORE``/``…_PASSWORD``, geprüft gegen flet-cli
0.86.5), nie in die Kommandozeile oder ins Repo.

Aufruf (aus der Umgebung, in der ``flet-cli 0.86.5`` installiert ist)::

    python tools/build_apk.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SIGNING = REPO / ".." / ".." / "7thCloud" / "tools" / "merkweiser-signing"
KEY_ALIAS = "merkweiser"


def signing_dir() -> Path:
    """Ort des gemeinsamen Keystores.

    Returns:
        ``MERKWEISER_SIGNING_DIR`` oder der Standardort relativ zum Repo.
    """
    return Path(os.environ.get("MERKWEISER_SIGNING_DIR") or DEFAULT_SIGNING).resolve()


def flet_command() -> list[str]:
    """Findet ``flet`` neben dem laufenden Python bzw. im ``PATH``.

    Returns:
        Der Befehl als Liste.

    Raises:
        SystemExit: flet-cli ist nicht installiert.
    """
    beside = Path(sys.executable).parent / ("flet.exe" if os.name == "nt" else "flet")
    found = str(beside) if beside.exists() else shutil.which("flet")
    if not found:
        raise SystemExit("flet-cli fehlt (pip install -e \".[build]\").")
    return [found]


def main() -> int:
    """Baut die APK signiert und kopiert sie nach ``SyncSpike/``.

    Returns:
        Exit-Code von ``flet build`` (0 bei Erfolg).

    Raises:
        SystemExit: Keystore oder Passwortdatei fehlen.
    """
    folder = signing_dir()
    keystore, password_file = folder / "merkweiser.jks", folder / "passwort.txt"
    if not (keystore.is_file() and password_file.is_file()):
        raise SystemExit(f"Keystore oder Passwort fehlt in {folder} (MERKWEISER_SIGNING_DIR setzen?).")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", FLET_ANDROID_SIGNING_KEY_STORE=str(keystore),
               FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD=password_file.read_text(encoding="utf-8").strip(),
               FLET_ANDROID_SIGNING_KEY_ALIAS=KEY_ALIAS)
    code = subprocess.call([*flet_command(), "build", "apk", "--no-rich-output"], cwd=REPO, env=env)
    apk = REPO / "build" / "apk" / "merkweiser.apk"
    if code == 0 and apk.is_file():
        (REPO / "SyncSpike").mkdir(exist_ok=True)
        shutil.copy2(apk, REPO / "SyncSpike" / apk.name)
        print(f"APK signiert und nach SyncSpike/{apk.name} kopiert.")
    return code


if __name__ == "__main__":
    sys.exit(main())
