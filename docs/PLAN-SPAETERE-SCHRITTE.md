# Plan: Spätere Schritte W1–W6 (Merkweiser) – überarbeitete Fassung nach Review

> Status: **Fassung 2, freigegeben am 2026-10-22** (Fragerunden 1–7 + Review: Entscheidungen 1.1–1.8, Befunde R1–R2, Y1–Y12). Fortschritt: Tabelle in [PLAN.md](PLAN.md), Abschnitt „Spätere Schritte“.
> **Anpassung an die Nutzer-Commits vom 2026-10-22** (`f9ce64b`, `54ff155`, `c356fee`): Der Tab „Heute“ heißt jetzt **„Tag“** (Datum wählbar, beim Öffnen heute); die Suche zeigt ganze Notizen; Verschieben schreibt kein „Verschoben aus“ mehr. Unten ist „Heute“ deshalb durch den Tab „Tag“ ersetzt; die W1-Regel für die Suche gilt für Notizkarten (siehe W1).

## Context

Merkweiser (`a:\Code\merkweiser`) ist ein Monorepo aus Core, App-Schicht und Mobile-UI (Flet 0.86.5); die Desktop-UI (Schritt 7) ist zurückgestellt. Die App verwaltet Markdown-Tagesnotizen mit Todos, und der Vault (Obsidian + Syncthing) ist die einzige Wahrheit. Sechs Nutzerwünsche sollen umsetzungsreif geplant werden:

- **W1** dringende Todos zuerst
- **W2** Tag-Seite
- **W3** doppelte Notizen
- **W4** Navigation, Konflikte und Backups
- **W5** Benachrichtigung
- **W6** Arbeitszeit-Tracker

Danach folgen Schritt 7 und Schritt 9.

**Freigabekriterium:** Für jeden der folgenden Fälle ist klar, wie er vermieden oder in einen entscheidbaren Konflikt überführt wird:

- Datenverlust
- doppelte Zeitverbuchung
- destruktive Wiederaufnahme
- fehlerhafter YAML-Merge
- unvollständige Recovery

**Projektregeln** (Memory, unverändert):

- **Doku:** immer mitpflegen. CHANGELOG nur Sichtbares, DEVELOPMENT_LOG Internes, dazu ARCHITEKTUR und FORMAT.
- **Code:**
  - etwa 300 Codezeilen pro Datei; neue Funktionen in eigene Service-Module statt in `NotesService` (bereits 369 Zeilen)
  - `GRENZE:`/`BAUSTELLE:` setzen und mit `rg "BAUSTELLE|GRENZE"` prüfen
  - ausführliche Docstrings
  - GUI-Texte mit Umlauten
  - Flet-APIs gegen 0.86.5 verifizieren und hinter Adapter legen
- **Git:**
  - Commit je Teilschritt direkt auf main
  - Push mit `timeout 60` und `GIT_TERMINAL_PROMPT=0`
  - keine Attribution
- **Daten und Werkzeuge:**
  - nur synthetische Testdaten
  - Escape-Falle: `\n` in Heredocs vermeiden, Edit/Write nutzen
  - unverwandte Bugs melden
  - Features nie stillschweigend streichen

---

## Anforderungen (verbindlich; Fassung 1 + Präzisierungen)

### W1 – Dringende Todos zuerst (nur Anzeige)
- Dringend heißt `==…==`; erkannt über `inline.is_urgent` bzw. `Row.urgent`.
- Gilt in **Todos**, **Suche** und im Tab **Tag**. Im Tab Tag (und in der Suche, die ganze Notizen zeigt) wird innerhalb jeder Notiz sortiert; die **Datei wird nie umsortiert**.
- Die Sortierung ist **stabil**: Einträge gleicher Dringlichkeit behalten ihre Reihenfolge.
- In Bäumen wird **je Geschwistergruppe** sortiert; ein Teilbaum bleibt an seinem Elternpunkt.
- In der Suche stehen Notizkarten mit einem dringenden Treffer zuerst, sonst gilt die bisherige Reihenfolge (neueste zuerst). Gleiches gilt für die Tag-Seite (W2).
- In der Benachrichtigung (W5) stehen dringende Todos zuerst.

### W2 – Tag-Seite
- Tags sind **überall antippbar**, wo sie im Notiztext stehen.
- Antippen öffnet eine **eigene Ansicht mit Zurück**. Sie zeigt **ganze Notizen** mit dem Tag (Themen und Todos), keine Einzeltreffer, **neueste zuerst**, je Notiz nur einmal.
- Todos sind dort wie im Tab Tag bedienbar (gleiche Notizkarten wie in der Suche). Antippen des übrigen Todo-Texts öffnet weiterhin „Bearbeiten“.
- Basis ist die vorhandene Tag- und Query-Infrastruktur (`query.Filter(tags=…)`).

### W3 – Doppelte Notizen
- **Gleich** heißt: gleiche Zeilentexte **nach Normalisierung der Zeilenenden** (LF = CRLF), sonst keine Normalisierung. Das ersetzt „byte-gleich“.
- Gezählt werden nur Fundstellen in **≥ 2 verschiedenen Tagesdateien**. Das Alter ergibt sich aus dem Datum der Tagesdatei.
- Duplikate werden **immer gemeldet**: keine Ausnahme für kurze Notizen, keine Option „alle behalten“.
- **2 Fundstellen:** „Neuere behalten“ / „Ältere behalten“.
- **≥ 3 Fundstellen:** alle mit Datum anzeigen; genau eine wählen, Schnellwahl „Neueste“ / „Älteste“.
- Alle anderen Fundstellen löscht `delete_note`.
- Offene Duplikatgruppen zählen im Einstellungen-Badge mit.
- Wiederaufnahme nach einem Absturz: siehe **S3**.

### W4 – Navigation, Konflikte, Backups
- **Tabs:** **Tag | Todos | Suche | Zeit | Einstellungen**.
- **Einstellungen** hat die Unterseiten **Konflikte**, **Backups** und **Benachrichtigungen**.
- **Badge** am Einstellungen-Symbol zählt offene Konflikte, Duplikatgruppen und unterbrochene Vorgänge.
- Der Start-Hinweis „Konflikte vorhanden“ führt zur Konflikte-Seite.
- **Zustand je Tab (1.6):**
  - Jeder Tab hat seinen eigenen Unterseiten-Stapel. Ein Tabwechsel löscht die Stapel der anderen Tabs **nicht**.
  - Beispiel: In Todos eine Tag-Seite öffnen, zu Suche wechseln, zurück zu Todos: Die Tag-Seite steht noch da.
  - Android-Zurück geht innerhalb des aktuellen Tabs zurück.
- **Backups:**
  - nach Datei gruppiert, neueste zuerst
  - je Datei eine chronologische Liste der Änderungen mit Zeit, Art, Vergleich vorher/nachher und je einem „Rückgängig“
  - ausgeblendete Auto-Merges bleiben hier erreichbar
  - verdrängte externe Stände erscheinen als eigene Art
- **Rückgängig (1.4):**
  - nimmt **nur diese Änderung** zurück; spätere Änderungen bleiben erhalten (Rückwärts-diff3 auf den aktuellen Stand)
  - nicht eindeutig: eigene Konfliktdatei, die Entscheidung fällt im Konfliktbereich
  - Das Modell der Einzeländerung bleibt. Die UI zeigt aber, **welche Änderungen zusammengehören** (z. B. beide Dateien eines Moves), und nennt die Folgen eines teilweisen Rückgängigmachens. Es gibt **keine** Garantie, dass jede Einzeländerung isoliert gefahrlos ist.
- Die Sonderfälle Auto-Merge und Konfliktentscheidung bleiben abgedeckt (siehe Design W4).

### W5 – Benachrichtigungen (nur Android)
- **Einstellbar:**
  - an/aus
  - Uhrzeit (Standard 07:00)
  - **Eskalation** an/aus (Standard **an**)
  - **Urlaub bis** (Datum, einschließlich; leer = kein Urlaub)
