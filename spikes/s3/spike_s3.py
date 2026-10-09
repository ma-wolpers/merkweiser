"""Spike S3: bw-gui Treeview mit Checkbox-Spalte und Rohtext-Roundtrip.

Wegwerfcode. Läuft mit zurückgezogenem Root-Fenster (nichts wird angezeigt).
Prüft:
1. Tcl/Tk-Version (Nicht-BMP-Zeichen wie Emoji).
2. ``WrappedTextField.get()`` gegen ``.text.get("1.0", "end-1c")`` bei
   führenden/abschließenden Leerzeichen, Tabs, Leerzeilen, Emoji, ``\\r``.
3. Themed ttk-Treeview mit Text-Checkbox-Spalte (☐/☑) und Hierarchie.
4. Die Guards ``checkbutton_guard``/``tk_state_guard`` auf diesem Spike-Code.
"""

from __future__ import annotations

import sys
from pathlib import Path

# bw-gui als Geschwister-Repo: <Code>/merkweiser/spikes/s3/spike_s3.py → <Code>/bw-gui/src
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bw-gui" / "src"))

from bw_gui.runtime import ui, widgets  # noqa: E402
from bw_gui.testing import checkbutton_guard, tk_state_guard  # noqa: E402
from bw_gui.theming import configure_ttk_theme  # noqa: E402
from bw_gui.widgets import WrappedTextField  # noqa: E402

SAMPLE = "  eingerückt\n\tTab-Zeile\n- [ ] Todo 😀 mit Emoji\n\nletzte Zeile mit Leerzeichen   \n\n"


def main() -> None:
    """Führt alle S3-Prüfungen aus und gibt einen Bericht aus."""
    root = ui.Tk()
    root.withdraw()
    print("tcl/tk:", root.tk.call("info", "patchlevel"), "| python", sys.version.split()[0])
    configure_ttk_theme(root)

    field = WrappedTextField(root, initial="")
    field.text.insert("1.0", SAMPLE)
    raw = field.text.get("1.0", "end-1c")
    print("get() == SAMPLE        :", field.get() == SAMPLE, "| get() strippt:", repr(field.get()[:12]))
    print(".text end-1c == SAMPLE :", raw == SAMPLE)
    if raw != SAMPLE:
        print("  diff raw   :", repr(raw))
        print("  diff sample:", repr(SAMPLE))
    field.text.delete("1.0", "end")
    field.text.insert("1.0", "a\r\nb")
    print("\\r\\n bleibt erhalten  :", field.text.get("1.0", "end-1c") == "a\r\nb")

    tree = widgets.Treeview(root, columns=("done", "text", "tags"), show="tree headings")
    tree.heading("done", text="✓")
    tree.heading("text", text="Todo")
    note = tree.insert("", "end", text="Thema #uni", values=("", "", "#uni"))
    tree.insert(note, "end", text="", values=("☐", "Aufgabe A", "#uni"))
    tree.insert(note, "end", text="", values=("☑", "==dringend==", "#uni #projekt/x"))
    root.update_idletasks()
    print("treeview rows          :", len(tree.get_children(note)), "| style bg:",
          widgets.Style().lookup("Treeview", "background"))

    here = Path(__file__).parent
    print("checkbutton_guard      :", checkbutton_guard.find_offenders(here))
    print("tk_state_guard         :", tk_state_guard.find_offenders(here))
    root.destroy()


if __name__ == "__main__":
    main()
