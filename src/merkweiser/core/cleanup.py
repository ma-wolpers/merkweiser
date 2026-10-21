"""Aufräumen beim Start: leere Tagesdateien finden (Nutzerwunsch vom 2026-10-21).

Eine Tagesdatei gilt als **leer**, wenn ihr Inhalt als UTF-8 (ohne BOM) nur aus
Leerraum (Leerzeichen, Tabs, Zeilenumbrüche) und Trennzeilen ``---`` besteht,
also z. B. aus Resten gelöschter Notizen des alten Formats. Alles andere bleibt
stehen, insbesondere:

* Dateien mit BOM oder in anderem Encoding (vorsichtshalber),
* Dateien mit Frontmatter (``tags: …`` ist Inhalt),
* Dateien mit offenem Konflikt (sonst entstünde „Hauptdatei fehlt“),
* Dateien, die eine andere Merkweiser-Instanz gerade bearbeitet.

Dieses Modul **entscheidet nur**; gelöscht wird über ``Writer.remove``
(Tausch-Protokoll mit Backup und erneuter Inhaltsprüfung unmittelbar davor).
"""

from __future__ import annotations

from pathlib import Path

from .vault import VaultIndex


def is_empty_day_text(raw: bytes) -> bool:
    """``True``, wenn Bytes nur Leerraum und ``---``-Zeilen enthalten (UTF-8 ohne BOM).

    Args:
        raw: Dateiinhalt.

    Returns:
        Ob die Datei als leer gilt.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return all(line.strip() in ("", "---") for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))


def empty_day_files(root: Path, index: VaultIndex, busy: set[str]) -> list[tuple[str, bytes]]:
    """Leere Tagesdateien, die gefahrlos entfernt werden dürfen.

    Args:
        root: Vault-Ordner.
        index: Aktueller Scan.
        busy: Pfade, die eine andere Instanz gerade bearbeitet.

    Returns:
        ``(Pfad relativ zum Vault, gelesener Inhalt)`` für ``Writer.remove``.
    """
    with_conflict = {c.main_relpath for c in index.conflicts}
    found = []
    for paths in index.day_files.values():
        for relpath in paths:
            if relpath in with_conflict or relpath in busy:
                continue
            try:
                raw = (root / relpath).read_bytes()
            except OSError:
                continue
            if is_empty_day_text(raw):
                found.append((relpath, raw))
    return found