- **Inhaltsbenachrichtigung:**
  - Nur für den **nächsten** Termin.
  - Inhalt: offene Todos der Tagesdatei **des Auslösetags** (verschobene Todos stehen seit `c356fee` ohne Kopfzeile direkt in der Zieldatei) plus offene dringende Todos **aller Tage**, dringende zuerst.
  - Stand ist der Moment der Planung.
  - Antippen öffnet den Tab **Tag** mit dem heutigen Datum.
  - **Ohne passende Todos keine Inhaltsbenachrichtigung.** Das sperrt **nicht** die neutralen Erinnerungen.
- **Folgetage** (App nicht wieder geöffnet):
  - **neutrale** Erinnerung „Öffne Merkweiser, um deine Todos zu sehen“, standardmäßig **eskalierend**
  - Vorplanung **Standard 14 Tage**, Maximum 30 (Begründung siehe Design W5)
- **Urlaub:** keine Benachrichtigungen; Zählung und Eskalation pausieren.
- **Technische Lage:** Flet 0.86.5 hat in der erkundeten Konfiguration **weder Benachrichtigungen noch Hintergrundausführung**. Darum gilt: Spike S5, dann der Fallback-Pfad.
- `GRENZE(Benachrichtigung)`: Änderungen nach dem Verlassen der App fehlen im bereits geplanten Inhalt.

### W6 – Arbeitszeit-Tracker (Tab „Zeit“)
- **Speicherung:**
  - im YAML-Frontmatter der Tagesdateien, flach und in ganzen Minuten: `zeit_<Tätigkeit>: <Minuten>`
  - Merkweiser ändert **nur `zeit_*` und `messung_*`**; alles andere bleibt byte-genau
  - fehlende Datei bzw. fehlendes Frontmatter wird angelegt
  - FORMAT: die Regel „Frontmatter wird nie verändert“ wird überall angepasst
- **Startstempel:**
  - `messung_start` (ISO mit Offset) und `messung_taetigkeit` bilden **einen Datensatz** (Y5)
  - steht in der Tagesdatei des Starttags
- **Stempel finden (1.7):**
  - Geprüft werden die Dateien des Übersichtszeitraums (Standard 7 Tage) beim App-Start und beim Wechsel in den Zeit-Tab.
  - Stempel **älter als 24 h** werden gelöscht, ohne Verbuchung und mit Hinweis, z. B. „Messung ‚Orga‘ seit Mo 08:15 war älter als 24 h und wurde verworfen“.
  - Die erste Wahl eines längeren Zeitraums löst **einmal je App-Sitzung** eine Suche über das ganze Archiv aus.
  - Die Bereinigung bezieht sich **nur auf tatsächlich geprüfte Dateien**.
- **Bedienung:**
  - Ein Knopf für Start und Stopp.
  - **Dauer:** wird aus den Zeitstempeln berechnet und **immer abgerundet**.
  - **Über Mitternacht:** wird je Tagesanteil abgerundet und der jeweiligen Tagesdatei zugerechnet. Die Tagesgrenze richtet sich nach der **lokalen Zeitzone des Geräts** (1.3).
  - **Tätigkeit wechseln:** Die laufende Messung endet jetzt, die neue beginnt jetzt.
  - **„Messung abbrechen“:** Endzeit wählen (mit Verbuchung) oder „Keine Zeit eintragen“ (nur der Stempel wird gelöscht).
- **Tätigkeiten:**
  - Die Liste ist app-intern, Standard „Orga“.
  - Namen, die nur in Dateien vorkommen, erscheinen in der Übersicht.
  - Reihenfolge nach der Minutensumme der letzten 7 Tage, bei Gleichstand bzw. ohne Nutzung alphabetisch.
- **Umbenennen:**
  - wirkt auf alle Tagesdateien und aktive Stempel
  - existiert der Name schon, wird nach Rückfrage **zusammengeführt** (Minuten je Tag addiert)
- **Löschen:** behält alle Zeiten; nicht möglich bei aktiver Messung.
- **Namensregel:** sichere Allowlist (1.8 / R2).
- **Übersicht:**
  - 7 Tage, wählbar 7/14/30
  - je Tag eine Zeile mit Tätigkeiten und h:mm, darunter Summen je Tätigkeit und gesamt
  - laufende Messung als „Orga läuft seit 08:15 (1:23)“, etwa minütlich neu berechnet (Y12); gespeichert wird nur der Stempel
- **Sync-Konflikte:**
  - Bei **unterschiedlichen Minuten** gewinnt automatisch das **Maximum**.
  - **Zwei verschiedene Stempel** → Nachfrage:
    1. Nur der spätere zählt (immer angeboten).
    2. Der frühere zählt (nur bei **gleicher** Tätigkeit).
    3. Die frühere Messung endet beim Beginn der späteren (nur bei **verschiedenen** Tätigkeiten); die frühere Zeit wird verbucht, die spätere läuft weiter.
  - **Einseitiger Stempel** → **immer nachfragen**: weiterlaufen lassen oder verwerfen.
  - **Fremde Eigenschaften** werden **je Schlüssel** zusammengeführt; bei unterschiedlichen Werten entsteht ein Konflikt.
- `cleanup.is_empty_day_text` behandelt Dateien mit `zeit_*` nicht als leer.

---

## Befunde aus der Erkundung

- **Frontmatter:** `blocks._find_frontmatter` erkennt nur die Spanne (Zeile 0 `---`, Ende `---`/`...`, ohne Ende `None`). Kein Code liest oder schreibt Schlüssel. Neue Tagesdateien entstehen ohne Frontmatter: `_edit(allow_missing=True)` → `Writer.write(rel, None, after)`.
- **Merge kennt kein Frontmatter:**
  - Union (`merge2`) macht aus `zeit_Orga: 90` / `120` **beide Zeilen**. `verify` lässt das durch, der Fall wird `AUTO`, und es entsteht still **doppeltes YAML**.
  - diff3 läuft nur für eigene Konfliktdateien mit Sidecar-Basis.
  - `verify()` liefert eine **Fehlerliste**; leer heißt gültig.
- **Op-Arten** (`OpStore.create`):

  | Art | Blobs / Besonderheit |
  |---|---|
  | `write` | `neu`, ggf. `vorher`; `verdraengt` nur im State (`d_sha1`) |
  | `remove` | `vorher` |
  | `automerge` | — |
  | `resolve` | — |
  | `move` | Kinder per `eltern_op` |
  | `konfliktbasis` | — |

  Abschlusszustände (`FINAL_STATES`): DONE, ABORTED, CONFLICTED, INTERRUPTED.
- **Muster für mehrteilige Vorgänge:** `core/move_exec.py`.
  - Eine Eltern-Op hält den vollständigen Plan im Manifest.
  - Jeder Schritt ist eine Kinder-`write`-Op.
  - **Ob ein Schritt erledigt ist, entscheidet allein der Zustand der Kinder-Op, nie ein Textvergleich** (`_child_state`, `DONE_LIKE`).
  - `recover_moves` setzt nach der Tausch-Wiederherstellung fort; `INCOMPLETE` wartet auf die Nutzerin bzw. den Nutzer.
- **Eigene Konfliktdateien:** `core/conflict_files.py` erzeugt `…sync-conflict-…-MERKWEISER….md` mit Sidecar auf eine `konfliktbasis`-Op; damit läuft diff3 im Dialog.
- **`retention.prune_ops` schützt heute:**
  - nicht abgeschlossene Ops
  - Ops mit offenem Hinweis
  - Ops, die eine existierende Konfliktdatei bzw. ein Marker referenziert
  - Sidecar-Basen
  - `nur_manuell`
