# Plan: Merkweiser – Notizverwaltung (Markdown-Notizen + Todos, Desktop + Android)

> **Status:** Freigegebener Umsetzungsplan (Stand 2026-10-09, nach vier
> Audit-Runden), hier eingefroren. Er beschreibt das Ziel; den jeweils
> umgesetzten Ist-Zustand beschreibt [ARCHITEKTUR.md](ARCHITEKTUR.md),
> den Verlauf [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md).

## Context

Konzept: `plan Notizverwaltung.md` im Geschwister-Repo `../tools4school`. Die Datei ist beschädigt, weil die neue Fassung mitten in die alte eingefügt wurde (ab „Ein bestimmtes Format, dem alle Notize# …“). Maßgeblich ist die neue Fassung. **Die Originaldatei wird nicht verändert.**

**Ziel:** ein neues, eigenständiges Programm (kein Ableger), das den Überblick über alle Tagesnotizen behält, sie sortiert und filtert und vor allem keine Todos verlieren lässt.

**Name:** **Merkweiser** (Paket und Repo `merkweiser`), am 2026-10-08 festgelegt. Er ist doppeldeutig: Wie ein Wegweiser zeigt er, was ich mir merken muss, und mit ihm merke ich mir Dinge weiser.

Stand: Diese Fassung enthält vier externe Audits (2026-10-08/09). Alle früheren Entscheidungen sind erhalten. Präzisiert wurden sie nur dort, wo ein Audit eine Bruchstelle gezeigt hat.

### Garantien (Abnahmekriterien, so formuliert, dass sie gleichzeitig wahr sind)

1. **Kein unerlaubter Datenverlust.** Inhalt verschwindet aus dem Vault nur
   - (a) durch eine explizite Nutzeraktion (Löschen, Konfliktentscheidung, Verschieben, Rohtext-Bearbeitung) oder
   - (b) durch die benannte Merge-Regel **„erledigt gewinnt“** (R1/R2, siehe Merge).

   In beiden Fällen liegt der vorige Stand im Backup. Jeder andere Verlust ist ein Fehler, und `verify.py` stuft ihn zum Konflikt herab.
2. **Externe Änderungen werden nie auf Basis eines veralteten Stands überschrieben oder gelöscht.** Sie bleiben die Hauptdatei oder werden als Konfliktdatei im Vault sichtbar.
   - **Geltungsbereich** (Nutzerentscheidung vom 2026-10-09): Schreiber, die pro Speichervorgang *öffnen–schreiben–schließen* oder per *Temp+Rename* ersetzen. Das gilt für Obsidian und Syncthing und wird durch S1/S4 belegt.
   - **Windows:** vollständig, dank Schreibsperre während des Tauschs.
   - **POSIX/Android:** Späte Schreibzugriffe in ein offenes Handle werden bis zum Ende der Quarantäne (2 min) erkannt und als Konfliktdatei sichtbar gemacht. Danach gilt `GRENZE W1`.
   - Auf Android-Shared-Storage ohne atomare Primitive gilt Garantie 2 nur **eingeschränkt**, mit den Grenzen `A1`–`A3` (siehe Plattform-Tabelle; Nutzerentscheidung „Go, eingeschränkt“ vom 2026-10-09). Auch dort wird nie eine vorhandene fremde Datei überschrieben, und `N` ist immer im Vault sichtbar.
   - Ein Prozessabsturz mitten im Tausch führt beim nächsten Start zu einer sicheren Wiederherstellung oder zu einem sichtbaren Konflikt, nie zu einer stillen Löschung.
3. **Ein Move hinterlässt nach einem Absturz höchstens ein nachvollziehbares Duplikat**, nie einen Verlust.
4. **Eine explizit getroffene Konfliktentscheidung wird durch Absturz, Neustart oder Scan nie stillschweigend rückgängig gemacht.**
   - **Mit vorhandenen App-Daten** wird sie nach einem Absturz vollständig zu Ende geführt (Resolve-Op).
   - **Bei Verlust der App-Daten** ist die Entscheidung selbst **nicht** rekonstruierbar. Der Vault-Marker `…MWENTSCHIEDEN` verhindert dann aber jeden Auto-Merge dieser Konfliktversion, und Merkweiser fragt erneut („Entscheidung unterbrochen, bitte erneut entscheiden“). Diese Absicherung ist eine Nutzerentscheidung vom 2026-10-09.
5. **Die Konfliktdatei ist genauso geschützt wie die Hauptdatei:** Sie wird nie blind gelöscht.
6. **Historie, Sidecars und Journale sind technische Hilfsmittel.** Sie sind nach Vault getrennt, nie Wahrheit, und ihr Fehlen schwächt nur Komfort, nie Korrektheit. Gehen sie verloren, gilt Garantie 4 in der dort benannten Form: Der Marker im Vault verhindert Auto-Merges, und Merkweiser fragt erneut.
7. **Heuristiken (Historien-Basis, Zeitstempel-Reihenfolge) erzeugen nur Vorschläge oder Anzeigereihenfolgen**, nie automatische Entscheidungen.
8. **Mehrdeutigkeit führt zu Konflikt oder `StaleTargetError`, nie zu Raten.**
9. **Parsing und strukturierte Edits erhalten unbekannten Markdown-Inhalt byte-genau.**
10. **Konflikte lassen sich nach einem Neustart aus dem Vault rekonstruieren.**
11. Bewusste Grenzen und Heuristiken sind als `GRENZE` dokumentiert und getestet.

### Wahrheitsmodell (wird so in `docs/ARCHITEKTUR.md` übernommen)

| Instanz | Rolle |
|---|---|
| Markdown-Dateien im Vault | **Einzige fachliche Wahrheit** |
| Obsidian | gleichberechtigter externer Editor. Seine Änderungen werden nie blind überschrieben. |
| Syncthing | gleichberechtigter externer Replikationsweg. Seine Änderungen und Konfliktdateien werden nie blind überschrieben oder gelöscht. |
| `*.sync-conflict-*.md` im Vault | **persistente Quelle für ungelöste Konflikte**, egal ob von Syncthing oder MERKWEISER |
| Op-Verzeichnisse (App-Daten) | **ein einziges Transaktionsmodell**: Manifest, Bytes und Zustand jeder Schreib-, Entfern- und Auflösungsoperation. Nach Abschluss sind sie zugleich die Backups. Der Zustand einer `resolve`-Op ist das „Auflösungs-Journal“. Sie ersetzen nie die Konfliktdatei als Wahrheit. |
| Marker `…MWENTSCHIEDEN` im Vault | von App-Daten unabhängige Spur: „Diese Konfliktversion wurde bewusst entschieden, die Auflösung läuft bzw. wurde unterbrochen.“ Er verhindert Auto-Merges, enthält aber nicht die Entscheidung selbst. |
| Konflikt-Sidecar (App-Daten) | technische Merge-Metadaten eines eigenen Konflikts (verlässliche Basis) |
| Beobachtungs-Historie (App-Daten) | technischer Zustand, liefert nur Merge-*Vorschläge*. Keine Wahrheit, darf jederzeit fehlen. |
| Backups (App-Daten) | Wiederherstellungs-Historie, keine aktive Datenquelle |
| Settings (App-Daten, JSON) | App-Konfiguration außerhalb des Vaults |
| Persistenter Index | gibt es nicht, `BAUSTELLE`. Suche nur im Speicher. |

### Entscheidungen

**Produktentscheidungen (vom Nutzer getroffen):**

| Thema | Entscheidung |
|---|---|
| Projekte | Verschachtelter Tag `#projekt/<projektname>`. Das Präfix ist einstellbar und wird wie jeder Tag vererbt. **Pro Todo-Zeile gibt es ein explizites Projekt;** „Projekt setzen“ ersetzt bzw. entfernt alle expliziten `#projekt/…` der Zeile. Geerbte Projekte wirken zusätzlich und werden als „geerbt“ angezeigt. Von Hand eingetragene Mehrfach-Projekte werden gelesen und angezeigt. |
| Notiz-Trenner | Eine `---`-Zeile ist **nur** dann Trenner, wenn davor eine Leerzeile oder ein Notizanfang steht. Frontmatter am Dateianfang und Codeblöcke werden ignoriert. Die App schreibt Trenner immer mit Leerzeilen davor und danach. |
| Todo verschieben | Ziel ist die Notiz `Verschoben aus [[YYYY-MM-DD]]` in der Zieldatei. Gibt es sie schon, wird sie wiederverwendet, sonst angehängt. Implizite Tags werden explizit an das Todo geschrieben. |
| Tag-Vererbung | Thema, Eltern-Listenpunkt (Einrückung) und umschließende Überschriften |
| Erläuterungsabsatz | Text auf Ebene 0 *vor* dem ersten Listenpunkt gehört zum Thema. Text auf Ebene 0 *nach* Listenpunkten beginnt ein neues Thema. |
| Überschriften | übergeordnete Vererbungsebene bis zur nächsten gleich- oder höherrangigen Überschrift |
| Dateien und Datum | Ganzer Dateiname gegen das Muster, rekursive Suche. Dubletten werden angezeigt und markiert. Sonstige `.md` werden ignoriert. |
| Auto-Merge | Automatisch nur, wenn kein Inhalt verloren geht, plus **„erledigt gewinnt“**. Alles andere wird ein Konflikt mit vorausgewähltem Vorschlag. **Präzisiert am 2026-10-09 (Umsetzung):** Ohne verlässliche Basis (Union) werden beidseitig verschiedene Stellen automatisch zu „beide, A dann B“ (verlustfrei, im Auto-Merge-Protokoll mit Rückgängig; GRENZE: eine Umformulierung steht dann doppelt da). Konflikt-Hunks entstehen nur noch im 3-Wege-Fall. |
| Eigene Konflikte | Eine Konfliktdatei im Vault im Syncthing-Format mit Gerätekennung `MERKWEISER…`. Der Name ist **kollisionssicher** (siehe unten). |
| Backups | 30 Tage. Backups zu offenen Konflikten bleiben erhalten. |
| Schreibprotokoll | **Tausch-Protokoll** (siehe unten) statt „prüfen, dann ersetzen“ |
| Offene Handles (W1) | Die Garantie wird auf belegte Schreibweisen begrenzt. Windows bekommt eine Schreibsperre, POSIX/Android eine Quarantäne von 2 min. |
| App-Daten-Verlust bei Auflösung | Ein **Vault-Marker** `…MWENTSCHIEDEN` an der Konfliktdatei vor dem Schreiben der Hauptdatei |
| Android ohne atomare Primitive | **Exklusiv anlegen** (`O_EXCL`). **Go, aber als „eingeschränkt“ markiert** (`A1`–`A3`). Das wird in Einstellungen und Startbanner angezeigt. Es beansprucht **nicht** die Garantie einer atomaren Installation. |
| Freitextsuche | **Eine Semantik im Core** für beide Plattformen: Standard ist Teilstring ohne Groß-/Kleinschreibung; Regex ist ein expliziter, umschaltbarer Modus auf Desktop **und** Mobile |
| Tag-Filter | Mehrere Tags standardmäßig **UND**, in der Filterleiste auf **ODER** umschaltbar |
| Verschachtelte Konfliktdateien | werden erkannt und der echten Hauptdatei zugeordnet, aber **nur manuell** aufgelöst |
| Android | `MANAGE_EXTERNAL_STORAGE` mit echtem Pfad, **solange S1 nicht widerspricht**. Sonst sofort S1b mit einem anderen Framework. |
| Repo | Monorepo `merkweiser` (dieses Repo), ein gemeinsamer Core |

**Technische Entscheidungen (von mir, jeweils die konservativste Variante):** Journal, Sidecar-Schlüssel, Vault-ID, eindeutige Namen durch exklusives Anlegen, Encoding-Grenze, Fence- und Tab-Regeln, Clock und Zeitzone, Aufbewahrung ab „ersetzt seit“, fsync-Formulierung, `replace_note_text`-Auflösung, `MAIN_DELETED` mit mehreren Konfliktdateien, Protokoll der Auto-Merges, **ein einheitliches Op-Modell (Write-Ahead) mit Wiederherstellungstabellen**, **Zuordnungsmodell in `verify.py`**. Details stehen unten.

### Befunde aus der Erkundung

- **Syncthing** legt `<stem>.sync-conflict-YYYYMMDD-HHMMSS-<DEVICE>.<ext>` ab, ohne Basisversion. Geräte-IDs sind 7 Zeichen lang (`[A-Z2-7]`). Im Vault liegen dutzende solcher Dateien.
- **bw-gui** (Tk/ttk): „Contract“ ist ein Regelwerk.
  - Bausteine: `BwBaseWindow` (Zustand vor `super().__init__()`), `KeybindingRegistry` + `WindowShortcutBinder` + `build_ui_hsm_contract`, `SettingsDialogOrchestrator`, `FileDialogService.askdirectory`, `WrappedTextField`, `Checkbox`/`Switch`, `RegexEntryField`.
  - Es fehlen ein Markdown-Editor, ein Tree-Wrapper, Polling und ein Pfadfeld.
  - Vorbild `../mappenblick` (ohne dessen `bind_all`). Shortcuts nach `../korrektor/app/adapters/gui/main_window_shortcuts.py`.
  - Einbindung über `bw_libs/shared_gui_core.py`.
- **namenfit-mobile** (Flet 0.86.5 gepinnt):
  - `flet build apk` bündelt nur `project.dependencies`.
  - `ft.StoragePaths` für App-Daten; `Path.home()` ist auf Android nicht beschreibbar.
  - Ordnerzugriff war dort nie gelöst.
  - Wiederverwendbar: `platform/android_storage.py`, das Port-Muster, `docs/kurzanleitung.md`.
- **Weitere Helfer:** `namenfit/bw_libs/app_paths.py`, `kursplaner/.../file_signature.py`, Blattwerk `app/ui/blatt_ui_editor.py`.

---

## Nebenaufgabe: bw-gui-Doku korrigieren (eigener Commit in `../bw-gui`, zuerst)

`docs/QUICKSTART.md`:

- **Z. 31:** Der maschinenspezifische absolute Pfad wird zu „Geschwisterordner `../bw-gui`“ (erledigt 2026-10-09).
- **Z. 281–287:** Die Links werden umgebogen:
  - `THEMING.md` → `THEME_CONTRACT.md`.
  - `MENUBAR`/`DIALOGS`/`WIDGETS`/`LAUFKERN` → Verweise auf `src/bw_gui/menu|dialogs|widgets|laufkern/` bzw. Abschnitte in `ARCHITECTURE.md`.
  - `TOGGLE_CONTRACT.md` und `SCROLLABILITY_CONTRACT.md` werden ergänzt.
  - Keine neuen Doku-Dateien.
- Prüfen, dass alle relativen `.md`-Links existieren.
- Kein CHANGELOG-Eintrag, Commit auf main.

---

## Architektur

```text
merkweiser/
  pyproject.toml   # ein Projekt; dependencies = APK-Pakete; Extras dev/ui/build; [tool.flet] app.path="src"
  AGENTS.md  CHANGELOG.md
  bw_libs/shared_gui_core.py      # nur Desktop, außerhalb src/ → nicht im APK
  src/main.py                     # Flet-Shim
  src/merkweiser/core/            # keine UI-/Flet-/Tk-/Android-Abhängigkeit; Dateisystem-I/O erlaubt, wo fachlich nötig
  src/merkweiser/ports/           # Protocols: AppStorage, Clock, FolderPicker
  src/merkweiser/app/             # NotesService (einzige UI-Fassade), Settings
  src/merkweiser/desktop/         # bw-gui
  src/merkweiser/mobile/          # Flet ui/ + platform/
  tests/… , tests/fixtures/*.md   # nur synthetische Notizen
  docs/KONZEPT.md FORMAT.md ARCHITEKTUR.md DEVELOPMENT_LOG.md kurzanleitung.md
```

### App-Daten-Layout (je Gerät, nie im Vault)

```text
<app-daten>/settings.json
<app-daten>/vaults/<vault-id>/               vault-id = sha1(normcase(realpath(Vault-Ordner)))
    meta.json                                Vault-Pfad, angelegt am (um alte Vaults im Backup-Browser zu listen)
    history/<sha1(relpath)>/index.json + <sha1>.md
    ops/<op-id>/manifest.json   NUR der ursprüngliche Plan + geprüfte Referenzen; per Temp+Rename geschrieben, danach unveränderlich
    ops/<op-id>/state.json      EINZIGE Quelle des aktuellen Fortschritts (atomar ersetzt); bei resolve = „Auflösungs-Journal“
    ops/<op-id>/lock            Betriebssystem-Lock (siehe Nebenläufigkeit); Inhalt: Instanz-ID (nur zur Anzeige)
    ops/<op-id>/<rolle>-<sha1>  persistierte Bytes (vorher, neu, verdraengt, konflikt, ergebnis)
    conflicts/<sha1(konflikt-relpath ohne Marker)>.json   Sidecar je Konfliktdatei
    instances/<instanz-id>      Heartbeat laufender Merkweiser-Instanzen
```

**Manifest gegen State (keine widersprüchlichen Quellen):**

- `manifest.json` enthält **keinen** Fortschritt, nur Art, Pfade, Hashes, Eltern-Op und Plan-Daten.
- Der Zustand steht **nur** in `state.json`: `{zustand, unter_ops, hinweise}`.
- **Klassifizierung durch die Wiederherstellung:**
  - Kein `state.json` → die Op wurde nie vorbereitet, der Vault ist garantiert unberührt → ABORTED.
  - `zustand ∈ {PREPARED … QUARANTINE}` → unvollständig.
  - `DONE` / `ABORTED` / `CONFLICTED` → abgeschlossen.
  - `INTERRUPTED` → geklärt, sobald `hinweise.bestaetigt` gesetzt ist.

**Ein einziges Transaktionsmodell:** Jede Schreib-, Entfern-, Move- oder Auflösungsoperation ist ein Op-Verzeichnis. Nach dem Abschluss *ist* dieses Verzeichnis das Backup; der frühere Ordner `backups/` entfällt. Eine `resolve`-Op ist die übergeordnete Transaktion: Ihr `state.json` ist das Auflösungs-Journal, und sie verweist auf ihre Unter-Ops (`safe_write`, Marker-Umbenennung, `safe_remove`) über deren `op-id`.

- **Vault-Isolation:** Zwei Vaults mit gleichem `relpath` teilen nie Historie, Backups, Sidecars oder Journale.
- `GRENZE`: Wird der Vault-Ordner umbenannt oder verschoben, beginnt eine neue ID. Die Historie startet leer (nur schwächere Vorschläge). Alte Backups bleiben unter der alten ID und sind im Backup-Browser sichtbar.
- **`op-id`** = `YYYYMMDD-HHMMSS-<8 Zeichen base32-Zufall>`. Der Ordner wird mit `os.mkdir` angelegt, das bei Existenz fehlschlägt; dann wird ein neuer Zufallsteil erzeugt. Dateien darin werden exklusiv angelegt (`open(…, "xb")`). **Ein Backup kann nie ein anderes überschreiben.**

### Zeit (`ports/clock.py`)

- `Clock.now()` liefert eine zeitzonenbewusste lokale Zeit; `Clock.today()` = `now().date()`.
- **Zeitbasis:** die Zeitzone des Geräts (Betriebssystem), Tageswechsel um Mitternacht.
- Den Clock nutzen: „Heute“ für neue Notizen, eigene Konfliktnamen (lokale Zeit wie bei Syncthing), `op-id`, Historien- und Backup-Zeitpunkte (gespeichert in UTC) und die Aufbewahrungsbereinigung.
- **Monotone Zeit:** `Clock.monotonic()` (in Produktion `time.monotonic()`) misst **ausschließlich verstrichene Dauern innerhalb eines Prozesses**, also die Quarantäne. Die Wanduhr (`now`/`today`) bleibt für Tagesdatum, Konfliktnamen und Zeitpunkte von Historie und Backups zuständig.
  - Dauern werden **nie** über Wanduhr-Vergleiche gemessen, auch nicht über Neustarts hinweg. Eine Quarantäne, die in einen Neustart fällt, **beginnt neu** (volle 2 min ab der Wiederherstellung).
  - Dafür gibt es keine eigene Abstraktion; es ist eine zusätzliche Methode desselben Ports.
- Tests verwenden ausschließlich `FakeClock`, das Wanduhr und monotone Zeit getrennt steuert.

### Parser-Pipeline (eine Richtung, keine konkurrierenden Parser)

`Datei → SourceText (verlustfrei) → Blocks/Spans → Note → Outline → Semantik (Inline-Tokens, effektive Tags, Query)`

| Modul | Verantwortung |
|---|---|
| `source.py` | **Verlustfreies Source-Modell:** Rohbytes, Encoding, BOM-Flag, `Line(no, text, eol)` mit EOL pro Zeile. Serialisieren heißt: unveränderte Original-Zeilen aneinanderhängen. **Kein AST, der neu rendert.** Änderungen sind `LineEdit(range, new_lines)`; neue Zeilen bekommen das dominante EOL. |
| `blocks.py` | Frontmatter, Codeblöcke (opak), Trenner, `NoteSpan(first, last)`. **Alleinige Instanz für Notizgrenzen.** |
| `lexer.py` | Gemeinsame Inline-Tokens (`CODE`, `LINK_URL`, `WIKILINK`, `HIGHLIGHT`, `TEXT`) mit Spalten-Spans |
| `outline.py` | Zeilenklassen nach der Grammatik und Baum. Knoten verweisen auf Zeilen-Spans. |
| `inline.py` | Checkbox (`[ ]`/`[x]`/`[X]`; `[-]` u. a. bleiben erhalten und gelten als normaler Punkt, `GRENZE`), dringend (Inhalt beginnt mit `==…==`), Tags (nur in `TEXT`/`HIGHLIGHT`, nicht rein numerisch), Projekt-Tags über das Präfix |
| `tags.py` | **Reine Auswertung:** effektiv = explizit ∪ Eltern-Punkt ∪ aktuelles Thema ∪ umschließende Überschriften |

**Encoding (bewusst kleine Support-Menge):**

- **Gelesen und geschrieben** werden nur **UTF-8** und **UTF-8 mit BOM** (BOM bleibt erhalten).
- **Alles andere ist „nicht unterstützt“:** ungültige UTF-8-Bytes, UTF-16/32-BOM.
  - Solche Dateien werden mit Ersatzzeichen **nur angezeigt und durchsucht** und mit einem Hinweis markiert.
  - Alle Schreiboperationen werden mit `UnsupportedEncoding` verweigert: Edits, Move als Quelle oder Ziel, Merge, Auflösung.
  - Konfliktdateien in diesem Zustand werden nur manuell außerhalb der App aufgelöst.
- Die Roundtrip-Invariante gilt für unterstützte Dateien; nicht unterstützte werden nie geschrieben.

### Grammatik (verbindlich in `docs/FORMAT.md`)

- **Datei:** optionales Frontmatter, also nur eine `---`-Zeile *als erste Zeile* bis zur nächsten `---`/`...`-Zeile. Danach folgen ≥1 Notizen, getrennt durch Trenner.
- **Codeblock:**
  - Öffnender Fence: ≥3 Backticks oder ≥3 Tilden (bei Backtick-Fences darf die Info-Zeichenkette keine Backticks enthalten), beliebig eingerückt.
  - **Schließender Fence:** dasselbe Zeichen, **Länge ≥ öffnende Länge**, danach nur Leerraum. Deshalb schließt ```` ``` ```` keinen ```` ```` ````-Block.
  - Ein offener Fence läuft bis zum Dateiende (wie Obsidian). Der Codeblock ist opak.
  - `GRENZE`: Mit 4 Leerzeichen eingerückte Codeblöcke (ohne Fence) sind nicht opak.
- **Trenner:** eine `---`-Zeile außerhalb von Code, direkt nach einer Leerzeile oder am Notizanfang. `Text` + `---` ist eine Setext-H2, `===` eine Setext-H1.
- **Notiz:** die Zeilen zwischen Trennern. Leerzeilen am Rand gehören zur Spanne, sind aber kein Inhalt. Leere Notizen werden nicht angezeigt, bleiben aber erhalten.
- **Einrückung:** **Tabstopps bei Vielfachen von 4.** Ein Tab springt zur nächsten Spalte, die ein Vielfaches von 4 ist. Gemischte Tabs und Leerzeichen werden zeichenweise zu einer Spalte verrechnet. Verglichen wird nur die berechnete Spalte; der Text bleibt byte-genau.
- **Zeilenklassen** (Vorrang von oben nach unten):
  1. Leerzeile.
  2. Überschrift (ATX `#{1,6} ` oder Setext; `#tag` ohne Leerzeichen ist ein Tag).
  3. Listenpunkt (`-`/`*`/`+`/`1.`/`1)`).
  4. Fortsetzung (eingerückt nach einem Punkt).
  5. Sonstiges (`>`, `|`, `<`, Bild/Embed-Zeile, eingerückter Text ohne Punkt): wird erhalten, beginnt nie ein Thema.
  6. Absatz auf Ebene 0.
- **Thema:** Ein Absatz auf Ebene 0 beginnt ein Thema, wenn er der erste Absatz der Notiz bzw. unter einer Überschrift ist oder wenn seit dem letzten Themenbeginn ≥1 Listenpunkt kam. Sonst ist er **Erläuterung**, und seine Tags zählen zum Thema. Eine Notiz darf beliebig viele Themen haben.
- **Überschriften-Ebene:** Eine Überschrift der Stufe h gilt bis zur nächsten mit Stufe ≤ h bzw. bis zum Notizende. Sie beendet das aktuelle Thema. Ihre Tags erben alle darunter.
- **Listen-Hierarchie:** Eltern ist der nächste vorhergehende Punkt mit kleinerer Spalte im selben Thema. Ohne einen solchen ist der Punkt Wurzelpunkt (`GRENZE`: flach dargestellt). Punkte vor dem ersten Thema gehören zu einem impliziten Thema ohne Tags.

### Dateien, Zugriff, Schreiben, Merge (getrennte Verantwortung)

| Modul | Verantwortung |
|---|---|
| `vault.py` | **Discovery und Adressierung, kein Schreiben.** Prüft das Muster gegen den ganzen Dateinamen und scannt rekursiv. Liefert `DayFiles(date)` und Dubletten. **Schreibziel:** genau eine existierende Datei → diese; keine → `<Ordner>/<Muster>`; mehrere → die am kanonischen Ort, sonst `AmbiguousDayFile` (die UI fragt). Liefert die Konfliktdatei-Zuordnung (siehe Konflikte). |
| `textfile.py` | Lesen (`FileSnapshot(raw, stat=(mtime_ns, size))`) und die Dateisystem-Primitive des Tausch-Protokolls: `displace`, `install_no_overwrite`, `create_exclusive`, `fsync` |
| `safe_write.py` | `safe_write`, `safe_remove` (Tausch-Protokoll) und das Neuplanen von Ops |
| `ops.py` (Op-Verzeichnisse = Transaktionen und Backups), `history.py`, `watch.py` | siehe unten |
| `merge/` | `align`, `diff3`, `union`, `verify`, `conflicts` (Zuordnung, Auflösung, Journal, Sidecars) |
| `edits.py`, `move.py`, `query.py` | fachliche Ops und Suche |

**Signatur:** `(mtime_ns, size)` ist nur ein Änderungshinweis für das Polling, keine Identität. **Maßgeblich ist der Inhalt.** Guards vergleichen Rohbytes. `sha1` dient nur als Schlüssel für Historie, Backups, Sidecars und Journale.

### Edit-Ziele (keine IDs)

- **Ziel:** `Target(relpath, line_no, expected_text)` bzw. `BlockTarget(relpath, first_line, expected_lines)`. Das ist eine flüchtige Adresse.
- **Auflösung:**
  1. Steht das Ziel noch an derselben Stelle → Treffer.
  2. Sonst alle exakten Vorkommen suchen. **Genau eines** → Treffer.
  3. Kein oder mehrere Vorkommen → `StaleTargetError`. Es wird nie geraten.
- **Ops:**
  - `toggle_done`: schreibt `[x]`, ändert ein vorhandenes `[X]` nicht.
  - `toggle_urgent`.
  - `set_project(name | None)`: entfernt alle expliziten `#projekt/…`-Tokens der Zeile (samt genau einem angrenzenden Leerzeichen) und hängt bei `name` ` #projekt/<name>` am Zeilenende an. Geerbte Projekte bleiben unberührt.
  - `add_todo`, `append_note`, `replace_note_text`, `delete_note` (Notiz-Spanne und genau ein angrenzender Trenner, Naht-Leerzeilen).
- **`replace_note_text`-Auflösung:**
  - Die ursprüngliche Notiz gilt als gefunden, wenn ihre Inhaltszeilen **genau einmal** als zusammenhängende Folge vorkommen **und** diese Folge im neuen Parse genau den Inhalt einer `NoteSpan` bildet. Die Grenzen sind also noch Trenner.
  - Sonst (Trenner eingefügt oder entfernt, Notiz geteilt, Grenzen verschoben, mehrere Kandidaten) wird **nicht geraten** und keine „ähnlichste Notiz“ gesucht.
  - Da der getippte Text nicht verloren gehen darf, entsteht in diesem Fall kein `StaleTargetError`, sondern eine **eigene Konfliktdatei**. Ihr Inhalt ist der Planungs-Snapshot mit ersetzter Notiz; das Sidecar enthält `base_sha1` = Planungs-Snapshot.

### Schreibprotokoll: Tausch-Protokoll mit Write-Ahead und Wiederherstellung (`safe_write.py`)

**Zentrale Invarianten:** Das sind die einzigen Regeln, auf die sich jeder Schritt und jede Wiederherstellung stützt.

- **L – Löschinvariante:** Eine Datei im Vault-Ordner wird nur unter einer von zwei Bedingungen entfernt. Das gilt für Hauptdateien, Konfliktdateien und eigene `.mw-*`-Dateien.
  - Ihre exakten Bytes liegen **vorher** als Kopie im Op-Verzeichnis: persistiert, mit `fsync` gesichert und durch erneutes Hashen geprüft. **Und** eine erneute Prüfung unmittelbar vor dem Entfernen zeigt dieselben Bytes.
  - **Oder** sie wird per atomarem Rename an einen anderen Vault-Pfad verschoben. Ihr Inhalt bleibt dann im Vault.
  - Eine Ausnahme gibt es nur für die eigene, nie installierte Temp-Datei, deren Ziel-Bytes `N` bereits persistiert sind.
- **I – Installationsinvariante:** Merkweiser legt im Vault **nur ohne Überschreiben** an. Wie das je Plattform geht, steht in der Plattform-Tabelle.
- **R – Determinismus der Wiederherstellung:** Die Wiederherstellung entscheidet ausschließlich aus dem unveränderlichen Manifest und dem aktuellen Plattenzustand, also den Hashes von `P`, `T` und `D`. `state.json` ist nur ein Hinweis auf den Fortschritt. Einzige Ausnahme: Im `O_EXCL`-Fallback wird die dort festgehaltene Identität von `P` (`P_CREATED`) als Beweis für „eigene Teildatei“ genutzt. Fehlt sie oder passt sie nicht, wird **konservativ „fremd“** angenommen, sodass ihr Fehlen nie zu einer Löschung führt. Jede Wiederherstellungsaktion unterliegt selbst L und I. Damit ist die Wiederherstellung idempotent, und ein Abbruch *während* der Wiederherstellung wird beim nächsten Start einfach fortgesetzt.
- **Backups sind immer Kopien** (eigene Datei, eigenes Inode), nie die verdrängte Datei selbst. Ein offenes fremdes Handle kann daher **kein** Backup nachträglich verändern, und der Manifest-Hash bleibt gültig.

**Bezeichnungen:**

- `P` = Zielpfad, `T` = `.<name>.mw-<op-id>.tmp`, `D` = `.<name>.mw-<op-id>.old`.
- `E` = erwartete Bytes (oder ABSENT), `N` = neue Bytes, `X` = ein beliebiger fremder Stand.

`safe_write(P, E, N, op)` – **Ersetzen-Pfad** (`E` ≠ ABSENT). Den **Create-only-Pfad** (`E` = ABSENT) beschreibt der Abschnitt danach.

0. **Planen und neu planen** wie gehabt: Datei neu lesen.
   - Bei Abweichung werden strukturierte Ops neu geplant (höchstens 3 Versuche, dann `StaleTargetError`).
   - `replace_note_text` wird per 3-Wege-Merge eingearbeitet bzw. landet in einer eigenen Konfliktdatei.
   - Eine extern gelöschte Datei, an der eine Änderung geplant war → eigene Konfliktdatei.
1. **PREPARED (Write-Ahead):**
   - Op-Verzeichnis per exklusivem `mkdir` anlegen, dazu `lock`.
   - `manifest.json` mit `{art, relpath, T, D, E_sha1, N_sha1, eltern_op}`.
   - Bytes `E` und `N` ablegen, `fsync`, erneut hashen.
   - Schlägt etwas fehl → Abbruch, **der Vault ist unberührt**.
2. **TMP_READY:** `T` exklusiv anlegen, `N` schreiben, `fsync`.
3. **DISPLACED:**
   - *Windows:* zuerst ein Handle auf `P` mit Freigabe nur für Lesen und Löschen öffnen (`CreateFileW` über ctypes, Schreib-Freigabe verweigert). Schlägt das wegen einer Sharing-Violation fehl, hat jemand die Datei zum Schreiben offen → 3× kurz wiederholen, dann Abbruch („Datei gerade in Benutzung“). Das Handle verhindert außerdem, dass während des Tauschs jemand Neues zum Schreiben öffnet.
   - Dann wird `P` atomar nach `D` umbenannt (unter Windows über das Handle).
4. **INSTALLED:** `T` wird ohne Überschreiben nach `P` installiert. Ist `P` belegt → `T` wird ohne Überschreiben zur eigenen Konfliktdatei.
5. **Die verdrängte Fassung sichern:**
   - `D` als Kopie ins Op-Verzeichnis legen (`verdraengt`, `fsync`, erneut hashen).
   - Ist der Hash gleich `E` → weiter mit 6.
   - Ist er ungleich `E` (eine fremde Änderung kam kurz vor Schritt 3), wird zurückgetauscht: Die eigene Version in `P` wird per Rename ohne Überschreiben zur eigenen Konfliktdatei (Sidecar mit `base_sha1 = E`, also verlässliche Basis). Dann wird `D` ohne Überschreiben nach `P` installiert; ist `P` belegt, wird auch `D` zur Konfliktdatei. Zustand: CONFLICTED.
6. **QUARANTINE (2 min, gemessen mit `Clock.monotonic()`, auf allen Plattformen):**
   - *Windows:* Das Handle wird jetzt geschlossen. Späte Schreibzugriffe in `D` hat die Schreibsperre ausgeschlossen; die Quarantäne dient hier nur der Prüfung von `P`.
   - *POSIX/Android:* `D` bleibt im Vault-Ordner liegen.
   - **Abschlussprüfung, in dieser Reihenfolge. Erst wenn beide Prüfungen erfüllt sind, gilt die Op als DONE:**
     1. **Zieldatei `P` prüfen.**
        - `P = N` → in Ordnung.
        - `P ≠ N` (extern ersetzt oder verändert, z. B. Temp+Rename eines Editors) oder `P` fehlt → `P` bleibt **unangetastet**. Liegt keine Vault-Datei mit dem Hash `N` vor (gesucht über eigene Konfliktdateien zu `P`), wird `N` **exklusiv als eigene Konfliktdatei** aus dem Op-Verzeichnis angelegt (Sidecar `base_sha1 = E`). Zustand CONFLICTED mit dem Hinweis „deine Änderung wurde extern verdrängt“.
     2. **`D` prüfen:** neu hashen. Gleich der Kopie → `D` löschen (L) → DONE (bzw. CONFLICTED, falls 1. das ergab). Ungleich (später Schreibzugriff) → `D` per Rename zur eigenen Konfliktdatei → CONFLICTED.
   - Fällt das Quarantäne-Ende in einen Neustart, **beginnt die Quarantäne neu** (siehe Clock). Die Abschlussprüfung läuft dann in der Wiederherstellung.
   - `GRENZE W5`: Ersetzt ein externer Schreiber `P` erst **nach** dem Abschluss (DONE) durch einen Stand, der nicht auf `N` beruht, ist das sein eigener „Lost Update“ und gilt als normale externe Änderung. `N` liegt dann nur noch im Op-Verzeichnis bzw. Backup.
7. **Historie** ergänzen (Best Effort). Die Op ist DONE, und ihr Verzeichnis dient als Backup (Aufbewahrung wie bisher).

**Create-only-Pfad** (`E` = ABSENT, z. B. eine neue Tagesdatei oder eine eigene Konfliktdatei):

1. **PREPARED** (Manifest mit `E = ABSENT`, Bytes `N`).
2. **TMP_READY** (`T` exklusiv, `N`, `fsync`).
3. Es gibt **kein** Wegbenennen.
4. **INSTALLED:** `T → P` ohne Überschreiben.
   - **Ist `P` vorhanden** (inzwischen extern angelegt) → die fremde Datei bleibt unangetastet; `T` wird ohne Überschreiben zur eigenen Konfliktdatei → CONFLICTED.
   - **Es wird nie erneut versucht**, `P` zu belegen. Ein Neuplanen auf den fremden Inhalt passiert nur über ein neues `safe_write` mit `E` = dessen Inhalt, und zwar nur bei strukturierten Ops (z. B. `append_note`).
5. **QUARANTINE** nur mit der Abschlussprüfung von `P` (kein `D`) → DONE bzw. CONFLICTED.

**Android-Fallback `O_EXCL`** (nur wenn der Selbsttest keine atomare Primitive findet), gilt für Ersetzen und Create-only:

- **Schritt 4** wird zu:
  1. Zustand `INSTALLING` persistieren.
  2. `P` mit `O_CREAT|O_EXCL` öffnen. Scheitert das (Pfad belegt) → die eigene Version wird Konfliktdatei, wie oben.
  3. **Sofort** die Identität der neuen Datei (`st_dev`, `st_ino` per `fstat`) in `state.json` eintragen (`zustand: P_CREATED, p_identitaet`).
  4. `N` schreiben, `fsync`, schließen.
  5. **Über den Pfad nachprüfen:** `P = N` und Identität gleich → INSTALLED. Sonst wurde `P` extern ersetzt oder verändert → `P` bleibt, `N` wird eigene Konfliktdatei → CONFLICTED.
- **Abbruch mit partiellem `P`:**
  - **Eigen** ist ein partielles `P` nur, wenn *alle* drei Bedingungen gelten: Zustand `P_CREATED`, aktuelle Identität = `p_identitaet` und Inhalt = echtes Präfix von `N`. Dann wird `P` per Rename nach `.<name>.mw-<op-id>.partial` verschoben. Sind Identität und Präfix danach unverändert, wird die Datei gelöscht (Ausnahme in L wie bei `T`), und Schritt 4 läuft erneut.
  - **Sonst** (Zustand nur `INSTALLING`, Identität unbekannt oder abweichend) gilt `P` als **fremd** und bleibt. `N` wird eigene Konfliktdatei → `GRENZE A2`.
- **Was Syncthing sieht:** Es kann den Teilstand scannen und an andere Geräte verteilen, danach den vollständigen. Bearbeitet ein Gerät den Teilstand, entsteht dort ein Syncthing-Konflikt (sichtbar) → `GRENZE A1`.
- **Ehrliche Garantie dieses Fallbacks:** Eine vorhandene Datei wird nie überschrieben, und `N` ist immer im Vault sichtbar (als `P` oder als Konfliktdatei).
  - **Nicht** garantiert ist eine Hauptdatei, die immer vollständig ist: `A1` (Teilstände für Millisekunden sichtbar) und `A2` (nach einem Absturz ohne Identitätsnachweis eine abgeschnittene Hauptdatei bis zur Konfliktauflösung).
  - **Ebenfalls nicht** garantiert ist Schutz vor gleichzeitigem In-place-Schreiben in die entstehende Datei → `A3`, gemischter Inhalt. Beide Quellen bleiben aber sichtbar, soweit der fremde Schreiber nicht selbst überschreibt.

`safe_remove(C, C0)` (Konfliktdatei entfernen) läuft wie der Ersetzen-Pfad ohne die Schritte 2 und 4:

- PREPARED mit Bytes `C0`.
- Unter Windows die Schreibsperre, dann `C → D`.
- Kopie anlegen und mit `C0` vergleichen.
  - Gleich → Quarantäne → löschen.
  - Ungleich → `D` wird ohne Überschreiben nach `C` zurückinstalliert; ist `C` belegt, unter einem neuen eigenen Konfliktnamen. Zustand CONFLICTED. **Eine Konfliktdatei wird nie blind gelöscht.**

**Plattform-Tabelle** (wird durch S1/S4 bestätigt oder korrigiert; ohne Bestätigung gibt es keine Garantie):

| Plattform | Wegbenennen | Installieren ohne Überschreiben | Offene Handles | Garantie 2 |
|---|---|---|---|---|
| Windows/NTFS | atomarer Rename über ein Handle mit Schreibsperre | `os.rename` (schlägt bei Existenz fehl), atomar | durch die Schreibsperre ausgeschlossen | voll |
| Linux / Android intern (ext4/f2fs) | `rename` | `os.link` + `unlink` oder `renameat2(RENAME_NOREPLACE)`, atomar | Quarantäne 2 min | voll für die belegten Schreibweisen, danach `W1` |
| Android Shared Storage (FUSE) | `rename` (S1) | atomar, falls S1 `link`/`NOREPLACE` belegt → wie Zeile darüber, **voll**. **Sonst `O_EXCL`-Fallback** | Quarantäne 2 min | **eingeschränkt** (`A1`–`A3`), nicht gleichwertig mit atomar |

- **Kein stiller Wechsel:** Welche Variante aktiv ist, wird beim Start je Vault per Selbsttest der Primitive ermittelt, protokolliert und in Einstellungen und Startbanner angezeigt („Schreibgarantie: voll“ bzw. „eingeschränkt (A1–A3)“).
- **No-Go:** Fehlen selbst atomarer Rename oder `O_EXCL` → **dieser Vault wird schreibgeschützt geöffnet**, mit Hinweis. Für Android folgt dann S1b.

**Verbleibende Grenzen** (ehrlich, getestet und dokumentiert):

- `GRENZE W1` (POSIX/Android): Ein Schreiber, der ein vor Schritt 3 geöffnetes Handle **länger als die Quarantäne** offen hält und dann hineinschreibt, schreibt in ein bereits gelöschtes Inode. **Diese Änderung geht verloren.** Ausdrücklich unterstützt sind nur die Schreibweisen „öffnen–schreiben–schließen pro Speichern“ und „Temp+Rename“ (Obsidian, Syncthing, belegt durch S1/S4). Nutzerentscheidung vom 2026-10-09.
- `GRENZE W2`: Zwischen den Schritten 3 und 4 existiert `P` für Mikrosekunden nicht. Ein Syncthing-Scan genau in diesem Moment könnte eine Löschung verteilen und danach die Neuanlage. Inhalt geht nicht verloren; auf anderen Geräten kann ein Konflikt entstehen.
- `GRENZE W4`: Stürzt Merkweiser **zwischen den Schritten 3 und 4** ab, fehlt `P`, bis Merkweiser wieder startet. Syncthing kann die Löschung in dieser Zeit verteilen. Der Inhalt liegt sicher in `D` (Vault) und im Op-Verzeichnis. Die Wiederherstellung installiert ihn beim nächsten Start, und Syncthing verteilt ihn erneut. Hat ein anderes Gerät die Datei gleichzeitig bearbeitet, löst Syncthing das als Konflikt auf (Änderung schlägt Löschung). Die Kurzanleitung empfiehlt `.stignore`: `.*.mw-*`, damit `D`/`T` nicht verteilt werden.
- `GRENZE A1`–`A3` (nur Android-Shared-Storage im `O_EXCL`-Fallback): `A1` Teilstände für Millisekunden sichtbar und synchronisierbar; `A2` nach einem Absturz ohne Identitätsnachweis eine abgeschnittene Hauptdatei bis zur Konfliktauflösung (`N` als Konfliktdatei, `E` im Op-Verzeichnis); `A3` gemischter Inhalt bei gleichzeitigem In-place-Schreiben in die entstehende Datei. Eine vorhandene Datei wird nie überschrieben. Nutzerentscheidung: Go, eingeschränkt.
- `GRENZE W5`: siehe Schritt 6 (externe Lost Updates nach DONE).
- **Dauerhaftigkeit:** Garantiert ist „nie halb geschrieben sichtbar“ (außer im `O_EXCL`-Fallback, `A1`–`A3`), **nicht** „nach Stromausfall sicher auf dem Datenträger“. Ein Verzeichnis-`fsync` gibt es nur auf POSIX. Nach einem Stromausfall kann der letzte Schreibvorgang fehlen; Op-Verzeichnis und Wiederherstellung fangen das ab, soweit das Dateisystem Metadaten journalt (NTFS/ext4/f2fs).

**Wiederherstellungstabelle** (je unvollständiger Op, deren `lock` frei oder veraltet ist; die Wiederherstellung übernimmt den Lock):

| # | Absturz nach … | mögliche Plattenzustände | Aktion beim nächsten Start |
|---|---|---|---|
| 1 | Beginn PREPARED (Manifest bzw. Bytes nicht vollständig geprüft) | Vault unberührt (der Vault wird erst nach PREPARED berührt) | Op → ABORTED. Ist `N` persistiert, Hinweis „Änderung wurde nicht ausgeführt“ mit **Wiederholen** (über das normale `safe_write` mit Guard). Ist `N` nicht persistiert, gab es noch keine vom Nutzer bestätigte Speicherung; Hinweis ohne Wiederholen. |
| 2 | PREPARED / TMP_READY, `D` fehlt | `P` = `E` oder `X`; `T` fehlt, ist teilweise oder vollständig | `T` entfernen (Ausnahme in L) → ABORTED mit Hinweis und Wiederholen |
| 3 | DISPLACED: `D` vorhanden, `P` fehlt | Absturz zwischen den Schritten 3 und 4 | `hash(D)=E`: `N` (aus `T` oder dem Op-Verzeichnis) ohne Überschreiben nach `P` → weiter bei 5. `hash(D)≠E`: `D` ohne Überschreiben nach `P` (der fremde Stand gewinnt), `N` als eigene Konfliktdatei → CONFLICTED. |
| 4 | DISPLACED, `P` vorhanden mit `X` (extern angelegt, während Merkweiser nicht lief) | `D` vorhanden | `P` bleibt. `N` wird eigene Konfliktdatei. `D`: Ist der Hash `E` → nach L löschen, sonst → eigene Konfliktdatei. CONFLICTED. |
| 5 | INSTALLED, `D` noch nicht gesichert | `P` = `N` oder `X`; `D` vorhanden | Schritt 5 für `D` ausführen. Danach eine **neue** Quarantäne mit Abschlussprüfung: `P = X` bleibt unangetastet, **`N` wird eigene Konfliktdatei**, falls sie nirgends im Vault liegt. |
| 6 | Rücktausch unvollständig (CONFLICTED in Arbeit) | z. B. `P = N` und `D ≠ E`; oder `P` fehlt, `D` vorhanden, Konfliktdatei mit `N` vorhanden | Ziel-Endzustand herstellen: Der fremde Stand steht in `P`, `N` steht in einer eigenen Konfliktdatei. Fehlende Teile werden nach L und I ergänzt; eine Konfliktdatei mit `N` wird zuerst über ihren Hash gesucht, damit keine Duplikate entstehen. |
| 7 | QUARANTINE | `P` = `N`, `X` oder fehlt; `D` vorhanden (bzw. kein `D` bei Create-only) | Quarantäne **neu beginnen** (monoton, 2 min), dann die Abschlussprüfung aus Schritt 6. Zuerst `P` (bei `P ≠ N` und fehlendem `N` im Vault → `N` als Konfliktdatei), dann `D` (gleich der Kopie → löschen, sonst → Konfliktdatei). Erst danach DONE bzw. CONFLICTED. Typischer Fall nach Neustart: `P = X`, `D = E`, `N` nur im Op-Verzeichnis → `N` wird sichtbar, `D` gelöscht. |
| 7a | Create-only: TMP_READY / INSTALLING | `P` fehlt bzw. ist vorhanden; `T` vorhanden | `P` fehlt → `T` (oder `N` aus dem Op-Verzeichnis) ohne Überschreiben installieren → Zeile 7. `P` vorhanden mit `N` → Zeile 7. `P` vorhanden mit anderem Inhalt → fremd, `P` bleibt, `N` wird Konfliktdatei → CONFLICTED. |
| 7b | `O_EXCL`-Fallback: INSTALLING / P_CREATED | `P` partiell, vollständig oder fremd | Wie im Fallback-Abschnitt: **eigen** nur bei P_CREATED + gleicher Identität + Präfix von `N` → beiseite schieben und neu installieren. Sonst fremd → `N` wird Konfliktdatei (`A2`). `P = N` mit gleicher Identität → Zeile 7. |
| 8 | `safe_remove` nach dem Verdrängen | `D` vorhanden, `C` leer oder neu belegt | Kopie anlegen und mit `C0` vergleichen. Gleich → Quarantäne → löschen. Ungleich → zurück nach `C` bzw. unter einem neuen eigenen Konfliktnamen. |
| 9 | Abbruch *während* der Wiederherstellung | ein Zwischenzustand von 1–8 | dieselbe Tabelle erneut anwenden (R: idempotent) |
| 10 | Der Betriebssystem-Lock der Op gehört einer anderen Instanz (auch einer suspendierten) | – | **Nicht übernehmen**, überspringen. Der Scan markiert `P`/`C` als „in Bearbeitung durch eine andere Instanz“: kein `MAIN_DELETED`, kein Merge, keine Auflösung. Die UI zeigt den Hinweis (inkl. Heartbeat-Alter). |
| 11 | **Verwaiste** `.mw-*.tmp`/`.old` ohne bekanntes Op-Verzeichnis (App-Daten verloren oder trotz `.stignore` von einem anderen Gerät synchronisiert) | – | **Nie** nach Alter löschen oder ins Backup verschieben. Beide werden per Rename **zu eigenen Konfliktdateien** und sind damit sichtbar. Auch ein unvollständiges `.tmp` wird gezeigt statt verworfen. |

**Startreihenfolge (fest):**

1. Instanz-Heartbeat starten.
2. **Op-Wiederherstellung** auf der Tausch-Ebene.
3. **Wiederherstellung der Resolve-Ops.**
4. Verwaiste `.mw-*`-Dateien behandeln.
5. Scan und Rekonstruktion der Konflikte.
6. Auto-Merge.

- Eine Hauptdatei, die fehlt, während zu ihr eine unvollständige Op existiert, gilt **nie** als externe Löschung.
**Nebenläufigkeit (Betriebssystem-Lock statt Zeitablauf):**

- **Exklusiv besitzen:** Wer eine Op ausführt oder wiederherstellt, hält einen **Betriebssystem-Lock** auf `ops/<op-id>/lock`, und zwar über die gesamte Ausführung. Unter POSIX/Android ist das `fcntl.flock(LOCK_EX|LOCK_NB)`, unter Windows `msvcrt.locking(LK_NBLCK)` auf Byte 0 eines offenen Handles.
  - Die App-Daten liegen immer auf einem lokalen Dateisystem (nie im Vault, nie FUSE oder Netz). Dort sind diese Locks verlässlich.
- **Freigabe:** Ein Lock gilt **nur** als frei, wenn das Betriebssystem ihn freigibt, also bei explizitem Unlock oder beim **Ende des Prozesses**. Ein **suspendierter** Prozess (z. B. Android im Hintergrund) behält seinen Lock. Deshalb kann eine zweite Instanz die Op **nicht** übernehmen, und es gibt keine gleichzeitige wirksame Ausführung.
- **Heartbeat** (`instances/<instanz-id>`, alle 10 s) dient **nur der Anzeige** („seit 3 min keine Lebenszeichen“). Er ist **kein** Kriterium für eine Übernahme. Das ersetzt die frühere Regel „Übernahme nach 60 s“.
- **Fencing als zweite Linie:** `state.json` trägt eine `epoche`, die bei jeder Übernahme erhöht wird. Vor **jedem** Zustandsübergang und **jeder** Vault-Operation prüft der Ausführende, dass er den Lock noch hält und dass die Epoche in `state.json` seiner eigenen entspricht. Sonst bricht er sofort ab, ohne weitere Wirkung. Das schützt gegen Programmierfehler bei der Lock-Behandlung und gegen Dateisysteme, die den Lock wider Erwarten nicht durchsetzen (Selbsttest beim Start: Lock aus einem zweiten Prozess testen; scheitert der Test → nur eine Instanz pro Vault zulassen, durch einen Vault-Lock beim Start).
- **Gleichzeitige Wiederherstellung:** Der Lock wird nicht blockierend versucht, der Verlierer überspringt (Zeile 10).
- Alle Namen enthalten die `op-id` und werden exklusiv angelegt.
- **Liveness:** Blockiert eine hängende Instanz eine Op, bleibt die Op sichtbar „in Bearbeitung“, bis der Nutzer jene Instanz beendet. Sicherheit geht vor Fortschritt.

**Alle höheren Operationen (Edits, Move, Merge, Konfliktauflösung) setzen nur diese Garantien voraus und keine stärkeren.**

### Move-Protokoll (`move.py`)

**Invariante:** Ein Absturz hinterlässt höchstens ein Duplikat. Die Quelle wird nur verändert, wenn sie den geplanten Block nachweislich noch byte-gleich und eindeutig enthält. Externe Änderungen in Race-Fenstern deckt `safe_write` ab; sie werden als Konflikt sichtbar.

1. **Planen:** `S0 = read(src)`, Block `B` (Todo mit Kindern und Fortsetzungen). `B'` = `B` mit den impliziten Tags explizit an der Wurzelzeile. `T0 = read(dst)`. Das Ziel bestimmt `vault`; bei `AmbiguousDayFile` wird abgebrochen.
2. **Ziel** per `safe_write`: `B'` wird ans Listenende der letzten Notiz `Verschoben aus [[<Quelldatum>]]` angehängt, sonst als neue Notiz mit Trenner. Wird das endgültig `StaleTargetError` → **nichts geändert**.
3. **Quelle** per `safe_write`: `B` als exakte Zeilenfolge auflösen.
   - Genau ein Treffer → entfernen (Naht-Leerzeilen).
   - Sonst → **Quelle unverändert**, Ergebnis `MoveResult.INCOMPLETE` („Todo steht jetzt in beiden Dateien“) mit den Optionen „Quelle trotzdem entfernen“ (nach erneuter Prüfung) oder „beide behalten“.
4. Gleiche Datei → ein einziger Patch.
5. **Absturzstellen:** vor 2 → nichts; während eines Writes → Tausch-Protokoll; zwischen 2 und 3 → sichtbares Duplikat; nach 3 → fertig.

**Move als Op (idempotent, ohne Todo-IDs):**

- Jeder Move ist eine Eltern-Op `art: move`.
  - **Manifest:** `src`, `dst`, `S0_sha1`, `T0_sha1`, die exakten Bytes von `B` und `B'`, die Ziel-Notizüberschrift.
  - **State:** `zustand ∈ {PREPARED, ZIEL_GESCHRIEBEN, QUELLE_ENTFERNT, DONE, INCOMPLETE}` und die `op-id`s der Unter-Ops `ziel` und `quelle`.
- **Identität:** Ein Move ist **diese Op** mit ihren exakten Inhalten. Nie zählt „ähnlicher Text im Ziel“.
- **Ob das Ziel geschrieben wurde, entscheidet ausschließlich der Zustand der Unter-Op `ziel`:**
  - DONE → geschrieben.
  - ABORTED → nicht geschrieben.
  - CONFLICTED → `B'` liegt in einer Konfliktdatei → INCOMPLETE.
  - Unvollständig → zuerst die Tausch-Wiederherstellung, dann neu bewerten.
- **Wiederaufnahme statt Neuanlage:**
  - Nach einem Absturz setzt die Wiederherstellung eine Move-Op ab dem ersten unerledigten Schritt fort. Ist das Ziel bereits geschrieben, wird es **nie** erneut angehängt.
  - Danach folgt Schritt 3 mit exaktem Blocknachweis in der Quelle.
- **UI-Wiederholung:**
  - „Erneut versuchen“ bzw. „Quelle trotzdem entfernen“ bei INCOMPLETE beziehen sich auf die **vorhandene Op** (`op-id`).
  - Will der Nutzer denselben Quellblock (gleiche `src` und byte-gleiches `B`) erneut verschieben, während eine unvollständige Move-Op dafür existiert, bietet die UI **„vorhandenen Vorgang fortsetzen“** an statt eines neuen Moves.
  - So entsteht nie unkontrolliert ein zweiter Zielblock.
- **Zielnachweis vor „Quelle trotzdem entfernen“:** `B'` muss im Ziel **genau einmal** als exakte Zeilenfolge vorkommen. Ist er extern verändert, fehlt er oder steht er mehrfach im Ziel → die Quelle wird nicht angefasst, der Zustand bleibt INCOMPLETE und sichtbar („Zielblock nicht eindeutig nachweisbar“). Es wird nichts automatisch bereinigt.
- **Die Quelle** wird weiterhin nur nach exaktem und eindeutigem Blocknachweis verändert.

### Merge (`merge/`), konservativ

- **Ausrichtung (`align.py`):** `difflib.SequenceMatcher(autojunk=False)`. **Anker sind nur Zeilen, die auf beiden Seiten genau einmal vorkommen** (Patience-Prinzip). Leerzeilen und wiederholte Zeilen verankern nie allein.
- **Änderungsregion:** ein maximaler Bereich zwischen zwei Ankern, in dem sich die Seiten unterscheiden. Benachbarte Regionen ohne Anker dazwischen werden verschmolzen.
- **Einseitige Einfügung:** Die Region ist auf der Gegenseite bzw. in der Basis leer.
- **Mit verlässlicher Basis (`diff3.py`)**, nur als Edit-Basis (`replace_note_text`) oder als Sidecar-Basis eigener Konflikte:

  | Fall | Ergebnis |
  |---|---|
  | Nur eine Seite ändert | diese Seite. Das ist erlaubt, weil die Änderung eine explizite Nutzeraktion auf dieser Seite war. |
  | Beide ändern identisch | einmal übernehmen |
  | Beide fügen am selben Anker verschiedenes ein | verlustfrei, Hauptdatei zuerst (Konzeptbeispiel A+B+C) |
  | Beide ändern dieselbe Region verschieden | Konflikt, außer R1/R2 |
  | Löschung gegen Änderung | **Konflikt** |

- **Ohne verlässliche Basis (`union.py`):**
  - Region nur in A oder nur in B → behalten. `GRENZE`: Einseitige Löschungen kommen zurück („lieber doppelt als verloren“).
  - Beidseitig verschieden → R1/R2, sonst Konflikt-Hunk.
  - Eine Kandidatenbasis aus der Historie erzeugt **nur den vorausgewählten Vorschlag**.
- **Merge-Regel „erledigt gewinnt“** (die einzige erlaubte Inhaltsersetzung ohne Nutzeraktion):
  - **R1:** Ein Zeilenpaar, das sich **nur** im Statuszeichen `[ ]` gegenüber `[x]`/`[X]` unterscheidet → die erledigte Zeile byte-genau übernehmen.
  - **R2:** Ein Zeilenpaar, das sich **nur** in `[x]` gegenüber `[X]` unterscheidet → die Zeile der **Hauptdatei** byte-genau übernehmen. Es wird nicht normalisiert.
  - Die Regeln gelten nur, wenn die Region auf beiden Seiten dieselbe Zeilenzahl hat und *jedes* Paar unter R1 oder R2 fällt.
  - `GRENZE`: Ein bewusstes Wieder-Öffnen geht verloren. Der vorige Stand liegt im Backup.
- **Verlustprüfung (`verify.py`, unabhängig vom Algorithmus): Zuordnungsmodell**
  - **Vorkommen:** Jede Eingabezeile ist ein Vorkommen `(Seite, Index)` mit Seite ∈ {A, B, Basis}. Jede Ausgabezeile ist ein Vorkommen `(Out, Index)`.
  - **Was der Merger liefert:** neben dem Ergebnis eine **Zuordnung** `f: Eingabe-Vorkommen → Ausgabe-Vorkommen` und für jede Zuordnung ein **Zertifikat**:
    - `ANKER`: ein eindeutiger Anker aus `align`.
    - `UEBERNAHME`: Die Zeile stammt aus genau einer Seite.
    - `IDENTISCHE_AENDERUNG(region)`: Eine Region liegt zwischen denselben beiden Ankern, die **in allen beteiligten Sequenzen** eindeutig sind (A, B und im diff3-Modus auch die Basis). Die Zeilenfolge in der Region ist auf A und B **byte-gleich** und unterscheidet sich von der Basisregion. Das umfasst **identische Einfügungen** (Basisregion leer) und **identische Ersetzungen** (Basisregion nicht leer, z. B. `B → C` auf beiden Seiten). A- und B-Vorkommen werden positionsweise gepaart und auf **ein** Ausgabe-Vorkommen abgebildet. Die Basis-Vorkommen der Region gelten **durch dieses Zertifikat als ersetzt**.
    - `R1` bzw. `R2`.
  - **Was `verify` unabhängig prüft** (die Ausrichtung wird für die Anker-Zertifikate selbst neu berechnet):
    1. **Je Seite injektiv:** Zwei Vorkommen *derselben* Seite fallen nie auf ein Ausgabe-Vorkommen. Zwei gleiche Zeilen auf einer Seite bleiben also zwei Zeilen.
    2. **Je Seite monoton:** Die Reihenfolge bleibt erhalten.
    3. **Viele-zu-eins nur seitenübergreifend** und nur mit dem Zertifikat `ANKER` oder `IDENTISCHE_AENDERUNG`. Gleicher Text allein ist **kein** Beweis: Gleicher Inhalt an anderer Stelle bzw. in einer anderen Region wird nicht zusammengelegt.
    4. **Byte-Gleichheit** zwischen Eingabe- und Ausgabe-Vorkommen, außer bei protokollierten `R1`/`R2`-Ersetzungen. Diese bleiben eine **eigene Kategorie** und werden nicht mit identischen Änderungen vermischt.
    5. **Vollständigkeit:**
       - *Union-Modus:* Jedes A- und B-Vorkommen ist zugeordnet.
       - *diff3-Modus:* Ein fehlendes Basis-Vorkommen ist nur zulässig, wenn (i) eine Seite es entfernt oder geändert hat, während die andere es unverändert ließ, **oder** (ii) es in der Basisregion eines **bestätigten** `IDENTISCHE_AENDERUNG`-Zertifikats liegt. Jedes A- und B-Vorkommen ist zugeordnet.
    6. **Keine erfundenen Zeilen:** Jedes Ausgabe-Vorkommen hat mindestens ein Urbild.
  - **Zertifikate unabhängig nachprüfen:** `verify` berechnet für jedes `IDENTISCHE_AENDERUNG`-Zertifikat selbst nach, dass die Grenzanker in allen Sequenzen eindeutig sind, dass die Regionen genau zwischen ihnen liegen und dass die Bytes gleich sind. Das Zertifikat des Mergers wird also nicht einfach geglaubt. `R1`/`R2` bleiben eine getrennte Kategorie.
  - **Mehrdeutigkeit:** Lässt sich eine Region nicht eindeutig begrenzen (wiederholte Zeilen, Leerzeilen) oder ein Zertifikat nicht bestätigen → **Konflikt** statt erzwungener Zusammenlegung.
  - Ein Verstoß stuft das Ergebnis zum Konflikt herab. Ergebnisse mit Konflikt werden über Ergebnis ∪ Hunks geprüft.

### Konflikte (`merge/conflicts.py`)

- **Persistente Quelle:**
  - Allein die Konfliktdateien im Vault. Solange eine existiert, ist der Konflikt offen.
  - Sidecars ergänzen das nur, solange ihre Konfliktdatei mit `konflikt_sha1` existiert; veraltete Sidecars werden aufgeräumt.
  - **Resolve-Ops verfallen nicht wegen eines abweichenden Hashes** (siehe Auflösungsprotokoll).
  - Ein Marker `…MWENTSCHIEDEN` im Namen kennzeichnet eine bereits entschiedene Version: nie Auto-Merge.
- **Zuordnung:**
  - Segment-Regex `\.sync-conflict-(\d{8})-(\d{6})-([A-Z0-9]+)` (Syncthing setzt es vor die Endung).
  - **Hauptdatei = Name ohne *alle* Segmente**, im selben Ordner. Das Ergebnis enthält per Konstruktion kein Segment mehr. Deshalb wird **eine Konfliktdatei nie als Hauptdatei behandelt**.
  - Nicht-`.md` gehen die App nichts an (`GRENZE`).
  - **Verschachtelte Konfliktdateien** (≥2 Segmente) werden als weitere Version der echten Hauptdatei angezeigt, aber **immer nur manuell** aufgelöst.
- **Eigene Konfliktdateien (kollisionssicher):**
  - Name: `<stem>.sync-conflict-<YYYYMMDD>-<HHMMSS>-MERKWEISER<8 base32>.md`.
  - Sie werden **exklusiv angelegt**; bei einer Kollision gibt es einen neuen Zufallsteil. Eine ältere Konfliktversion kann so nie überschrieben werden.
  - Erkennung als „eigen“ über das Präfix `MERKWEISER`. Syncthing-IDs haben 7 Zeichen, daher gibt es keine Verwechslung.
- **Sidecar (je Konfliktdatei, nicht je Hauptdatei):**
  - Pfad `conflicts/<sha1(konflikt-relpath ohne Marker)>.json`. Er bleibt stabil, wenn der Marker gesetzt wird.
  - Konfliktdateien aus Schritt 5/6 des Tausch-Protokolls bekommen ein Sidecar mit `base_sha1 = E`, also eine verlässliche Basis.
  - Inhalt `{konflikt_relpath, konflikt_sha1, haupt_relpath, base_sha1, erstellt}`. Die Basisversion liegt in der Historie und ist geschützt.
  - Mehrere offene eigene Konflikte einer Hauptdatei haben getrennte Sidecars.
  - Gültig nur, solange die Konfliktdatei mit `konflikt_sha1` existiert. Fehlt das Sidecar → Behandlung wie ein Syncthing-Konflikt.
- **Reihenfolge mehrerer Konfliktdateien:**
  - Nach dem äußersten Zeitstempel im Namen. `GRENZE`: Das ist nur Anzeige- und Abarbeitungsreihenfolge; Geräteuhren können abweichen, und es wird keine Kausalität behauptet.
  - Sie werden nacheinander verarbeitet. Beim ersten Konflikt stoppt die Kette.
- **`MAIN_DELETED`** (die Hauptdatei fehlt):
  - Es werden **alle** Konfliktversionen gelistet (sortiert wie oben).
  - Der Nutzer wählt **genau eine** als Wiederherstellungsgrundlage oder „alle verwerfen“ (alle ins Backup).
  - Nach der Wiederherstellung werden die übrigen zu normalen Konflikten gegen die neue Hauptdatei, aber **nur manuell** (Feld `nur_manuell` der Resolve-Op).
  - Es werden **nie** automatisch mehrere Konfliktstände zusammengefasst.
- **Sichtbarkeit:**
  - Der Konflikt-Zähler ist immer sichtbar; betroffene Dateien zeigen ein Banner.
  - Konfliktdateien werden nicht in die Todo-Übersicht gemischt.
  - **Jeder Auto-Merge wird protokolliert** (Backup-Op `automerge`) und erscheint in der Liste „Automatisch zusammengeführt“ mit „Rückgängig“ (Wiederherstellung aus dem Backup per `safe_write`).
- **Hunk-Optionen:**
  - A, B, Bearbeitet (vorbefüllt mit dem Vorschlag).
  - **Beide** = rohe Textverkettung A, dann B, nur wenn beide Seiten nicht leer und verschieden sind.
  - Bei Löschung gegen Änderung gibt es nur A, B oder Bearbeitet. Identische Seiten sind kein Hunk. Benachbarte Hunks sind bereits verschmolzen.

### Auflösungsprotokoll: Resolve-Op mit Vault-Marker (Garantien 4 und 5)

**Invariante:** Eine explizit gewählte Konfliktentscheidung wird durch Absturz, Neustart oder Scan nicht unbemerkt rückgängig gemacht. Ohne Schutz würde nach „A gewählt, Absturz vor dem Entfernen von B“ der nächste Union-Merge B wieder einführen.

**Marker:** Die Gerätekennung der Konfliktdatei bekommt den Zusatz `MWENTSCHIEDEN`.

- Beispiel: `X.sync-conflict-20261008-101500-ABCDEFG.md` → `X.sync-conflict-20261008-101500-ABCDEFGMWENTSCHIEDEN.md`.
- Die Segment-Regex `[A-Z0-9]+` passt weiterhin, die Zuordnung zur Hauptdatei ändert sich nicht.
- Erkannt wird der Marker am Suffix der Kennung. Das Sidecar ist über den relpath **ohne** Marker verschlüsselt.
- Eine markierte Datei ist weiterhin ein **offener Konflikt**. Sie wird aber **nie automatisch gemerged** und erscheint als „Entscheidung in Arbeit“ bzw. „unterbrochen“.
- Über Syncthing ist der Marker auch auf anderen Geräten sichtbar. Dort gilt er als „Entscheidung auf einem anderen Gerät in Arbeit“: nur manuell, mit dem Hinweis, erst dort abzuschließen.

**Ablauf:**

1. **Planen:** Hauptdatei-Snapshot `M0` (oder ABSENT), Konfliktdatei `C` mit Snapshot `C0`, Nutzerwahl je Hunk → Ergebnis `R`.
2. **Resolve-Op PREPARED** (Write-Ahead):
   - Manifest `{art: resolve, haupt, konflikt C, marker Cm, haupt_sha1_vorher, konflikt_sha1, ergebnis_sha1, entscheidung je Hunk, nur_manuell: […]}`.
   - Die Bytes `M0`, `C0` und `R` werden persistiert und geprüft. Ab hier existiert die Entscheidung dauerhaft in den App-Daten.
3. **MARKED:**
   - `C → Cm` per Rename ohne Überschreiben. Das ist nach L erlaubt, weil der Inhalt im Vault bleibt.
   - Danach `Cm` gegen `C0` hashen. Bei einer Abweichung wird `Cm` ohne Überschreiben nach `C` zurückbenannt; die Op wird INTERRUPTED, die Auflösung neu berechnet und neu angezeigt.
4. **MAIN_WRITTEN:** Unter-Op `safe_write(haupt, M0 → R)`.
   - Bei `StaleTargetError` oder Race-Konflikt → `Cm` zurück nach `C` (ohne Überschreiben; ist `C` belegt, bleibt `Cm`). Die Op wird INTERRUPTED und die Auflösung neu angezeigt.
5. **REMOVED:** Unter-Op `safe_remove(Cm, C0)`. Hat sich `Cm` verändert → es wird nicht gelöscht, die Op wird INTERRUPTED (siehe Tabelle).
6. **DONE:** Erst jetzt gilt der Konflikt als persistent gelöst. Das Op-Verzeichnis bleibt als Backup.

**Wiederherstellung** (läuft **nach** der Tausch-Ebene, die bereits jede unvollständige Unter-Op in einen definierten Zustand gebracht hat, und **vor** dem Scan bzw. Auto-Merge):

| Fall | Plattenzustand | Aktion |
|---|---|---|
| a | Op PREPARED, `C = C0` unmarkiert, Haupt = `M0` | Ab Schritt 3 fortsetzen. Die Entscheidung ist persistiert und bleibt gültig. |
| b | `Cm = C0`, Haupt = `M0` (die Unter-Op `safe_write` war abgebrochen bzw. ABORTED) | Ab Schritt 4 fortsetzen |
| c | Die Unter-Op `safe_write` ist CONFLICTED (Race während des Haupt-Writes) | INTERRUPTED. `Cm` bleibt markiert, also nur manuell. Die neue Konfliktlage wird mit der früheren Wahl als Vorschlag angezeigt. |
| d | Haupt = `R`, `Cm = C0` vorhanden | Ab Schritt 5 fortsetzen |
| e | Haupt = `R`, weder `Cm` noch `C` vorhanden | Ist die Unter-Op `safe_remove` DONE → DONE. Ist sie unvollständig, hat die Tausch-Ebene sie bereits abgeschlossen → DONE. Fehlt die Unter-Op (die Konfliktdatei wurde extern entfernt) → DONE mit einem Hinweis im Protokoll. Die Entscheidung ist angewendet, deshalb ist das korrekt. |
| f | Haupt = `R`, `C` oder `Cm` vorhanden mit **≠ `C0`** | Die Entscheidung ist angewendet → Op DONE. Die veränderte Konfliktdatei wird **nie gelöscht**. Sie bleibt ein manueller Konflikt mit dem Hinweis „deine frühere Wahl: …“. |
| g | Haupt = `M0`, `C`/`Cm` mit **≠ `C0`** | INTERRUPTED. Nichts wird gelöscht oder automatisch gemerged. Der Konflikt wird manuell angezeigt, die frühere Wahl als vorausgewählter Vorschlag. |
| h | Haupt **extern verändert** (weder `M0` noch `R`) | INTERRUPTED. Der Konflikt bleibt (markiert, also nur manuell), die frühere Wahl wird als Vorschlag gegen den neuen Stand angezeigt. Es wird nie automatisch etwas angewendet. |
| i | **Weder `C` noch `Cm` vorhanden**, Haupt = `M0` | Die Konfliktdatei wurde extern entfernt, **bevor** die Entscheidung angewendet war. Ein Fehlen beweist keinen Abschluss. → INTERRUPTED mit dem Hinweis „Konfliktdatei wurde extern entfernt – deine Entscheidung ist nicht angewendet“ und **„Trotzdem anwenden“** (normales `safe_write` mit Guard, `R` aus dem Op-Verzeichnis). |
| j | Weder `C` noch `Cm` vorhanden, Haupt weder `M0` noch `R` (oder fehlt) | INTERRUPTED mit Hinweis. Die frühere Entscheidung und alle Bytes stehen im Op-Verzeichnis zur Ansicht und zur manuellen Übernahme bereit. Nichts passiert automatisch. |
| k | **App-Daten fehlen oder sind beschädigt** (kein Op-Verzeichnis, Manifest nicht lesbar) | Ist ein **Marker `Cm` im Vault** vorhanden → „Eine frühere Entscheidung zu dieser Konfliktversion wurde unterbrochen und ist **nicht rekonstruierbar** – bitte erneut entscheiden“. Nie Auto-Merge. Ohne Marker wurde die Hauptdatei noch nicht geschrieben (der Marker liegt *vor* dem Haupt-Write), es wurde also nichts angewendet und ein normaler Konflikt ist korrekt. Verwaiste `.mw-*` → Zeile 11 der Tausch-Tabelle. |

**Regeln:**

- Für eine Konfliktdatei mit unvollständiger Resolve-Op **oder** mit Marker läuft **nie** ein Auto-Merge.
- **Sidecars** verfallen, sobald ihre Konfliktdatei nicht mehr `konflikt_sha1` entspricht.
- **Resolve-Ops verfallen nicht wegen eines abweichenden Hashes.** Sie bleiben INTERRUPTED und dokumentieren die frühere Entscheidung, bis der Konflikt manuell gelöst ist **oder** der Nutzer den Hinweis bestätigt. Erst dann gelten sie als „geklärt“ und unterliegen der normalen Aufbewahrung.
- Technische Metadaten werden nur bei geklärtem Zustand entfernt (DONE, ABORTED oder bestätigt INTERRUPTED).
- **`MAIN_DELETED`:** Die Wiederherstellung aus Version k ist eine Resolve-Op mit `M0 = ABSENT`. Die übrigen Konfliktversionen werden in `nur_manuell` aufgenommen.

### Beobachtungs-Historie (`history.py`)

Sie ersetzt die einzelne Schattenkopie (Begründung siehe erstes Audit). Die Grundidee „Basis je Gerät außerhalb des Vaults“ bleibt.

- **Einträge** sind unveränderlich und dedupliziert: `<sha1>.md`.
- **Index** pro Eintrag: `{sha1, first_seen, last_seen, ersetzt_seit | null}`.
- **Scan bzw. Lesen** hängt neue Versionen an und aktualisiert nur Metadaten (`last_seen`; bei der vorherigen aktuellen Version wird `ersetzt_seit` gesetzt; bei einer gelöschten Datei bekommt die letzte Version `ersetzt_seit`). **Er überschreibt oder löscht nie einen Eintrag.**
- **Aufbewahrung „30 Tage“ bezieht sich auf `ersetzt_seit`**, also darauf, wie lange eine Version schon *veraltet* ist. Nicht auf `last_seen`, damit tägliches Lesen alte Versionen nicht künstlich am Leben hält.
  - Die aktuelle Version wird nie gelöscht.
  - Die neuesten 5 Versionen je Datei bleiben immer.
  - Versionen, die Sidecars oder Journale offener Konflikte referenzieren (`base_sha1`, `haupt_sha1_vorher`, `ergebnis_sha1`), bleiben ebenfalls.
- **Wofür:** nur für Vorschläge. Kandidatenbasis ist die neueste Version mit `last_seen` vor dem Zeitstempel im Konfliktnamen, die sich von A und B unterscheidet. `GRENZE`: Das ist eine **reine Heuristik** über lokale Beobachtungszeiten und unsynchronisierte Geräteuhren. Sie behauptet keine Kausalität und wird **nie** für einen Auto-Merge verwendet.
- Ein fehlender Eintrag nach einem Absturz → nur schwächere Vorschläge.

### Backups (`ops.py`)

- **Backups sind abgeschlossene Op-Verzeichnisse** (`vaults/<vault-id>/ops/<op-id>/`). Es gibt kein zweites Modell.
- **Was:** die persistierten Bytes jeder Op, also vorher, neu, verdrängt (als *Kopie*), Konflikt und Ergebnis.
- **Wo:** unveränderlich nach dem Schreiben, kollisionsfrei (siehe `op-id`), **nie im Vault**. Weil Backups nur Kopien sind, kann ein offenes fremdes Handle sie nicht verändern.
- **`manifest.json`** (nur Plan, kein Fortschritt; der steht in `state.json`): `{op_id, art (write|automerge|resolve|remove|move|recover|marker), eltern_op, erstellt (UTC), dateien: [{relpath, rolle (vorher|verdraengt|konflikt|ergebnis), sha1}], konflikt_refs: [{konflikt_relpath, konflikt_sha1}]}`.
- **Aufbewahrung (30 Tage):** Eine Op wird beim Start nur gelöscht, wenn sie älter ist **und** keine ihrer `konflikt_refs` auf eine aktuell existierende Konfliktdatei zeigt **und** keine unvollständige oder unbestätigt INTERRUPTED-Op sie referenziert. Unvollständige Ops werden nie gelöscht, egal wie alt sie sind. Die Verknüpfung ist damit explizit und aus Vault + Manifesten rekonstruierbar.
- **Backup-Fehler** → die Operation wird abgebrochen, nichts geschrieben, die UI meldet den Fehler.

### Watcher (`watch.py`)

- `poll(prev_state) → (Änderungen, new_state)` mit `{pfad: (mtime_ns, size)}`.
- **Er meldet nur Unterschiede zwischen zwei Beobachtungen**, keine Garantie für Zwischenstände. Maßgeblich ist der aktuelle Plattenstand.
- Die Korrektheit hängt allein an den Guards bzw. am Tausch-Protokoll.
- Desktop pollt über `after`; Mobile über Lifecycle-Wechsel und Timer.

### Suche (`query.py`)

- `Filter(text, von, bis, tags, tag_modus=UND|ODER, projekt, status, dringend)`:
  - **Verschiedene Filterarten werden UND-verknüpft.** Ein leeres Feld bedeutet keine Einschränkung.
  - `tags` werden gegen die **effektiven** Tags geprüft (inkl. Vererbung). Standard ist UND, umschaltbar auf ODER.
  - `projekt` wird gegen die effektiven Projekt-Tags geprüft.
  - `status` (offen/erledigt/alle): Ist er gesetzt, kommen nur Todos in Frage. `[-]` und andere Status gelten nicht als Todo.
  - `dringend` (ja/nein/egal) bezieht sich auf Todos.
  - `text`: `TextQuery(muster, modus)`, **im Core definiert und auf beiden Plattformen identisch**. `TEILSTRING` (Standard) vergleicht per `casefold`, also ohne Groß-/Kleinschreibung. `REGEX` (ein expliziter Modus-Schalter auf Desktop **und** Mobile) nutzt `re.IGNORECASE`; ein ungültiges Muster → Fehleranzeige, keine Filterung. Die UIs reichen nur `muster` und `modus` durch.
  - `von`/`bis`: das Datum der Tagesdatei, inklusiv.
- Treffer werden auf Knoten-Ebene mit Kontext geliefert. Cache nur im Speicher.

### App-Schicht (`merkweiser/app/`)

`NotesService` bleibt die einzige UI-Fassade:

- Ansichten: `day(date)` (inkl. Dubletten und Encoding-Hinweisen), `todos(filter)`, `search(filter)`, `conflicts()` (inkl. `MAIN_DELETED`, verschachtelter Fälle und Auto-Merge-Protokoll).
- Aktionen: alle Edit-Ops, `move_todo` (→ `MoveResult`), `resolve_conflict`, `undo_automerge`, `rescan()`.
- Settings als JSON in den App-Daten: Ordner, Namensmuster, Projekt-Präfix, Poll-Intervall, Aufbewahrung (30 Tage).

### Desktop (`merkweiser/desktop/`, bw-gui)

- `MainWindow(BwBaseWindow)`: Datumsnavigation (Treeview), Konflikt-Zähler, Modi **Tag / Todos / Suche / Konflikte**.
- **Tag:** strukturierte Ansicht. „Roh bearbeiten“ über `WrappedTextField` → `replace_note_text`. Banner bei Konflikt, Markierung bei Dubletten bzw. Encoding.
- **Todos:** Suchfeld mit Modus-Schalter Teilstring/Regex (im Regex-Modus `RegexEntryField`), `Switch`es (offen/erledigt/dringend, **UND/ODER für Tags**), Tag/Projekt-Auswahl, Zeitraum. Projekte zeigen „explizit“ bzw. „geerbt“.
- **Konflikte:**
  - Hunks nebeneinander, Vorschlag vorausgewählt, „Beide“ nur, wo definiert.
  - Dialoge für `MAIN_DELETED` und `MoveResult.INCOMPLETE`.
  - Liste „Automatisch zusammengeführt“ mit Rückgängig.
- **Shortcuts:** zentral über `UiIntent`, `KeybindingRegistry`, `WindowShortcutBinder` und HSM-Contract, ohne `bind_all`.
  - Belegung: Strg+N, Leertaste, Strg+U, Strg+P, Strg+M (Datum über `TextPromptDialogService`), Strg+F, F5.
- **Einstellungen:** `SettingsDialogOrchestrator` + „Notizordner wählen…“ (`FileDialogService.askdirectory`), solange es kein Pfadfeld gibt.
- **Polling:** `after`.
- **bw-gui** wird nur nach S3 und über einen eigenen Teilplan mit Rückfrage erweitert.

### Mobile (`merkweiser/mobile/`, Flet 0.86.5 gepinnt, solange der Android-Ansatz aus S1 gilt)

- **Ansichten:** Heute, Todos, Suche (mit demselben Modus-Schalter Teilstring/Regex wie am Desktop), Konflikte, Einstellungen. `ft.SafeArea`, Scrollen auf `ft.View`, Zurück-Taste über `_on_view_pop`.
- **`platform/`:** `android_storage.py` (aus namenfit-mobile; nie `Path.home()`) und `folder_access.py` (Ordnerwahl, Berechtigung).
- **Polling:** bei Lifecycle-Wechseln und per Timer.

---

## Umsetzungsschritte (jeweils ein eigener Commit auf main, Docs im selben Commit)

0. **Spikes (Go/No-Go, Wegwerfcode im Scratchpad, nur synthetische Dateien):**
   - **S1 Android mit Flet 0.86.5:**
     - Konfiguration: `MANAGE_EXTERNAL_STORAGE` (Manifest, Anfrage zur Laufzeit, Paket in `project.dependencies`).
     - Im Syncthing-Testordner: listen, lesen, schreiben, `os.replace`; Syncthing überträgt die Änderung.
     - **Zusätzlich die Tausch-Primitive auf Shared Storage:** atomarer Rename, `os.link`, `renameat2(RENAME_NOREPLACE)`, `O_EXCL`. Das Ergebnis füllt die Android-Zeilen der Plattform-Tabelle; daraus folgt „voll“, „`A1`“ oder „No-Go → S1b“.
     - **Schreibweise von Obsidian Mobile** feststellen: öffnen–schreiben–schließen oder offenes Handle? (`/proc/<pid>/fd` bzw. strace, soweit möglich; sonst ein Testszenario mit einer Speicherung in der Quarantäne.)
     - Abbruchkriterium: Lesen, Schreiben, Rename oder Syncthing-Übernahme fehlt. Dann sofort **S1b** mit einem anderen Framework (zuerst BeeWare/Briefcase, sonst Kivy über WSL).
     - Scheitert auch S1b → Android bleibt `BAUSTELLE`; Core und Desktop werden trotzdem fertig.
   - **S2:** `flet build apk` aus `src/`. Der Core ist importierbar, das Desktop-Paket stört nicht. Analog für S1b.
   - **S3:** bw-gui `Treeview` mit Checkbox-Spalte, Guards, `WrappedTextField`.
   - **S4 Tausch-Protokoll unter Windows mit laufendem Obsidian und Syncthing:**
     - **Handle-Lebensdauer:** Hält Obsidian Notizdateien zwischen Speichervorgängen offen? (Sysinternals `handle.exe`/Process Monitor beim Tippen, Speichern und Tab-Wechsel.) Mit welchen Rechten und Freigaben (Schreiben? `FILE_SHARE_DELETE`?)
     - **Schreibsperre:** Unser Handle mit verweigerter Schreib-Freigabe, während Obsidian speichern will. Wiederholt Obsidian später, zeigt es einen Fehler, oder **verliert es den Editorinhalt**?
     - **Rename** einer in Obsidian geöffneten Notiz (Sharing-Violation?) und Obsidians Reaktion auf das Mikrosekunden-Verschwinden (schließt sich der Tab, geht ein Entwurf verloren?).
     - **Kritische Zeitpunkte** gezielt mit Haltepunkten im Protokoll erzeugen: eine externe Speicherung (a) vor dem Wegbenennen, (b) zwischen Wegbenennen und Installieren, (c) nach dem Installieren vor der Kopie von `D`, (d) während der Quarantäne, (e) nach der Quarantäne. Für jeden Zeitpunkt festhalten, wo die Änderung landet.
     - **Syncthing:** Löschungs-Events beim Mikrosekunden-Verschwinden? Verhalten bei `P`, das nach einem simulierten Absturz minutenlang fehlt (`W4`)? Greift `.stignore` für `.*.mw-*`?
     - **Ergebnis:** `W1`, `W2` und `W4` sowie die Windows-Zeile der Plattform-Tabelle **mit Belegen** in `ARCHITEKTUR.md`.
     - **Rückfrage vor der Umsetzung**, falls (1) Obsidians Reaktion auf Schreibsperre oder Rename inakzeptabel ist (z. B. Verlust des Editorinhalts oder geschlossener Tab mit Entwurf) **oder** (2) Obsidian bzw. Syncthing eine Schreibweise zeigen, die nicht unter den Geltungsbereich von Garantie 2 fällt.
   - Alle Ergebnisse kommen in `docs/ARCHITEKTUR.md`.
1. **Gerüst:**
   - `pyproject.toml`, `AGENTS.md`, `bw_libs/`.
   - `docs/KONZEPT.md` (bereinigt plus Entscheidungen), `docs/FORMAT.md` (Grammatik, Fences, Tabs, Encoding), `docs/ARCHITEKTUR.md` (Wahrheitsmodell, Garantien, Protokolle, App-Daten-Layout).
   - `DEVELOPMENT_LOG.md`, `CHANGELOG.md`.
2. **Core lesen:** `source` (inkl. Encoding), `blocks`, `lexer`, `outline`, `inline`, `tags`, `vault`, `textfile` (lesen), `ports/clock`. Dazu Fixture-Korpus und Roundtrip-Tests.
3. **Core schreiben:** `textfile`-Primitive inkl. Selbsttest je Plattform, App-Daten-Layout und Vault-ID, **Op-Verzeichnisse** (Manifest nur als Plan, State als einzige Fortschrittsquelle, Betriebssystem-Lock + Epoche, Heartbeat nur zur Anzeige, `op-id`), `Clock.monotonic`, `history` (Anhängen), `safe_write`/`safe_remove` (Ersetzen-Pfad, **Create-only-Pfad**, `O_EXCL`-Fallback, Quarantäne mit Prüfung von `P`), **Wiederherstellung der Tausch-Ebene und feste Startreihenfolge**, `edits`, `move` (als idempotente Move-Op).
4. **Suche/Filter:** `query`.
5. **Merge und Konflikte:** `align`, `diff3`, `union`, `verify`, `conflicts` (Zuordnung inkl. Verschachtelung und Marker, eigene Konfliktnamen, Sidecars, **Resolve-Op mit Marker und Wiederherstellungstabelle**, `MAIN_DELETED`, Auto-Merge-Protokoll), `watch`, Aufbewahrung für Historie und Backups.
6. **App-Schicht:** `NotesService` und Settings.
7. **Desktop-UI** (Tag, Todos, Suche, Konflikte, Einstellungen).
8. **Mobile-UI und APK** mit dem Framework aus S1/S1b, dazu `docs/kurzanleitung.md` (inkl. `.stignore`-Empfehlung).
9. **Abschluss:**
   - CHANGELOG 0.1.0.
   - ARCHITEKTUR mit allen `GRENZE`/`BAUSTELLE`; Prüfung: `rg -n "\b(GRENZE|BAUSTELLE)\b"`.
   - Wunschliste `7thVault/Projekte/Wunschliste.md`.

**Konventionen:**

- ~300 Zeilen pro Datei sind ein Richtwert bzw. Warnsignal. Keine künstlichen `*_helpers`/`*_utils`; Ausnahmen werden mit `GRENZE(dateigroesse)` markiert.
- Docstrings im Google-Stil für Methoden nach Projektkonvention. Sie erklären Zweck, Invarianten und Fehlerfälle.
- Docs auf Deutsch, keine Co-Authored-By-Zeile, `GRENZE`/`BAUSTELLE` einheitlich.

---

## Verifikation (pytest, nur synthetische Fixtures, nur `FakeClock`)

- **Roundtrip** byte-identisch bei:
  - CRLF, LF, gemischten Zeilenenden; mit und ohne Schluss-Newline.
  - UTF-8 mit und ohne BOM.
  - Frontmatter; Code-Fences inkl. **längerer Fences mit kürzeren darin** und unvollständiger Fences.
  - Setext-`---`/`===`; `#tag` gegen Überschrift; Tags in URLs, Code und Wikilinks.
  - `[-]`, `[X]`; Bilder, Links, Embeds; **gemischte Tabs/Leerzeichen**; Tabellen, Zitate.
- **Encoding:** ungültiges UTF-8 und UTF-16-BOM → nur lesbar, jede Schreib-Op verweigert, Datei unverändert.
- **Minimal-Diff:**
  - Strukturierte Ops ändern nur die erwarteten Zeilen; `toggle_done` lässt `[X]` stehen.
  - `set_project` ersetzt nur Projekt-Tokens.
  - `replace_note_text` ändert genau die Notiz-Spanne.
- **Grammatik und Vererbung:**
  - Erläuterungsabsatz; neues Thema nach einer Liste; Überschriften-Bereiche.
  - Eltern-Punkt bei Tab-Stopps (Tab gegen 2/4 Leerzeichen); Punkte ohne Eltern; Listen vor dem ersten Thema.
  - Konzeptbeispiel `#uni`.
- **Ziele:**
  - Verschoben und eindeutig → Treffer. **Identische Todos** → `StaleTargetError`.
  - `replace_note_text` nach eingefügtem bzw. entferntem Trenner, geteilter Notiz oder mehreren Kandidaten → eigene Konfliktdatei mit Sidecar-Basis, nie Raten.
- **Schreibprotokoll** (mit Fault-Injection-Hooks in `textfile`):
  - Externer Write zwischen Planung und Guard → neu planen bzw. `StaleTargetError`.
  - Externer Write **zwischen Guard und Wegbenennen** → die fremde Fassung wird wieder Hauptdatei, die eigene wird Konfliktdatei.
  - Externes Neuanlegen **zwischen Wegbenennen und Installieren** → die eigene Fassung wird Konfliktdatei.
  - **Prozessabbruch an jeder Protokollgrenze** von `safe_write` und `safe_remove`. Fault-Injection wirft an jeder benannten Grenze `SimulatedCrash`: während und nach PREPARED, nach dem Anlegen bzw. Schreiben bzw. `fsync` von `T`, nach DISPLACED, nach INSTALLED, nach der Kopie von `D`, während des Rücktauschs, in der Quarantäne. Danach wird eine **neue Instanz** gestartet, die die feste Startreihenfolge durchläuft: zuerst die Wiederherstellung, dann Scan und Auto-Merge.
  - **Abbruch während der Wiederherstellung** (geschachtelte Fault-Injection) → erneuter Start führt zum selben Endzustand.
  - **Prüfinvariante nach jedem Szenario:** Jeder Stand, der je Hauptdatei war oder extern geschrieben wurde (`E`, `N`, `X`), steht in `P` oder in einer Konfliktdatei im Vault. `E` darf nur dann allein im Op-Verzeichnis liegen, wenn `N` es legitim ersetzt hat. Ein nicht angewendetes `N` erscheint als Hinweis mit „Wiederholen“.
  - Neustart mit verbliebenen `.mw-*.tmp`/`.old` mit und ohne Op-Verzeichnis → Wiederherstellung bzw. sichtbare Konfliktdateien, **keine Löschung nach Alter**.
  - Hauptdatei fehlt, `D` existiert → wird wiederhergestellt, **nie** als `MAIN_DELETED` gewertet.
  - Externe Änderung an `D` vor der Kopie, nach der Kopie, während der Quarantäne → Konfliktdatei. Backups bleiben unverändert (Hash geprüft). Nach der Quarantäne: dokumentierter `W1`-Test (POSIX).
  - Windows: Eine fremde Datei ist zum Schreiben geöffnet → das Protokoll wartet bzw. bricht ab, nichts geändert.
  - **Create-only:** `E = ABSENT` legt eine neue Tagesdatei erfolgreich an. Entsteht `P` extern vor der Installation, wird es nicht überschrieben, und `N` wird Konfliktdatei; es gibt keinen Wiederholungsversuch auf `P`. Abbruch in TMP_READY bzw. INSTALLING → Zeile 7a.
  - **`O_EXCL`-Fallback** (simuliert): überschreibt nie. Abbruch mit partiellem `P` in INSTALLING (Identität unbekannt) → `A2`-Pfad. Abbruch in P_CREATED mit passender Identität und Präfix → neu installiert. Externe Ersetzung bzw. In-place-Änderung von `P` während des Schreibens → `P` bleibt, `N` wird Konfliktdatei. Statusanzeige „eingeschränkt“.
  - **Quarantäne mit Prüfung von `P`:** `P` wird nach dem Installieren von `N` extern durch `X` ersetzt (Temp+Rename), während der Quarantäne und kurz vor deren Ende → `N` wird Konfliktdatei, `X` bleibt. `D = E` wird erst danach gelöscht. Abbruch nach der Ersetzung → Neustart mit `P = X`, `D = E`, `N` im Op-Verzeichnis → `N` sichtbar.
  - **Monotone Zeit:** Die Wanduhr springt während der Quarantäne vor bzw. zurück → keine vorzeitige Beendigung. Neustart → Quarantäne beginnt neu.
  - **Manifest/State:** Ein Manifest ohne `state.json` → ABORTED, Vault unberührt. Es gibt keinen Fortschritt im Manifest.
  - Backup-Fehler → nichts geschrieben.
  - Kollidierende Temp-, Op- und Konfliktnamen (`FakeClock` liefert dieselbe Sekunde) → nie überschrieben.
  - **Zwei Instanzen** gleichzeitig, auch bei gleichzeitiger Wiederherstellung derselben Op → nur der Lock-Halter handelt.
  - **Suspendierte erste Instanz** (Prozess angehalten per `SIGSTOP` bzw. Suspend; Heartbeat > 60 s alt) → die zweite Instanz übernimmt **nicht**. Wird die erste fortgesetzt, macht sie korrekt weiter.
  - **Fencing:** Die Epoche in `state.json` wird künstlich erhöht (simulierte Übernahme) → die alte Instanz bricht vor ihrem nächsten Zustandsübergang bzw. ihrer nächsten Vault-Operation ohne Wirkung ab.
  - Selbsttest „Lock wird nicht durchgesetzt“ (simuliert) → nur eine Instanz pro Vault.
- **Move:**
  - Quelle extern an anderer Stelle geändert → sauber.
  - Quelle im Block geändert → `INCOMPLETE`.
  - Ziel extern geändert → neu planen; Ziel nicht neu planbar → nichts geändert.
  - `AmbiguousDayFile`.
  - Simulierter Absturz an jeder Stelle → höchstens ein Duplikat.
  - **Absturz nach erfolgreichem Zielschreiben** → die Wiederherstellung setzt die Move-Op fort: kein zweites Anhängen, die Quelle wird nur mit exaktem Nachweis entfernt.
  - **Mehrfaches „Erneut versuchen“** bzw. erneutes Verschieben desselben Quellblocks → „vorhandenen Vorgang fortsetzen“, das Ziel wird nie vervielfacht.
  - **Zielblock extern verändert bzw. mehrfach vorhanden** → INCOMPLETE bleibt sichtbar, die Quelle bleibt unangetastet.
  - „Verschoben aus“ wird wiederverwendet; implizite Tags werden explizit ergänzt.
- **Merge:**
  - A/B/C automatisch.
  - Konkurrierende Einfügungen; identische Änderungen.
  - Löschung gegen Änderung → Konflikt.
  - Wiederholte Zeilen und Leerzeilen ergeben keinen falschen sauberen Merge.
  - R1 (`[ ]` gegen `[x]`/`[X]`); **R2 (`[x]` gegen `[X]` → Hauptdatei-Bytes)**.
  - Union bringt eine Löschung zurück (`GRENZE`-Test).
  - **Beide Seiten ändern dieselbe Basiszeile identisch** (`A,B` → `A,C` auf beiden Seiten) → einmal `C`, kein falscher Konflikt; das Basis-Vorkommen `B` ist durch das Zertifikat abgedeckt.
  - **Identische Einfügung beider Seiten am selben Anker** → einmal im Ergebnis, kein falscher Konflikt.
  - **Verschiedene Einfügungen am selben Anker** → beide erhalten, Hauptdatei zuerst.
  - **Eine Seite mit zwei identischen Vorkommen, die andere mit einem** → die beiden Vorkommen fallen nicht zusammen.
  - Wiederholte Zeilen und Leerzeilen als mögliche Anker → keine mehrdeutige Zuordnung, sondern ein Konflikt.
  - **Gleicher Inhalt an unterschiedlichen Positionen** → keine falsche Viele-zu-eins-Zuordnung.
  - **Manipulierte Zuordnungen bzw. Zertifikate** (injizierter fehlerhafter Merger) → `verify` stuft zum Konflikt herab (Union- und diff3-Modus).
  - `R1`/`R2` werden getrennt von identischen Änderungen protokolliert.
  - Die Historienbasis erzeugt nur einen Vorschlag.
- **Konfliktauflösung:**
  - Wahl A, B, Beide oder Bearbeitet, jeweils mit **Absturz** vor dem Marker, nach dem Marker, **während** `safe_write` (jede Tausch-Grenze), nach dem Hauptdatei-Write und vor bzw. während `safe_remove` → nach dem Neustart wird die gewählte Fassung zu Ende geführt, B wird **nicht** ungefragt wieder eingefügt.
  - Jede Zeile a–k der Wiederherstellungstabelle als eigener Test. Darunter: Konfliktdatei fehlt bei altem, neuem oder unbekanntem Hauptdateistand; Haupt- bzw. Konfliktdatei wird während der Wiederherstellung extern geändert.
  - **App-Daten gelöscht bzw. beschädigt** mit vorhandenem Marker → kein Auto-Merge, erneute Rückfrage. Ohne Marker → normaler Konflikt, weil noch nichts angewendet war.
  - **Konfliktdatei vor dem Entfernen geändert → nie gelöscht**, die frühere Wahl bleibt als Hinweis sichtbar.
  - Eine Resolve-Op mit abweichendem Hash bleibt INTERRUPTED, bis der Konflikt gelöst oder der Hinweis bestätigt ist.
  - Marker auf einem zweiten Gerät (per Kopie simuliert) → dort nur manuell.
  - Mehrere eigene Konflikte einer Hauptdatei: getrennte Sidecars, kollisionsfreie Namen.
  - Auto-Merge-Protokoll und Rückgängig.
- **Konfliktnamen:**
  - **Verschachtelte Konfliktdateien** → richtige Hauptdatei, nur manuell, eine Konfliktdatei ist nie Hauptdatei.
  - **Hauptdatei fehlt + mehrere Konfliktdateien** → genau eine wählen, Rest nur manuell, keine automatische Zusammenfassung.
- **Historie und Backups:**
  - **Zwei Vaults mit gleichem `relpath`** teilen keine Historie und keine Backups.
  - Aufbewahrung gemessen an `ersetzt_seit`; tägliches Lesen verlängert alte Versionen nicht.
  - Referenzen offener Konflikte schützen Historie und Backups vor dem Löschen.
  - Ein Scan überschreibt nie.
- **Suche:** UND/ODER bei Tags, effektive Tags und Projekte, leere Felder, `status` und `dringend` kombiniert, Datumsbereich inklusiv. **Teilstring- und Regex-Modus im Core, identische Golden-Tests für beide UIs** (dieselbe Anfrage ergibt auf Desktop und Mobile dieselben Treffer).
- **Watcher:** zwei Änderungen zwischen zwei Polls → nur der Endstand, Korrektheit bleibt.
- **Vault:** ganzer Dateiname, Dubletten, Schreibziel-Regel, Konfliktdateien sind keine Tagesdateien.
- **Desktop-E2E** im synthetischen Testordner:
  - Gleichzeitiges Ändern in Obsidian.
  - Konfliktdatei von Hand anlegen → Banner, Auflösung, Backup.
  - App während der Auflösung **und** während eines Tauschs beenden (Task-Kill) → nach dem Neustart läuft zuerst die Wiederherstellung, die Entscheidung bleibt erhalten, keine Datei fehlt.
  - S4-Szenarien als wiederholbares manuelles Protokoll.
- **Mobile-E2E:** APK mit synthetischem Syncthing-Ordner; auf beiden Geräten bearbeiten und den Konfliktfall durchspielen.
- `pytest` grün, Guard-Tests aus `bw_gui.testing` eingebunden.
