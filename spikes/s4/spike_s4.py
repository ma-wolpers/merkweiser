"""Spike S4: Tausch-Protokoll unter Windows gegen ein laufendes Obsidian.

Wegwerfcode, interaktiv. Arbeitet AUSSCHLIESSLICH in einem eigenen Test-Vault
mit synthetischen Notizen (Standard: Ordner ``MerkweiserS4-Testvault`` neben
diesem Skript). Den Ordner in Obsidian als *neuen* Vault öffnen.

Aufruf:  python spike_s4.py [Test-Vault-Ordner]

Teil A  – Handle-Lebensdauer: Hält Obsidian eine Notiz zum Schreiben offen?
          (Prüfung per CreateFileW mit verweigerter Schreib-Freigabe, 30 s lang,
          während du tippst.)
Teil B  – Schreibsperre: Sperre 15 s halten, während du in Obsidian tippst.
          Wie reagiert Obsidian (Fehler, später speichern, Inhalt weg)?
Teil C  – Tausch-Protokoll mit Haltepunkten (a)–(e): An jedem Haltepunkt
          speicherst du eine Änderung in Obsidian; das Skript protokolliert,
          wo sie landet (P, D, Konfliktdatei, verloren).
Teil D  – Datei 60 s „weg“ (simulierter Absturz zwischen Wegbenennen und
          Installieren, Grenze W4): Reaktion von Obsidian/Syncthing.

Ergebnis: ``s4-bericht-<zeit>.txt`` im Test-Vault. Bitte die Beobachtungen in
Obsidian (Fehlermeldungen, geschlossene Tabs, verlorener Text) jeweils bei
der Rückfrage eintippen – sie landen mit im Bericht.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

GENERIC_READ = 0x80000000
DELETE = 0x00010000
FILE_SHARE_READ = 0x1
FILE_SHARE_DELETE = 0x4
OPEN_EXISTING = 3
INVALID_HANDLE = wintypes.HANDLE(-1).value
ERROR_SHARING_VIOLATION = 32

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

REPORT: list[str] = []


def log(msg: str) -> None:
    """Gibt eine Zeile aus und merkt sie für den Bericht vor.

    Args:
        msg: Zu protokollierende Zeile.
    """
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    REPORT.append(line)


def ask(prompt: str) -> str:
    """Fragt eine Beobachtung ab und protokolliert sie.

    Args:
        prompt: Frage an die Person am Rechner.

    Returns:
        Die eingetippte Antwort.
    """
    answer = input(f"\n>>> {prompt}\n    Antwort (Enter = nichts Auffälliges): ")
    REPORT.append(f"    BEOBACHTUNG: {prompt} -> {answer or '(nichts Auffälliges)'}")
    return answer


def open_deny_write(path: Path) -> int | None:
    """Öffnet ``path`` mit Freigabe nur für Lesen und Löschen (Schreiben verweigert).

    Args:
        path: Zu öffnende Datei.

    Returns:
        Handle oder ``None`` bei Sharing-Violation (jemand hält Schreibzugriff).

    Raises:
        OSError: bei anderen Fehlern.
    """
    h = _k32.CreateFileW(str(path), GENERIC_READ | DELETE, FILE_SHARE_READ | FILE_SHARE_DELETE,
                         None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE:
        err = ctypes.get_last_error()
        if err == ERROR_SHARING_VIOLATION:
            return None
        raise OSError(err, ctypes.FormatError(err))
    return h


def snapshot(vault: Path) -> dict[str, bytes]:
    """Liest alle Dateien des Test-Vaults (ohne ``.obsidian``) ein.

    Args:
        vault: Test-Vault-Ordner.

    Returns:
        Abbildung Dateiname → Inhalt.
    """
    return {p.name: p.read_bytes() for p in vault.iterdir() if p.is_file() and not p.name.startswith("s4-bericht")}


def where_is(vault: Path, marker: bytes) -> str:
    """Sucht, in welchen Dateien ein Änderungsmarker steht.

    Args:
        vault: Test-Vault-Ordner.
        marker: Bytefolge, die die Person in Obsidian getippt hat.

    Returns:
        Lesbare Fundstellen oder ``NICHT GEFUNDEN``.
    """
    hits = [n for n, b in snapshot(vault).items() if marker in b]
    return ", ".join(hits) if hits else "NICHT GEFUNDEN (verloren oder nur in offenem Handle)"


def part_a(note: Path) -> None:
    """Teil A: misst 30 s lang, ob Obsidian die Notiz zum Schreiben offen hält."""
    log("TEIL A: Öffne die Notiz in Obsidian und tippe 30 s lang immer wieder etwas.")
    input("    Enter drücken, sobald du anfängst zu tippen …")
    ok = viol = 0
    end = time.monotonic() + 30
    while time.monotonic() < end:
        h = open_deny_write(note)
        if h is None:
            viol += 1
        else:
            ok += 1
            _k32.CloseHandle(h)
        time.sleep(0.05)
    log(f"TEIL A: Sperre möglich={ok}, Sharing-Violation (Obsidian hält Schreib-Handle)={viol}")


def part_b(note: Path) -> None:
    """Teil B: hält 15 s eine Schreibsperre, während in Obsidian getippt wird."""
    log("TEIL B: Gleich halte ich 15 s eine Schreibsperre. Tippe währenddessen in Obsidian 'SPERRE-B'.")
    input("    Enter zum Start …")
    h = open_deny_write(note)
    if h is None:
        log("TEIL B: Sperre nicht möglich (Obsidian hält gerade Schreib-Handle) – bitte wiederholen.")
        return
    time.sleep(15)
    _k32.CloseHandle(h)
    log("TEIL B: Sperre freigegeben. Warte 5 s auf Obsidians Speichern …")
    time.sleep(5)
    log(f"TEIL B: 'SPERRE-B' gefunden in: {where_is(note.parent, b'SPERRE-B')}")
    ask("Hat Obsidian während der Sperre einen Fehler gezeigt? Ist Text verloren?")


def swap_with_breakpoints(note: Path) -> None:
    """Teil C: Tausch-Protokoll mit Haltepunkten (a)–(e)."""
    vault = note.parent
    for label, tag in [("a vor dem Wegbenennen", b"HP-A"), ("b zwischen Wegbenennen und Installieren", b"HP-B"),
                       ("c nach Installieren, vor Kopie von D", b"HP-C"), ("d während der Quarantäne", b"HP-D"),
                       ("e nach der Quarantäne", b"HP-E")]:
        log(f"TEIL C ({label}): Tausch beginnt.")
        expected = note.read_bytes()
        new = expected + f"\n- [ ] Merkweiser-Version {tag.decode()}\n".encode()
        tmp, old = vault / f".{note.name}.mw-s4.tmp", vault / f".{note.name}.mw-s4.old"
        tmp.write_bytes(new)
        if tag == b"HP-A":
            input(f"    HALT (a): Tippe jetzt '{tag.decode()}' in Obsidian, warte bis gespeichert, dann Enter …")
        h = open_deny_write(note)
        if h is None:
            log("    Sperre nicht möglich (Schreib-Handle offen) → Protokoll würde hier abbrechen.")
            tmp.unlink()
            continue
        _k32.CloseHandle(h)  # Spike: Rename per Pfad direkt nach Prüfung
        os.rename(note, old)
        if tag == b"HP-B":
            input(f"    HALT (b): Notiz ist JETZT weg. Tippe '{tag.decode()}' in Obsidian, dann Enter …")
        try:
            os.rename(tmp, note)  # Windows: schlägt fehl, wenn note existiert
            log("    installiert.")
        except FileExistsError:
            log("    P war belegt → eigene Version würde Konfliktdatei.")
            tmp.unlink()
        if tag == b"HP-C":
            input(f"    HALT (c): Tippe '{tag.decode()}' in Obsidian, dann Enter …")
        d_bytes = old.read_bytes()
        log(f"    D == erwartet: {d_bytes == expected}")
        if tag == b"HP-D":
            input(f"    HALT (d, Quarantäne): Tippe '{tag.decode()}' in Obsidian, dann Enter …")
        d_again = old.read_bytes()
        log(f"    D nach Quarantäne unverändert: {d_again == d_bytes}; P == N: {note.read_bytes() == new}")
        old.unlink()
        if tag == b"HP-E":
            input(f"    HALT (e): Tippe '{tag.decode()}' in Obsidian, dann Enter …")
        time.sleep(3)
        log(f"    '{tag.decode()}' gefunden in: {where_is(vault, tag)}")
        ask(f"Haltepunkt ({label}): Hat Obsidian etwas gemeldet, den Tab geschlossen oder Text verworfen?")


def part_d(note: Path) -> None:
    """Teil D: Datei 60 s verschwunden (simulierter Absturz, Grenze W4)."""
    old = note.parent / f".{note.name}.mw-s4.old"
    log("TEIL D: Notiz wird für 60 s weggenommen (simulierter Absturz). Beobachte Obsidian und Syncthing.")
    input("    Enter zum Start …")
    os.rename(note, old)
    time.sleep(60)
    try:
        os.rename(old, note)
        log("TEIL D: Notiz wiederhergestellt.")
    except FileExistsError:
        log("TEIL D: Pfad inzwischen neu belegt (z. B. Obsidian/Syncthing) – .old bleibt liegen!")
    ask("Was haben Obsidian (Tab? Datei neu angelegt?) und Syncthing (Löschung verteilt?) gemacht?")


def main() -> None:
    """Richtet den Test-Vault ein und führt die Teile A–D nacheinander aus."""
    vault = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("MerkweiserS4-Testvault")
    vault.mkdir(parents=True, exist_ok=True)
    note = vault / "2026-01-01.md"
    if not note.exists():
        note.write_text("Synthetisches Testthema #test\n\n- [ ] Testaufgabe\n", encoding="utf-8")
    log(f"Test-Vault: {vault}  Notiz: {note.name}")
    print("Öffne diesen Ordner in Obsidian als NEUEN Vault und die Notiz im Editor.\n"
          "Optional: Ordner zusätzlich in Syncthing als Testordner freigeben.")
    input("Enter, wenn bereit …")
    for part in (part_a, part_b, swap_with_breakpoints, part_d):
        try:
            part(note)
        except Exception as exc:  # Spike: Fehler sind Befunde
            log(f"FEHLER in {part.__name__}: {type(exc).__name__}: {exc}")
    report = vault / f"s4-bericht-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    report.write_text("\n".join(REPORT) + "\n", encoding="utf-8")
    print(f"\nBericht: {report}")


if __name__ == "__main__":
    main()