- **Bestehender Fehler:** Kinder eines `INCOMPLETE`-Moves werden **nicht** geschützt. Nach Ablauf der Aufbewahrung sieht `_continue` den Zielschritt als offen an und **hängt erneut an**. Behebung in Phase 0.
- **Flet 0.86.5:**

  | Funktion | Stand |
  |---|---|
  | `ft.Text(spans=[ft.TextSpan(…, on_click=…)])` | ✔ |
  | Badge über `ft.Icon(…, badge="3")` als `icon` der `NavigationBarDestination` | ✔ |
  | `ft.TimePicker` (`page.show_dialog`, `on_change`) | ✔ |
  | `ft.Dropdown` (`on_select`) | ✔ |
  | `ft.SegmentedButton` | ✔ |
  | `page.on_app_lifecycle_state_change` (SHOW/RESUME/HIDE/INACTIVE/PAUSE/DETACH/RESTART) | ✔ |
  | Benachrichtigungen, Hintergrundausführung | ✘ |

  Der Build kann Permissions (`[tool.flet.android.permission]`) und Pubspec-Abhängigkeiten setzen, aber **keine Receiver oder Services**. Das geht nur über ein eigenes **Flutter-Plugin**, dessen Android-Manifest Android automatisch einmischt: per Flet-Erweiterung (`build_base.py:1745ff`) oder eigenem Build-Template (`tool.flet.template.dir`).
- **Vorhandene Bausteine zum Wiederverwenden:**
  - `note_ops.delete_note`
  - `patch.resolve_block` (exakter, eindeutiger Blocknachweis)
  - `vault.write_target`
  - `conflicts.render`
  - `merge.diff3.merge3`, `merge.verify.verify`
  - `automerge_log.undo_automerge` und `undone_manual_paths` (`nur_manuell`)
  - `conflict_views.line_diff`
  - `ops.read_blob`

---

## Sicherheitsmodelle (vor der jeweiligen Umsetzung verbindlich)

### S0 – Schrittprotokoll (gemeinsame Grundlage für Y1, Y2, Y3, Undo)

Das Move-Muster wird verallgemeinert: `core/step_ops.py` (neu, etwa 120 Zeilen) bündelt `child_state(store, parent, relpath)`, `run_step(…)` (planen auf frischem Stand, bis zu 3 Neuversuche bei `ChangedBeforeWriteError`), `finish` und `incomplete`.

- Die **Eltern-Op** speichert **vor dem ersten Schreiben** im Manifest den vollständigen Plan: alle Dateien, die je Datei **beim Planen gesehenen Werte** und die Nutzerentscheidung.
- **Ein Schritt = genau ein atomarer `Writer.write` je Datei**, als Kinder-Op. Alles, was eine Datei betrifft, steckt in **einem** Schreibvorgang, z. B. „Minuten addieren + Stempel entfernen“ oder „`zeit_alt` entfernen + `zeit_neu` erhöhen“. Halbe Zustände innerhalb einer Datei kann es deshalb nicht geben.
- Ein Schritt gilt als **erledigt**, wenn seine jüngste Kinder-Op `DONE_LIKE` oder `CONFLICTED` ist.
  - Bei `CONFLICTED` steht Merkweisers Fassung in einer eigenen Konfliktdatei mit Sidecar-Basis. Der Merge mit Basis bringt sie ein (diff3; bei `zeit_*` zusätzlich das Maximum).
  - Ein Vergleich von Text oder Werten entscheidet **nie** über „erledigt“.
- **Wiederaufnahme:** Beim Start nach `recover` (Tausch-Wiederherstellung, alle Kinder sind danach eindeutig installiert oder nicht) und nach `recover_moves` laufen die neuen Arten über `recover_steps`. Erledigte Schritte werden übersprungen.
- Vor jedem **offenen** Schritt prüft Merkweiser, ob die Datei noch zum Plan passt.
  - Passt sie nicht, wird **nichts geschrieben**.
  - Die Op wird `INCOMPLETE` mit Hinweis und erscheint im Konfliktbereich unter „Unterbrochene Vorgänge“, mit „Erneut prüfen“ / „Verwerfen“ und Verweis auf die Backups.
  - So bleibt die Wiederaufnahme nicht-destruktiv.
- Die Retention schützt Eltern und Kinder bis zum Abschluss (**S6**).

### S1 – Zeitbuchung `stop` / `switch` / `abort` (Y1)

**Planung:** Die Eltern-Op `zeitbuchung` speichert im Manifest:
- `stempel` (Start, Tätigkeit, Datei des Starttags)
- `ende`
- `segmente` = `[{tag, relpath, minuten}]` (Datei über `write_target`; bei `AmbiguousDayFile` Abbruch **vor** der Op)
- bei `switch`: `neuer_stempel` (Start = `ende`, neue Tätigkeit)
- bei `abort` ohne Zeit: keine Segmente

**Schritte, in dieser Reihenfolge:**
1. Segmente der **Folgetage** (nur über Mitternacht), aufsteigend: jeweils `zeit_X += minuten`.
2. **Starttag-Datei**, ein Schreibvorgang:
   - Segment des Starttags addieren
   - Stempel entfernen
   - bei `switch` mit gleichem Tag den neuen Stempel setzen
3. Nur bei `switch` mit anderem Tag: neuen Stempel in die heutige Datei.

**Prüfung vor jedem offenen Schritt:** Der Stempel in der Starttag-Datei muss noch **genau** dem Manifest entsprechen.
- **Fehlt er vor Schritt 1:** Die Op wird `ABORTED`, nichts ist verbucht. Hinweis: „Messung wurde inzwischen anderswo beendet“.
- **Fehlt er nach erledigtem Schritt 1:** `INCOMPLETE` mit Liste der schon verbuchten Teile, keine weitere Buchung. Rücknahme ist einzeln über die Backups möglich.

**Sperre:** Solange eine `zeitbuchung` offen ist, zeigt der Zeit-Tab „Buchung wird abgeschlossen …“ bzw. den Hinweis und bietet **keinen** zweiten Stopp an. Ein doppeltes Stoppen ist damit ausgeschlossen.

**Einzelne Schreibvorgänge ohne Eltern-Op:**
- Start
- veralteten Stempel löschen
- Abbruch ohne Zeit

Ihr erwarteter Ausgangsstand wird über `Writer.write(expected)` geprüft.

### S2 – Umbenennen und Zusammenführen (Y2, Y8)

**Planung:** `valid_activity(neu)` wird geprüft. Dann wird **das ganze Archiv** nach `zeit_alt` und Stempeln mit `alt` durchsucht.

Die Eltern-Op `umbenennen` speichert im Manifest:
- `alt`, `neu`, `zusammenfuehren`
- `dateien = [{relpath, alt_wert, neu_wert|None, stempel_alt: bool}]`

Zum Zeitpunkt der Op-Erzeugung wird außerdem der **Umbenennungs-Log** geschrieben (app-intern, siehe unten).

**Schritt je Datei, ein Schreibvorgang:**
- `zeit_alt` entfernen
- `zeit_neu = neu_wert + alt_wert` (bzw. `alt_wert`)
- `messung_taetigkeit alt → neu`

**Vor einem offenen Schritt:** Die aktuellen Werte müssen **gleich den geplanten** sein.
- Sonst wird diese Datei **übersprungen** und als „Umbenennung unklar“ gemeldet (siehe unten).
- Erneute Addition ist unmöglich, weil Entfernen und Addieren atomar zusammen geschehen. Ob ein Schritt erledigt ist, entscheidet das Schrittprotokoll.

Nach allen Dateien wird die Geräteliste aktualisiert und die Op `DONE`.

**Umbenennungs-Log** (app-intern: `alt → neu`, Zeitpunkt) gegen später durch Sync auftauchende alte Schlüssel (Y8):
- **Normalisierung im Merge:** Vor dem `zeit_*`-Maximum wird auf **beide** Seiten eines Sync-Konflikts die bekannte Umbenennung angewandt (`zeit_alt` in `zeit_neu` addieren). Danach gilt je Schlüssel das Maximum.
  - Beispiel: A hat nach der Umbenennung `Verwaltung: 90`; B (ohne Kenntnis) hat `Orga: 120`, die Zahl schließt die 90 ein. B normalisiert ergibt `Verwaltung: 120`, Maximum 120. ✔
  - Mit Zusammenführung: A hat `Verwaltung: 140` (50 + 90); B hat `Verwaltung: 50` und `Orga: 120`. B normalisiert ergibt 170, Maximum 170. ✔
