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

Nach dem Build wird der Fingerabdruck der APK per ``apksigner`` (Android-SDK)
geprüft, mit Java aus ``JAVA_HOME`` bzw. dem JDK, das ``flet build`` unter
``~/java`` installiert; fehlt ``apksigner``, wird das nur gemeldet.

Aufruf (aus der Umgebung, in der ``flet-cli 0.86.5`` installiert ist)::

    python tools/build_apk.py                     # die App
    python tools/build_apk.py --project spikes/s5 # ein Spike (eigene App-ID)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SIGNING = REPO / ".." / ".." / "7thCloud" / "tools" / "merkweiser-signing"
KEY_ALIAS = "merkweiser"
EXPECTED_SHA256_PREFIX = "06e0555bc0c9b23f"  # öffentlicher Fingerabdruck (README im Signing-Ordner), apksigner-Schreibweise


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


def java_bin() -> Path | None:
    """``bin`` eines JDK: ``JAVA_HOME`` oder das von ``flet build`` unter ``~/java`` installierte."""
    if os.environ.get("JAVA_HOME"):
        return Path(os.environ["JAVA_HOME"]) / "bin"
    found = sorted((Path.home() / "java").glob("*/bin"), reverse=True)
    return found[0] if found else None


def find_apksigner() -> Path | None:
    """``apksigner`` aus den neuesten Build-Tools des Android-SDK (``ANDROID_HOME``/``ANDROID_SDK_ROOT``)."""
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not sdk:
        return None
    name = "apksigner.bat" if os.name == "nt" else "apksigner"
    tools = sorted(Path(sdk).glob(f"build-tools/*/{name}"), reverse=True)
    return tools[0] if tools else None


def check_signature(apk: Path) -> str:
    """Prüft per ``apksigner``, ob die APK mit dem Merkweiser-Schlüssel signiert ist.

    ``keytool -printcert -jarfile`` reicht nicht: Es liest nur v1-Signaturen, die
    APK von ``flet build`` ist nur v2/v3-signiert („Not a signed jar file“).

    Returns:
        Meldung für die Ausgabe.

    Raises:
        SystemExit: falscher Schlüssel.
    """
    apksigner = find_apksigner()
    if apksigner is None:
        return "Signatur nicht geprüft (apksigner nicht gefunden)."
    env = dict(os.environ)
    jbin = java_bin()
    if jbin is not None:
        env["JAVA_HOME"] = str(jbin.parent)
        env["PATH"] = str(jbin) + os.pathsep + env.get("PATH", "")
    output = subprocess.run([str(apksigner), "verify", "--print-certs", str(apk)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env).stdout
    if EXPECTED_SHA256_PREFIX not in output:
        raise SystemExit(f"FEHLER: {apk.name} ist nicht mit dem Merkweiser-Schlüssel signiert.")
    return f"Signatur geprüft (SHA-256 {EXPECTED_SHA256_PREFIX}…)."


def main(argv: list[str] | None = None) -> int:
    """Baut die APK signiert, prüft die Signatur und kopiert sie nach ``SyncSpike/``.

    Returns:
        Exit-Code von ``flet build`` (0 bei Erfolg).

    Raises:
        SystemExit: Keystore oder Passwortdatei fehlen, oder die Signatur stimmt nicht.
    """
    parser = argparse.ArgumentParser(description="Signierte Merkweiser-APK bauen")
    parser.add_argument("--project", default=".", help="Projektordner relativ zum Repo (Standard: die App)")
    args = parser.parse_args(argv)
    project = (REPO / args.project).resolve()
    folder = signing_dir()
    keystore, password_file = folder / "merkweiser.jks", folder / "passwort.txt"
    if not (keystore.is_file() and password_file.is_file()):
        raise SystemExit(f"Keystore oder Passwort fehlt in {folder} (MERKWEISER_SIGNING_DIR setzen?).")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", FLET_ANDROID_SIGNING_KEY_STORE=str(keystore),
               FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD=password_file.read_text(encoding="utf-8").strip(),
               FLET_ANDROID_SIGNING_KEY_ALIAS=KEY_ALIAS)
    code = subprocess.call([*flet_command(), "build", "apk", "--no-rich-output"], cwd=project, env=env)
    apks = sorted((project / "build" / "apk").glob("*.apk"))
    if code == 0 and apks:
        print(check_signature(apks[0]))
        (REPO / "SyncSpike").mkdir(exist_ok=True)
        shutil.copy2(apks[0], REPO / "SyncSpike" / apks[0].name)
        print(f"APK signiert und nach SyncSpike/{apks[0].name} kopiert.")
    return code


if __name__ == "__main__":
    sys.exit(main())
