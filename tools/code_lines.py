"""Zählt ausführbare Code-Zeilen pro Datei (Richtwert: ~300, siehe AGENTS.md).

Gezählt werden Zeilen, die Python-Tokens außer Kommentaren und Zeilenumbrüchen
enthalten, **ohne** Docstrings und ohne ``import``-Zeilen. ``wc -l`` ist
ausdrücklich nicht das Maß.

Aufruf::

    python tools/code_lines.py [Pfade …]   # Standard: src/
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path

LIMIT = 300


def _excluded_lines(tree: ast.AST) -> set[int]:
    """Sammelt Zeilen von Docstrings und Import-Anweisungen.

    Args:
        tree: Geparster Modul-AST.

    Returns:
        Menge der 1-basierten Zeilennummern, die nicht zählen.
    """
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            excluded.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
                    and isinstance(first.value.value, str):
                excluded.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return excluded


def count_code_lines(path: Path) -> int:
    """Zählt die ausführbaren Code-Zeilen einer Python-Datei.

    Args:
        path: Pfad zur ``.py``-Datei.

    Returns:
        Anzahl der Zeilen mit Code (ohne Kommentare, Leerzeilen, Docstrings, Imports).
    """
    source = path.read_text(encoding="utf-8")
    excluded = _excluded_lines(ast.parse(source))
    skip = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
            tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}
    lines: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in skip:
            continue
        for line in range(tok.start[0], tok.end[0] + 1):
            if line not in excluded:
                lines.add(line)
    return len(lines)


def main(argv: list[str]) -> int:
    """Gibt die Zählung aller Dateien aus und meldet Überschreitungen.

    Args:
        argv: Pfade (Dateien oder Ordner); Standard ``src``.

    Returns:
        ``1``, wenn eine Datei über dem Richtwert liegt und nicht mit
        ``GRENZE(dateigroesse)`` markiert ist, sonst ``0``.
    """
    paths = [Path(p) for p in argv] or [Path("src")]
    files = sorted(f for p in paths for f in ([p] if p.is_file() else p.rglob("*.py")))
    status = 0
    for file in files:
        count = count_code_lines(file)
        marked = "GRENZE(dateigroesse)" in file.read_text(encoding="utf-8")
        flag = " <-- über Richtwert" if count > LIMIT and not marked else ""
        status |= bool(flag)
        print(f"{count:5d}  {file}{flag}")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