- **Ohne Konflikt** (beim Scan des geprüften Zeitraums bzw. Archivs):
  - Taucht `zeit_alt` in einer Datei **ohne** `zeit_neu` auf, wird automatisch migriert. Das ist eine reine Umbenennung, also ist nichts doppelt.
  - Stehen **beide** in einer Datei (z. B. ein anderes Gerät hat ohne Kenntnis der Umbenennung zusammengeführt), wird **nicht** automatisch gerechnet. Stattdessen erscheint der Hinweis „Umbenennung unklar“ für diese Tage, mit der Wahl **addieren / größeren Wert / nichts ändern**.
- **Aktive Stempel** mit altem Namen werden umbenannt (Anforderung W6). *Abweichung bei der Umsetzung (2026-10-23):* Ein Stempel verrät nicht, von welchem Gerät er stammt; „fremde“ Stempel lassen sich also nicht ausnehmen. Stoppt ein anderes Gerät gleichzeitig, entsteht ein Sync-Konflikt um den Stempel-Datensatz, der nachgefragt wird (S5) – nichts wird still doppelt gebucht. Ein Stopp auf dem anderen Gerät mit altem Namen bucht `zeit_alt`; das wird später migriert (siehe oben).
- Legt man eine Tätigkeit neu an, deren Name im Log als `alt` steht, wird der Log-Eintrag entfernt, mit Hinweis.
- `GRENZE(Umbenennung)`: Das andere Gerät kennt die Umbenennung nicht und zeigt den alten Namen weiter, bis er dort ebenfalls umbenannt wird.

### S3 – Duplikatbereinigung (Y3)

**Planung:** Die Eltern-Op `duplikat` speichert im Manifest:
- `zeilen` (normalisiert)
- `fundstellen = [{relpath, tag, erste_zeile}]`
- `behalten` (Index)

**Prüfung vor jedem Schritt, auch nach einem Neustart:** Die behaltene Fundstelle muss die Notiz noch exakt enthalten (`resolve_block`, eindeutig; bei mehreren Vorkommen gilt das an `erste_zeile`).
- Fehlt sie, wird `INCOMPLETE` gesetzt: „Behaltene Fassung fehlt – nichts weiter gelöscht“.

**Schritt je anderer Fundstelle:** Gesucht wird eine **ganze Notiz** mit exakt diesen Zeilen in der aktuellen Datei.

| Ergebnis | Aktion |
|---|---|
| genau eine | `delete_note` |
| mehrere | die an `erste_zeile`; sonst überspringen |
| keine (verändert oder entfernt) | überspringen, Hinweis „Fundstelle … inzwischen verändert – nicht gelöscht“ |

Die Auswahl wird **nie** neu abgeleitet; sie steht im Manifest.

### S4 – Rückgängig, Existenz und Merge-Entscheidung (Y6, Y7, Y9)

**Eingaben:** `before = vorher | None` (`None` = Datei existierte nicht) und `after = neu | None` (`None` = gelöscht). `current` ist der aktuelle Stand oder `None`.

**Inhalt:** `merge3(base=after or b"", a=current or b"", b=before or b"")`. Eine fehlende Datei zählt also nur **intern** als leer.

**Existenz** (diff3 auf einem Wahrheitswert):

```
ex = exists(before) if exists(current) == exists(after) else exists(current)
```

| Ergebnis | Inhalt | Aktion |
|---|---|---|
| `ex` falsch | leer | Datei entfernen (`Writer.remove`, erwartet `current`) |
| `ex` falsch | nicht leer | **Konfliktdatei** (nie Inhalt durch Löschen verlieren) |
| `ex` wahr | — | schreiben, auch ein leeres Ergebnis (eine echt leere Datei bleibt eine leere Datei) |

**Sicherheitsentscheidung** (Y9):

```python
merge_is_safe(result, a, b, base) -> bool:
    return result.clean and verify(result, a, b, base) == []
```

`verify` liefert die **Liste der Fehler**.
- **Nur** bei `True` wird direkt geschrieben.
- Sonst wird `before` eine **eigene Konfliktdatei** mit Sidecar-Basis `after` (neue `konfliktbasis`-Op). Der Konfliktdialog zeigt dann einen echten diff3.

**Frontmatter** (Y7):
- Ab Phase 6 trennt Undo Frontmatter und Rumpf wie der Sync-Merge.
- Das Frontmatter wird **je Schlüssel bzw. Stempel-Datensatz per diff3** zusammengeführt, **ohne** Maximum-Regel: Undo darf Werte senken.
- Haben beide Seiten denselben Schlüssel bzw. Stempel geändert, entsteht eine **Konfliktdatei**. Jüngere Zeitwerte, Stempel und fremde Eigenschaften werden so nie still überschrieben.
- Bis Phase 6 läuft Undo zeilenbasiert über die ganze Datei. diff3 ist dabei konservativ: Eine von beiden Seiten geänderte Zeile wird zum Hunk und damit zur Konfliktdatei. Phase 6 ergänzt Regressionstests für die bestehende Backup-Funktion.

**Weitere Regeln:**
- **Idempotenz:** Undo ist eine Eltern-Op `rueckgaengig` (`ziel_op`) mit einem Schritt. „Bereits rückgängig gemacht“ wird aus vorhandenen abgeschlossenen `rueckgaengig`-Ops **abgeleitet**; die Ziel-Op wird nicht verändert.
- **Wiederhergestellte Sync-Konfliktdateien** (Undo eines Konfliktdatei-`remove`) erhalten `nur_manuell` auf der `rueckgaengig`-Op. So führt der nächste Start sie nicht automatisch erneut zusammen.
- **Verdrängte Stände** werden immer als Konfliktdatei wiederhergestellt (ohne Sidecar, Union-Pfad).

### S5 – Frontmatter-Parser und Stempel-Datensatz (Y4, Y5)

**Unterstützte Struktur** (`core/frontmatter.py`, ohne Fremdpakete):
- **Begrenzer:** Zeile 0 ist exakt `---` (nach BOM), Ende ist `---` oder `...` (wie `_find_frontmatter`).
- **Einträge:** Jeder Eintrag beginnt mit einer **Schlüsselzeile ohne Einrückung**: `^([A-Za-z_\u00C0-\uFFFF][^:#"'\n]*?):(?:[ \t]|$)`, also ein **unquotierter** Schlüssel, nach dem ersten `: ` beginnt der Wert. Doppelpunkte **im Wert** sind erlaubt.
- **Folgezeilen** gehören zum Eintrag: eingerückte Zeilen, Zeilen mit `- ` (kompakte Listen) und Leerzeilen. Damit sind auch Block-Skalare (`|`, `>`) und verschachtelte Strukturen als **undurchsichtige Einträge** abgedeckt; ihr Inhalt wird nur als ganzer Block verglichen.
- **Fremde Werte** werden nie interpretiert, nur byte-genau verglichen und übernommen.

**Undurchsichtiges Frontmatter (`OPAQUE`):** Jede andere Zeile ohne Einrückung macht das Frontmatter `OPAQUE`, ebenso jeder **doppelte fremde Schlüssel**. Das betrifft z. B.:
- Kommentare `#`
- quotierte Schlüssel
- `? `-Schlüssel
- Flow-Fortsetzungen
- Tabs am Zeilenanfang
- Dokumentmarker

Folgen von `OPAQUE`:
- **Schreiben eigener Schlüssel:** wird **verweigert** („Kopfbereich nicht sicher lesbar – Zeit nicht eingetragen“). Die Zeitmessung zeigt den Fehler; nichts wird umgeschrieben.
- **Sync-Merge:** Das Frontmatter gilt als Block, bei Gleichheit wird es übernommen, sonst entsteht ein **manueller Konflikt** („Kopfbereich unterschiedlich“), zu lösen durch Wahl von Seite A oder B.

**Unvollständige Begrenzer** (Zeile 0 `---` ohne Ende):
- Es wird **nie** ein neues Frontmatter davorgesetzt; das Schreiben wird verweigert.
- Im Merge gilt der Rumpf wie heute.

**Eigene Werte streng geprüft:**
- `zeit_*` muss `^\d{1,5}$` sein.
- `messung_start` muss ISO-8601 mit Offset sein.
- `messung_taetigkeit` muss gültig nach R2 sein.
- Ungültig heißt **beschädigt**: kein stilles Überschreiben, Hinweis mit „verwerfen“.
- Doppelte eigene `zeit_*`-Schlüssel (Altlast aus Union-Merges oder Handarbeit) werden als **Maximum** gelesen und beim nächsten Schreiben zu einer Zeile zusammengefasst, im Einklang mit der Konfliktregel; das steht im DEVELOPMENT_LOG.

**Byte-Genauigkeit:**
- Nur die eigenen Zeilen werden ersetzt, eingefügt (vor dem schließenden Begrenzer) oder entfernt.
- BOM, CRLF bzw. das vorherrschende Zeilenende und eine fehlende abschließende Zeile bleiben erhalten.
- Ein Frontmatter wird nur entfernt, wenn es durch Merkweiser **ganz leer** wird.
- Nicht schreibbares Encoding wird verweigert.

**Stempel als Datensatz:** `stamp_of(fm) -> Stamp | None | Damaged`.
- Beide Schlüssel fehlen: `None`.
- Beide gültig: `Stamp`.
- Nur einer, doppelt oder ungültig: `Damaged`. Ein beschädigter Stempel läuft **nie** als Messung weiter: Der Zeit-Tab zeigt „Beschädigter Messstempel in … – verwerfen“, ohne Verbuchung.

**Merge des Stempel-Datensatzes:** Er wird **nur als Ganzes** gemergt, nie je Schlüssel.
- gleich → übernehmen
- ohne Basis, einseitig → **Nachfrage**
- zwei verschiedene → Optionen 1–3 (siehe W6)
- `Damaged` auf einer Seite → Nachfrage mit Option „verwerfen“

Mit Basis (nur eigene Konfliktdateien, z. B. CONFLICTED-Schritte aus S1/S2) gilt diff3 auf dem Datensatz: Hat nur eine Seite ihn gegenüber der Basis geändert, ist der Fall eindeutig und es gibt keine Nachfrage. Andernfalls wird nachgefragt (siehe Offene Punkte, B1).

**Ergebnis in `resolve`:**
- Option 3 bucht die Minuten der früheren Messung (früherer Start → späterer Start, beide am Tag dieser Datei, also kein Mitternachtsfall) **im selben Ergebnis**.
- Das Ergebnis-Frontmatter wird mit dem Rumpf über `render` zu den Ergebnisbytes zusammengesetzt und läuft durch das bestehende `resolve` (eine atomare Hauptdatei-Schreibung).

### S6 – Retention schützt alle Wiederaufnahme-Abhängigkeiten (Y11)

`prune_ops` berechnet den Schutz **bei jedem Lauf neu aus dem Zustand**. Es gibt keine Schutz-Flags, die man vergessen könnte; der Schutz endet automatisch und wiederholbar, sobald der Vorgang abgeschlossen ist.

Geschützt sind:
- **P1** nicht abgeschlossene Ops (wie bisher; `INCOMPLETE` ist nicht final)
- **P2** alle Ops, deren `eltern_op` nicht abgeschlossen ist (**behebt den Move-Fehler**)
- **P3** Ops, die das Manifest einer nicht abgeschlossenen Op referenziert (`ziel_op`, `basis_op`)
- **P4** Sidecar-Basen, Konfliktdatei- bzw. Marker-Referenzen, `nur_manuell` (wie bisher)

Tests zeigen: Eine Wiederaufnahme scheitert nie an gelöschten Blobs. Nach Abschluss wird beim nächsten Lauf normal gelöscht.

### S7 – Zeitzone und Mitternacht (1.3)

- **Dauer:** Gerechnet wird mit **absoluten Zeitpunkten** (UTC-Differenz). Bei Sommer- und Winterzeit stimmt die Gesamtdauer daher immer.
- **Tagesgrenzen:** Sie sind die lokalen Mitternachten **in der aktuellen Zeitzone des Geräts beim Stoppen**, über `datetime.astimezone()` mit den Systemregeln (inklusive Sommerzeit).
- **Starttag:** Das erste Segment gehört immer zur Datei des Stempels, nicht zu einem neu berechneten Datum.
- **Abrunden:** je Segment auf ganze Minuten.
- `GRENZE(Zeitzone)`: Wechselt die Zeitzone des Geräts während einer Messung, stimmt die Summe. Der Teilungspunkt über Mitternacht kann sich aber um den Zeitzonenunterschied verschieben.
- **Anzeige:** Die Startzeit erscheint in lokaler Zeit; der Stempel speichert den Offset vom Start.

### R2 – Tätigkeitsnamen (Allowlist, 1.8)

`valid_activity(name) -> str` liefert den normalisierten Namen oder wirft `ValueError` mit deutscher Meldung. Vorgehen:
1. `unicodedata.normalize("NFC", name)`
2. Leerzeichen am Rand entfernen
3. Länge 1–40
4. Jedes Zeichen muss passen: Buchstabe (Kategorie `L*`), Kombinationszeichen `M*` **direkt nach** einem Buchstaben, Ziffer `Nd`, `-`, `_` oder ein **einzelnes** Leerzeichen zwischen anderen Zeichen.

Damit ist **alles andere** ausgeschlossen, also auch Steuerzeichen, Zeilenumbrüche, Tabs und alle YAML-Sonderzeichen; es braucht keine Verbotsliste.

- **Vergleich:** nach NFC; „gibt es schon“ prüft zusätzlich `casefold`, damit kein „Orga“/„orga“-Doppel entsteht.
- **Geltung:** vor jedem Datei-Schreiben sowie beim Hinzufügen, Umbenennen, Starten und Wechseln.
- **Bestehende Namen außerhalb der Regel** (nur aus Hand-Edits möglich) erscheinen nur lesend in der Übersicht. Man kann nicht mit ihnen starten, sie aber in einen gültigen Namen **umbenennen**.

### Y12 – Minütliche Aktualisierung

Die Klasse `Ticker` (rein, testbar, in `mobile/ui/time_view.py` bzw. `app/ticker.py`) hält **höchstens einen** Task.
- `start()` bricht einen vorhandenen Task ab und startet genau einen neuen (`page.run_task`).
- `stop()` bricht ab.
- Aufgerufen wird `start` beim Sichtbarwerden der Zeit-Ansicht und `stop` bei Tabwechsel, Unterseite, Dialog-Unterseite und Lifecycle HIDE/PAUSE.
- Der Task aktualisiert **nur Anzeige-Controls**; er schreibt nie.

---

## Design je Wunsch

### W1/W2
- **`app/views.py`:**
  - `urgent_first(rows)` zerlegt nach `depth` in Teilbaum-Blöcke und sortiert stabil je Geschwistergruppe.
  - `text_parts(text) -> list[tuple[str, str | None]]` nutzt `inline.TAG_RE` (`_TAG_RE` wird öffentlich).
- **`mobile/ui/note_view.py`:** `ft.Text(spans=…)`; Tag-Spans fett in der Primärfarbe mit `on_click → app.nav.push(TagPage(tag))`.
- **`app/tag_service.py` bzw. View-Funktion `tag_notes(tag)`:** über `query.search(Filter(tags=(tag,)))`, eindeutig je `(relpath, note_index)`, neueste zuerst.
- **`mobile/ui/tag_view.py`:** nutzt `note_row` mit `urgent_first`.

### W4 Navigation (1.6)
- **`app/nav.py`** (rein, testbar): `Nav` mit `stacks: dict[Tab, list[PageRef]]` und `current`.
  - `PageRef` sind **Daten** (z. B. `TagPage(tag)`, `BackupFile(relpath)`), keine Controls. Gerendert wird immer frisch.
  - `switch(tab)` behält alle Stapel.
  - Erneutes Antippen des aktiven Tabs springt zur Wurzel.
  - `push` legt eine Seite auf den Stapel des aktuellen Tabs.
  - `back() -> bool` nimmt die oberste Seite des aktuellen Stapels; an der Wurzel eines anderen Tabs als Tag wechselt es zu Tag; an der Wurzel von Tag liefert es `False` (System-Zurück).
- **Einzige Wahrheit:** Die einzige Wahrheit ist `Nav`.
  - `page.views` wird bei jedem `render` daraus abgeleitet: Wurzel-View plus je Unterseite eine View des aktuellen Tabs.
  - `page.on_view_pop` ruft nur `nav.back()` und dann `render`.
- **Phase 1 prüft in 0.86.5:** System-Zurück bei mehreren Views, `View.can_pop` / `on_confirm_pop` und Zurück bei offenem Dialog (Dialog schließt, der Stapel bleibt unverändert).
  - Fallback, falls System-Zurück nicht abfangbar ist: Der Zurück-Knopf in der App funktioniert, System-Zurück verlässt die App (`GRENZE(Zurück)`).

### W4 Backups
- **`core/backups.py`:**
  - `Change(op_id, relpath, zeit, art, before: bytes|None, after: bytes|None, gruppe: op_id|None, gruppen_art)` aus allen **Blatt-Ops** (`write`/`remove`).
  - Die Art wird über die Eltern-Op bestimmt:

    | Eltern-Op | Art |
    |---|---|
    | `automerge` | automatisch zusammengeführt |
    | `resolve` | Konflikt entschieden |
    | `move` | verschoben |
    | `rueckgaengig` | Rückgängig |
    | `duplikat` | Duplikat entfernt |
    | `zeitbuchung` | Zeit eingetragen |
    | `umbenennen` | Tätigkeit umbenannt |
    | keine | bearbeitet / angelegt / gelöscht |

  - Verdrängte Stände (`d_sha1`) bilden eine eigene Art.
  - `changes_by_file(store)` sortiert neueste zuerst.
  - `undo_change(...)` setzt **S4** um.
- **Zusammenhang** (1.4): Hat eine Änderung eine `gruppe`, zeigen Liste und Bestätigungsdialog „Gehört zu: Verschieben 20.10. → 21.10. (2 Dateien)“ mit Links zu den Geschwistern und einer Folgenwarnung je Gruppenart.

  | Gruppenart | Warnung |
  |---|---|
  | Move | Nur das Ziel zurück heißt: Das Todo steht in keiner Datei mehr (bleibt im Backup); nur die Quelle zurück heißt: Das Todo steht doppelt. |
  | Mitternachtsbuchung | Der andere Tag bleibt verbucht. |
  | Duplikat | Die Notiz wird wieder als Duplikat gemeldet. |
  | Umbenennung | Nur diese Datei. |

- **Auto-Merge / Resolve:** Die Einzeländerungen sind einzeln rückgängig zu machen (S4). Zusätzlich bleibt in der Gruppe der bisherige Knopf „**Zusammenführung rückgängig**“ (`undo_automerge`, stellt Hauptdatei und Konfliktdatei wieder her, `nur_manuell`) erhalten. Für `resolve` gibt es das Gegenstück über eine gemeinsame Hilfsfunktion mit `automerge_log._restore_conflict`.
- **UI:** `mobile/ui/backup_view.py` mit Dateiliste, Änderungsliste, Vergleich (`line_diff`) und Rückgängig mit Bestätigung.

### W3
- **`core/duplicates.py`:** `find_duplicates(docs) -> list[DuplicateGroup(zeilen, fundstellen)]`, sortiert nach Datum.
- **`app/duplicate_service.py`:** `duplicates()` und `keep_one(group, keep)` (S3).
- **UI:** Abschnitt „Doppelte Notizen“ auf der Konflikte-Seite.

### W6
- **`core/frontmatter.py`** (S5):
  - `parse(doc) -> Frontmatter(entries | OPAQUE, span)`
  - `get_minutes(raw) -> dict[str, int]`
  - `stamp_of(...)`
  - `set_own(raw, minutes: dict, stamp: Stamp | None | KEEP) -> bytes`
  - `valid_activity` (R2)
- **`core/merge/frontmatter.py`:** `merge_frontmatter(a, b, base=None, renames=()) -> FmMerge(lines, conflicts)`.
  - `zeit_*`: zuerst die Umbenennungen normalisieren (S2), dann das Maximum.
  - Stempel als Datensatz (S5).
  - Fremde Schlüssel: gleich → einmal; einseitig → übernehmen (mit Basis greift die diff3-Regel, auch für Löschungen); unterschiedlich → `PropertyConflict`.
  - `OPAQUE` → Block: gleich oder Konflikt.
  - Eine zweite Variante `reverse=True` (ohne Maximum) dient dem Undo (S4).
- **`conflicts._evaluate`:**
  - Frontmatter und Rumpf werden getrennt; der Rumpf läuft wie bisher (`merge2`/`merge3` + `merge_is_safe`).
  - `AUTO` nur, wenn beides sauber ist; sonst `MANUAL` mit dem Grund „laufende Messungen“, „unterschiedliche Eigenschaften“ oder „Kopfbereich unterschiedlich“.
  - `ConflictCase.frontmatter: FmMerge | None`; `render` und `hunk_result` setzen alles wieder zusammen.
- **Dialoge:** `mobile/ui/stamp_dialog.py` für Stempel- und Eigenschaftswahl; das Ergebnis geht in `resolve`.
- **`core/timetrack.py`** (rein):
  - `Stamp`
  - `segments(start, end, start_day) -> list[(date, minuten)]` (S7)
  - `stale(stamp, now)`
  - `overview(...)`
  - `order_activities(...)`
- **`app/time_service.py`:**
  - `scan(days)`: Minuten, gültige, veraltete und beschädigte Stempel; bereinigt veraltete; bei mehreren gültigen Stempeln ohne Sync-Konflikt (z. B. von zwei Geräten in verschiedenen Tagesdateien) öffnet sich der Stempel-Dialog.
  - `archive_scan()` (einmal je Sitzung)
  - `start`, `stop`, `switch`, `abort(end | None)` (S1)
  - `rename(alt, neu, merge)` (S2)
  - `delete`
  - `recover_steps` (S0)
- **`app/settings.py`:**
  - `taetigkeiten: list[str] = ["Orga"]`
  - `umbenennungen: list[dict]`
  - `benachrichtigung_an: bool = False`
  - `benachrichtigung_zeit: str = "07:00"`
  - `eskalation_an: bool = True`
  - `urlaub_bis: str | None = None`
- **UI** (`mobile/ui/time_view.py` und `time_dialogs.py`):
  - Dropdown (`on_select`), Start/Stopp-Knopf, „läuft seit …“
  - „Messung abbrechen“ mit TimePicker bzw. „Keine Zeit eintragen“
  - Tätigkeiten verwalten: Validierung, Zusammenführen-Rückfrage, Löschen gesperrt bei aktiver Messung
  - SegmentedButton 7/14/30
  - Tageszeilen und Summen
  - Hinweise: veraltet, beschädigt, Umbenennung unklar, unterbrochene Buchung
  - `Ticker`

### W5
- **Spike S5** (Y10) als eigenes **Flutter-Plugin** + Flet-Erweiterung `packages/merkweiser_notify`. Das Plugin umhüllt `flutter_local_notifications`: `zonedSchedule` im Modus **`inexactAllowWhileIdle`**, `cancelAll`, Berechtigung anfragen und abfragen, Start-Payload. Receiver (`ScheduledNotificationReceiver`, `ScheduledNotificationBootReceiver`) und `RECEIVE_BOOT_COMPLETED` stehen **im Manifest des Plugins**; `POST_NOTIFICATIONS` kommt über `[tool.flet.android.permission]`.
- **Der Spike belegt auf dem Gerät:**
  1. Build mit Flet 0.86.5 und die Receiver im zusammengeführten Manifest (`build/…/AndroidManifest.xml` bzw. per `aapt dump`)
  2. Berechtigungsdialog unter Android 13+: verweigern, später in den Systemeinstellungen erlauben, wieder entziehen; Merkweiser zeigt den Zustand an
  3. Auslösen bei geschlossener App (aus dem App-Umschalter gewischt)
  4. Auslösen nach einem Geräte-Neustart
  5. Antippen öffnet die App im Tab **Tag** (heutiges Datum) (Kaltstart und laufende App)
  6. Verhalten bei Akku-Optimierung bzw. „eingeschränkt“
  7. gemessene Verspätung gegenüber der Soll-Uhrzeit

  Das Ergebnis kommt nach `spikes/s5/bericht.md`.
- **Fallback**, wenn die Erweiterung scheitert: eigenes Build-Template (`tool.flet.template.dir`) mit Kotlin-Receiver und Aufruf per pyjnius; gleiche Prüfliste.
- **Genauigkeit:** Ohne Exact-Alarm-Recht (Android 14 standardmäßig verweigert) ist die Auslösung **ungenau**. Die Einstellungen sagen ehrlich: „gegen 7:00, kann sich bei Akkusparen verzögern“.
- **Begründung des Horizonts:** Android kann Alarme einer App, die lange nicht geöffnet wurde, über App-Standby-Buckets („selten“ bzw. „eingeschränkt“) stark drosseln, bis zu einem Alarm je Tag oder weniger. Deshalb ist der Standard 14 Tage, das Maximum 30; mehr wäre nicht verlässlich. `GRENZE(Zustellung)`: Android garantiert keine Zustellung.
- **`app/notify_plan.py`** (rein): `plan(now, settings, content_for(day)) -> list[Planned(at, title, body, level)]`
  - Termine sind die nächsten N Tage zur eingestellten Uhrzeit (lokale Zeitzone); Urlaubstage werden übersprungen.
  - **Termin 1:** der nächste Termin, sofern nicht im Urlaub. Gibt es Inhalt, kommt die Inhaltsbenachrichtigung (`normal`), sonst **keine**.
  - **Folgetermine:** neutral. Die Stufe zählt Nicht-Urlaubstermine seit Termin 1: 2. Termin `normal`, 3. Termin `hoch` („Seit 2 Tagen nicht geöffnet …“), ab dem 4. `maximal` (Heads-up).
  - **Eskalation aus:** Alle neutralen Erinnerungen sind `normal` mit gleichem Text, und es gibt weiterhin täglich eine.
  - **Liegt Termin 1 im Urlaub:** Der erste Termin nach dem Urlaub ist **neutral** `normal`, weil der Inhalt veraltet wäre; danach eskaliert es wie oben.
- **Adapter** `mobile/platform/notifications.py`: Protocol, Plugin-Implementierung und No-op für Desktop und Tests.
  - Neu geplant wird bei HIDE/PAUSE/DETACH, beim Start und bei Einstellungsänderungen (vorher `cancelAll`).
  - Start per Payload → `nav.switch(TAG)` auf die Wurzel, Datum heute.
- **Einstellungsseite „Benachrichtigungen“:**
  - Schalter (das erste Einschalten fragt die Berechtigung an)
  - Anzeige des Berechtigungszustands
  - TimePicker
  - Schalter Eskalation
  - DatePicker für den Urlaub und „Urlaub beenden“

---

## Phasen

Jede Phase: Tests → Doku → Commit + Push. Nach den Phasen 2, 4, 8 und 10 kommt ein APK-Gerätetest **mit dir**.

0. **Vorbereitung:**
   - Plan nach `docs/PLAN.md` übernehmen.
   - `core/step_ops.py` (S0) aus `move_exec` herauslösen (Move nutzt es, gleiches Verhalten).
   - **Retention S6** einschließlich Behebung des Move-Fehlers, mit Test: Move `INCOMPLETE`, Kinder älter als die Aufbewahrung → nach `prune` + Fortsetzen genau ein Ziel-Eintrag.
1. **W1 + W2** und `Nav` (inklusive Prüfung von System-Zurück in 0.86.5).
2. **W4a Navigation:** neue Tabs, Einstellungen als Hub, Konflikte als Unterseite, Badge, „Unterbrochene Vorgänge“.
3. **W4b Backups:** S4 (zeilenbasiert), Gruppenhinweise, Undo-Retention.
4. **W3 Duplikate:** S3.
5. **W6a YAML-Kern:** S5-Parser, R2, FORMAT.md (Frontmatter-Regel überall angepasst), `cleanup`-Test.
6. **W6b YAML-Merge:**
   - `merge_frontmatter` und `_evaluate`/`render`
   - Stempel- und Eigenschafts-Dialog
   - Undo auf Frontmatter-Trennung umstellen (Y7) plus Regressionstests für Backups
   - Regressionstest für die doppelte YAML-Zeile
7. **W6c Tracker-Core:** S1, S2 inklusive Umbenennungs-Log, S7, Scan/Bereinigung (1.7).
8. **W6d Zeit-Tab-UI** mit `Ticker`.
9. **S5 Spike Benachrichtigungen** mit Bericht; danach entscheidest du, ob es Plugin oder Template wird.
10. **W5 Umsetzung.**

Danach `docs/PLAN.md` auf „erledigt“ setzen; weiter mit Schritt 7 (Desktop) und Schritt 9.

**Begründung der Reihenfolge:** Phase 0 kommt zuerst, weil S0 und S6 die gemeinsame Grundlage für die Phasen 3, 4 und 7 sind und der Move-Fehler heute besteht. Backups kommen vor YAML, weil zeilenbasiertes diff3 schon konservativ ist (S4); Phase 6 schließt die Lücke ausdrücklich.

---

## Verifikation

**Gesamtsuite:** `.venv/Scripts/python -m pytest` grün (heute 325 bestanden + 1 übersprungen). Absturztests nutzen die vorhandenen `fs.point`-Haltepunkte bzw. werfen Ausnahmen nach Kinder-Ops.

**Beibehalten aus Fassung 1:**
- `urgent_first` (Teilbäume, Stabilität)
- `text_parts`
- Duplikate LF/CRLF
- Frontmatter byte-genau
- Merge-Regressionstest „kein doppeltes YAML“
- Tracker-Minuten
- Tätigkeitsverwaltung
- `notify_plan`

**Zeitmessung und Recovery:**
- Absturz nach jedem Schritt von `stop`, `switch`, `abort(end)` und der Mitternachtsbuchung (vor Schritt 1, nach Schritt 1, nach Schritt 2) → Wiederaufnahme ohne doppelte Minuten und ohne verlorenen Stempel.
- Stempel ist zwischen den Schritten von außen verschwunden → `ABORTED` bzw. `INCOMPLETE`, keine weitere Buchung.
- Umbenennen: Absturz nach jeder Datei → Wiederaufnahme ohne doppelte Addition; zwischenzeitlich geänderter Wert → Datei übersprungen und gemeldet.
- Umbenennen und Sync:
  - alter Schlüssel taucht allein wieder auf → migriert
  - beide in einer Datei → „unklar“, keine Rechnung
  - Konflikt mit Normalisierung + Maximum (beide Beispiele aus S2)
  - fremder aktiver Stempel bleibt unberührt
- Duplikate: Absturz nach Löschen von B bei A/B/C mit Wahl A → C wird gelöscht, A bleibt; C inzwischen verändert → nicht gelöscht; A fehlt → `INCOMPLETE`, nichts gelöscht.
- Zeitzone: Mitternacht, Sommer- und Winterzeitnacht (Summe stimmt), Wechsel der Zeitzone (Summe stimmt, `GRENZE`); Abrunden je Segment.

**Stempel und Frontmatter:**
- Veralteter Stempel im 7-Tage-Fenster → bereinigt mit Hinweis.
- Veralteter Stempel außerhalb → erst bei Archivsuche (Wahl eines längeren Zeitraums, einmal je Sitzung).
- Unvollständiger, beschädigter, einseitiger und doppelter Stempel; zwei konkurrierende Stempel mit allen drei Optionen und ihren Bedingungen; keine Kombination von Start und Tätigkeit aus verschiedenen Geräten.
- Parser-Fälle:
  - BOM, CRLF, keine abschließende Zeile
  - fremde Eigenschaften, Listen, `|`- und `>`-Blöcke, verschachtelt
  - quotierter Schlüssel, Kommentar und doppelter fremder Schlüssel → `OPAQUE`: Schreiben verweigert, Merge-Konflikt, Datei unverändert
  - offenes `---` ohne Ende → kein Voranstellen
  - Doppelpunkt im Wert
  - eigene doppelte Schlüssel → Maximum, danach eine Zeile
- R2: Zeilenumbruch, Tab, Steuerzeichen, `:`, `#`, Anführungszeichen → abgewiesen; „Café“ in NFC und NFD → gleich akzeptiert; „ß“, Umlaute → akzeptiert; casefold-Dublette → Rückfrage.

**Backups und Retention:**
- Undo bei Neuanlage (Datei wird entfernt, wenn leer), Löschung (Datei kommt wieder), echt leerer Datei (bleibt als leere Datei), extern entfernter Datei (Konfliktdatei statt stiller Neuanlage mit Verlust).
- Rückwärts-diff3 erhält spätere Änderungen; ein Hunk erzeugt eine Konfliktdatei mit Sidecar.
- `merge_is_safe` liefert beide Fälle ausdrücklich.
- Ab Phase 6: Undo bei später geänderten `zeit_*`, `messung_*` und fremden Schlüsseln → Konfliktdatei, keine stille Überschreibung.
- Wiederhergestellte Sync-Konfliktdatei bleibt `nur_manuell`.
- Retention P1–P4, darunter der Move-Fehler-Test.

**Benachrichtigungen** (`notify_plan`):
- keine Todos → kein Termin 1, aber neutrale Folgetermine
- Eskalation an/aus
- Horizont 14 (Standard) und Grenze 30
- Urlaub einschließlich Enddatum
- Termin 1 im Urlaub → erster Termin danach neutral
- Auslösetag morgen → Inhalt aus der Datei von morgen
- lokale Uhrzeit

Gerätetests nach Spike-Prüfliste (Y10).

**Navigation** (`Nav`):
- Tag-Seite in Todos → Suche → Todos: die Tag-Seite ist noch da.
- Zurück wirkt nur auf den aktuellen Tab.
- An der Wurzel geht es zum Tab Tag bzw. zum System.
- Erneutes Antippen des Tabs führt zur Wurzel.
- Ein Dialog ist kein Stapel-Eintrag.

**Ticker:** Mehrfaches Öffnen ergibt einen Task; Verlassen ergibt keinen.

**Gerätetests mit dir (Testordner):**

| Nach Phase | Prüfen |
|---|---|
| 2 | Tag-Seite, Tab-Stapel, Zurück, Badge |
| 4 | Backup rückgängig inklusive Gruppenwarnung, Duplikat auflösen |
| 8 | Messung über App-Neustart, Mitternacht (Gerätezeit), Syncthing-Konflikt mit zwei Stempeln und einseitigem Stempel, Umbenennen |
| 10 | Benachrichtigung (Uhrzeit auf in 2 Minuten, App schließen, Neustart, Antippen), Urlaub |

`rg "BAUSTELLE|GRENZE"` prüfen; ARCHITEKTUR (Schrittprotokoll, Frontmatter-Parser, Nav), FORMAT, CHANGELOG und DEVELOPMENT_LOG je Phase.

---

## Offene Punkte

**Blockiert die Freigabe:** keiner.

**Während der Umsetzung klärbar** (gesetzter Standard in Klammern):
- **B1 – Stempel-Merge mit Basis.** Bei eigenen Konfliktdateien mit Basis gilt diff3 auf dem Datensatz ohne Nachfrage (*eindeutig, weil die Basis zeigt, wer geändert hat*). Ohne Basis wird immer nachgefragt, wie entschieden.
- **B2 – Benachrichtigungen ab Werk.** Standard *aus*; das erste Einschalten fragt die Berechtigung an.
- **B3 – Allowlist.** Zusätzlich erlaubt sind *Ziffern, `-`, `_` und einzelne Leerzeichen*, etwa für „Klasse 7b“.
- **B4 – Zurück-Verhalten.** An der Wurzel eines anderen Tabs geht es *zum Tab Tag*; erneutes Antippen eines Tabs führt *zur Wurzel*.
- **B5 – Eskalationsstufen und Texte.** Wie in Design W5; nach dem Spike anpassbar.
- **B6 – Plugin oder Build-Template.** Entschieden: eigenes Kotlin-Plugin in der Flet-Erweiterung (`packages/merkweiser_notify`); seit 2026-10-25 auf Wunsch in der App-APK, Gerätetest offen.
- **B7 – „Unterbrochene Vorgänge“.** Vor Phase 2 prüfen, ob es schon eine Anzeige für `INCOMPLETE`-Moves gibt; sonst neuer Abschnitt auf der Konflikte-Seite.

---

## Ergänzung W6a – Wechsel nachtragen (umgesetzt 2026-10-25)

**Wunsch:** Beim Wechseln der Tätigkeit eine Uhrzeit in der Vergangenheit wählen können – aber nur nach dem Beginn der laufenden Messung –, um Wechsel nachträglich einzutragen.

**Regel:** Wechselzeitpunkt `t` mit *Beginn der laufenden Messung < t ≤ jetzt*. Die laufende Messung endet um `t` (Minuten wie immer je Tag abgerundet, über Mitternacht geteilt), die neue Messung beginnt um `t`.

**Umsetzung:**
- `time_service.switch(service, activity, at=None)`: `at` Standard jetzt; Prüfung der Regel mit deutscher Meldung; `book(alter Stempel, ende=at, Segmente bis at, neuer Stempel = Stamp(at, neu), neue Datei = Tagesdatei des **Tages von `at`**)`. Der neue Stempel steht damit wie jeder Stempel in der Datei seines Starttags; liegt `at` vor Mitternacht und ist es jetzt nach Mitternacht, landet er in der gestrigen Datei, und sein späterer Stopp teilt wieder an Mitternacht.
- Absturzsicherheit unverändert über das Zeitbuchungs-Protokoll (S1): Die Datei des Tages von `at` bekommt Minuten und neuen Stempel in **einem** Schreibvorgang (bzw. bei gleichem Tag zusammen mit dem Entfernen des alten Stempels).
- 24-h-Regel: `at` liegt nach dem Beginn der laufenden (höchstens 24 h alten) Messung, der neue Stempel ist also nie veraltet.
- UI (Entscheidung 2026-10-25): **Zwei Knöpfe.** „Wechseln zu „X“ …“ öffnet **immer** einen Dialog mit Uhrzeit-Wahl (TimePicker, vorbelegt mit jetzt; die aktuelle Uhrzeit ist also auch dort wählbar). Daneben ein **Mini-Knopf** (Symbol, Tooltip „Sofort wechseln“) für den Wechsel jetzt ohne Dialog. Die gewählte Uhrzeit wird wie beim Abbrechen über `end_from_time` (heute bzw. Vortag) zum Zeitpunkt.
- Mehrere nachgetragene Wechsel nacheinander gehen (jeder nach dem vorigen).
- `GRENZE(Wechsel nachtragen)`: Ein Wechsel **vor** einem schon eingetragenen Wechsel ist nicht möglich (dafür müssten gebuchte Minuten geändert werden); Korrektur dann über *Backups* bzw. von Hand im YAML-Kopf.

**Tests:** Wechsel in der Vergangenheit bucht die alte Tätigkeit bis `t` und startet die neue um `t`; `t` ≤ Beginn und `t` in der Zukunft werden abgelehnt; `t` vor Mitternacht bei jetzt nach Mitternacht (neuer Stempel in der gestrigen Datei, Minuten geteilt); Absturz vor jedem Schritt → genau einmal gebucht; Dialog Jetzt/Uhrzeit in der Oberfläche.

**Entschieden (2026-10-25):** Bedienung mit Dialog-Knopf und Mini-Knopf (siehe UI). **Bewusst kein „Start nachtragen“:** Das Starten der Zeitmessung soll immer Teil der Arbeitsstart-Routine sein (Nutzerentscheidung) – also bitte auch später nicht nachrüsten. Nur Wechseln bekommt die Uhrzeit-Wahl; Stoppen mit Uhrzeit gibt es schon über „Messung abbrechen → Endzeit wählen“.

**Umgesetzt (2026-10-25).** Dabei gefunden und behoben: Beim Wechsel in eine **andere** Tagesdatei (z. B. Start 22:00, Wechsel nach Mitternacht – auch beim Sofort-Wechsel) hielt die Zeitbuchung den im eigenen Stempel-Schritt entfernten Stempel für „anderswo beendet“ und setzte den neuen Stempel nicht.
