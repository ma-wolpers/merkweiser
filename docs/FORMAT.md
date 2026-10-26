# Wie Merkweiser deine Notizen liest

Diese Seite ist die verbindliche Grammatik. Parser (`blocks.py`, `outline.py`, `inline.py`, `tags.py`) und Tests richten sich danach. Weicht der Code davon ab, ist das ein Fehler im Code.

Grundsatz: **Merkweiser liest deine Markdown-Dateien, schreibt sie aber nie neu.** Was es nicht versteht, bleibt Byte für Byte erhalten. Es ändert nur die Zeilen, die du in Merkweiser bearbeitest.

## Dateien

- Eine Tagesdatei heißt standardmäßig `YYYY-MM-DD.md`, z. B. `2026-10-08.md`. Das Muster ist einstellbar, solange Jahr, Monat und Tag darin eindeutig vorkommen.
- Der **ganze Dateiname** muss dem Muster entsprechen. `2026-10-08 Elternabend.md` ist also keine Tagesdatei und wird ignoriert.
- Merkweiser sucht auch in Unterordnern. Gibt es zu einem Datum mehrere Dateien, zeigt es alle an und markiert sie als **Dublette**. Neue Notizen landen in der einzigen vorhandenen Datei. Gibt es noch keine, entsteht eine neue im Notizordner. Gibt es mehrere, fragt Merkweiser nach.
- **Encoding:** Merkweiser liest und schreibt UTF-8 mit und ohne BOM. Andere Dateien zeigt es nur an und durchsucht sie, ändert sie aber nie, und markiert sie mit einem Hinweis.
- Zeilenenden (LF/CRLF, auch gemischt) und ein fehlender Schluss-Zeilenumbruch bleiben erhalten.

## Notizen

*Geändert am 2026-10-21: Vorher trennte nur `---` Notizen; Leerzeilen gehörten zur Notiz.*

- Eine Datei enthält beliebig viele Notizen.
- **Jede Leerzeile beendet eine Notiz.** Eine Notiz ist also ein Block von Zeilen ohne Leerzeile dazwischen.

  ```markdown
  Notiz vom Vormittag
  - Inhalt

  Notiz vom Nachmittag

  - [ ] dieses Todo ist eine eigene Notiz (ohne Thema)
  ```

- Einzige Ausnahme: Leerzeilen **in einem Codeblock** beenden die Notiz nicht.
- Eine Zeile, die nur `---` enthält, ist ein **Trenner**: Sie beendet die Notiz und wird nicht angezeigt, auch direkt unter Text. Merkweiser schreibt selbst keine Trenner mehr; vorhandene bleiben stehen.
- Leere Notizen gibt es nicht. Leerzeilen und Trenner am Stück erzeugen keine Notiz.
- **Frontmatter:** Beginnt die Datei mit `---`, ist alles bis zur nächsten `---`- oder `...`-Zeile Frontmatter. Das ist keine Notiz. Merkweiser verändert darin **nur seine eigenen Schlüssel** `zeit_*`, `messung_start` und `messung_taetigkeit` (Zeiterfassung, siehe unten); alles andere bleibt Zeichen für Zeichen erhalten.
- Merkweiser schreibt eine neue Notiz mit genau einer Leerzeile davor.
- **Folge für ältere Dateien:** Die Dateien bleiben unverändert, werden aber neu gelesen. Steht zwischen einem Thema und seinen Todos eine Leerzeile, sind das jetzt getrennte Notizen, und die Todos erben die Tags des Themas nicht mehr. Dasselbe gilt für „lockere“ Listen mit Leerzeilen zwischen den Punkten: Jeder Punkt ist eine eigene Notiz, Verschachtelung über Leerzeilen hinweg gibt es nicht.

## Codeblöcke

- Ein Codeblock beginnt mit mindestens drei Backticks oder Tilden und endet mit **demselben Zeichen in mindestens derselben Anzahl**. Eine kürzere Folge ```` ``` ```` innerhalb eines ```` ```` ````-Blocks schließt ihn also nicht.
- Im Codeblock gibt es keine Trenner, Notizgrenzen, Tags, Todos oder Themen. Er bleibt unverändert.
- Ein nicht geschlossener Codeblock reicht bis zum Dateiende, wie in Obsidian.
- **GRENZE:** Mit vier Leerzeichen eingerückter Code ohne Backticks gilt nicht als Codeblock.

## Aufbau einer Notiz

Merkweiser ordnet jede Zeile einer Klasse zu (bei Überschneidung gewinnt die obere):

1. **Listenpunkt:** beginnt mit `-`, `*`, `+`, `1.` oder `1)`.
2. **Fortsetzung:** eine Zeile direkt unter einem Listenpunkt (oder unter dessen Fortsetzung), **eingerückt oder nicht**; sie gehört zu diesem Punkt und beginnt kein Thema. Ausgenommen sind Zeilen der Klasse „Sonstiges“ ohne Einrückung.
3. **Sonstiges:** Zitate `>`, Tabellen `|`, HTML `<`, Zeilen nur mit Bild bzw. Embed, eingerückter Text ohne Punkt. Sie bleiben erhalten, beginnen aber nie ein Thema.
4. **Text** auf Ebene 0 (ohne Einrückung).

**Überschriften sind gewöhnlicher Text** (geändert am 2026-10-21): `## Woche #w` wird angezeigt, wie es dasteht, und behandelt wie jede andere Textzeile. `#w` darin ist ein normaler Tag. Eine `===`-Unterstreichung ist ebenfalls Text; `---` direkt unter Text ist ein Trenner.

### Thema

- **Jede Notiz hat höchstens ein Thema:** die Textzeilen am Anfang der Notiz, vor dem ersten Listenpunkt. Mehrere solche Zeilen bilden zusammen das Thema (die zweite und weitere sind „Erläuterung“).

  ```markdown
  Elternabend #schule        ← Thema
  Vorher Raum klären.        ← Erläuterung (gehört zum Thema)
  - [ ] Beamer reservieren   ← erbt #schule
  noch zum Beamer            ← Fortsetzung des Punkts darüber
  - [ ] Kopien               ← erbt #schule

  Neues Thema                ← neue Notiz, neues Thema
  - [ ] Stühle               ← erbt #schule nicht
  ```

- Nach dem ersten Listenpunkt beginnt nie ein Thema. Text, der nicht direkt unter einem Punkt steht (etwa nach einem Zitat), bleibt als „Sonstiges“ in der Notiz.
- Beginnt eine Notiz mit einem Listenpunkt, hat sie **kein Thema**. Das ist z. B. bei einem einzelnen Todo zwischen Leerzeilen der Fall.
- **Leeres Thema:** Eine Themenzeile, die außer Tags und Leerraum nichts enthält oder nur `...` (bzw. `…`), ist ein leeres Thema, z. B. `...`, `#schule` oder `... #schule`. Die Notiz *hat* damit ein Thema: Erläuterungszeilen darunter sind möglich, und die Tags gelten und vererben sich wie bei jedem Thema. Angezeigt wird „kein Thema“ samt den Tags. Ein `#` in Code oder Links ist kein Tag; ``#a `code` `` ist also kein leeres Thema.
- **Tag-Thema:** ein leeres Thema mit mindestens einem Tag (z. B. `#schule`).
- Themen werden über ihre getrimmte Zeile verglichen (`…` zählt als `...`), ohne weitere Normalisierung.

### Einrückung

- Die Einrückung bestimmt die Verschachtelung. Eltern eines Punkts ist der nächste Punkt darüber mit kleinerer Einrückung in derselben Notiz.
- **Tabs** springen zur nächsten Spalte, die ein Vielfaches von 4 ist (Tabstopps 4, 8, 12 …). Tabs und Leerzeichen dürfen gemischt werden; verglichen wird die errechnete Spalte. Die Zeichen selbst bleiben unverändert.
- **GRENZE:** Ein eingerückter Punkt ohne passenden Elternpunkt wird flach unter dem Thema angezeigt; seine Einrückung bleibt in der Datei erhalten.

## Todos

| Schreibweise | Bedeutung |
|---|---|
| `- [ ] Text` | offenes Todo |
| `- [x] Text` oder `- [X] Text` | erledigtes Todo. Merkweiser schreibt `[x]`; ein vorhandenes `[X]` bleibt beim Bearbeiten stehen. |
| `- [ ] ==Text==` | **dringend (Gelb)**: Der Inhalt beginnt mit einer `==…==`-Markierung. |
| `- [ ] ==🔴Text==` | **sehr dringend (Rot)**, *Geändert am 2026-10-26 auf Nutzerwunsch (W7):* Nach dem öffnenden `==` steht 🔴; beim Lesen ist **ein** Leerzeichen danach erlaubt (`==🔴 Text==`), Merkweiser schreibt ohne. Obsidian zeigt beides als Hervorhebung. Geschlossen wird am ersten `==` nach dem Textbeginn; `==🔴==` ohne weiteren Text gilt als Gelb mit dem Text „🔴“. Text, der selbst `==` enthält, kann Merkweiser nicht markieren. **GRENZE:** Beginnt der Text selbst mit 🔴, wird Gelb als Rot gelesen. |
| `- [-] Text`, andere Zeichen | **GRENZE:** wird als normaler Listenpunkt behandelt und bleibt unverändert. |

## Tags und Projekte

- Ein **Tag** ist `#name` wie in Obsidian. Rein numerische Tags (`#2026`) gelten nicht als Tags. In Inline-Code, Link-URLs und `[[Wikilinks]]` wird nicht nach Tags gesucht.
- Ein **Projekt** ist ein verschachtelter Tag mit einstellbarem Präfix, standardmäßig `#projekt/<name>`, z. B. `#projekt/umzug`.
  - „Projekt setzen“ ersetzt **alle** Projekt-Tags direkt in der Todo-Zeile durch genau eines, bzw. entfernt sie.
  - Geerbte Projekte wirken zusätzlich und werden als „geerbt“ angezeigt.
- **Vererbung:** Ein Eintrag hat seine eigenen Tags (inklusive seiner Fortsetzungszeilen), die seiner Elternpunkte (entlang der Einrückung) und die des Themas seiner Notiz (inklusive Erläuterung). Vererbung endet an der Notizgrenze, also an jeder Leerzeile.
- **Suche:** Tag- und Projektfilter prüfen diese *effektiven* Tags. Mehrere Tags werden standardmäßig mit UND verknüpft; ODER lässt sich umschalten.

## Was Merkweiser selbst schreibt

- **Neue Notiz:** Sie wird an die Tagesdatei von heute angehängt, mit einer Leerzeile davor (kein `---`). Es entsteht kein Metadatenblock. Enthält dein Text Leerzeilen, entstehen daraus mehrere Notizen.
- **Zeiterfassung:** nur die eigenen Schlüssel im Frontmatter (siehe „Zeiterfassung im Frontmatter“).
- **Notiz löschen:** Die Notiz verschwindet samt einer angrenzenden Lücke (Leerzeilen, alte Trenner), sodass keine doppelten Leerzeilen zurückbleiben.
- **Leere Tagesdateien** (nur Leerzeichen, Tabs, Zeilenumbrüche und `---`) entfernt Merkweiser beim Start über das sichere Löschprotokoll, mit Backup. Nicht entfernt werden Dateien mit BOM, mit Frontmatter oder mit offenem Konflikt.
- **Todo verschieben:** Merkweiser schreibt **keinen** Herkunftsvermerk. Zusammenhänge behältst du über Tags bzw. Projekttags.
  - **Ganze Notiz:** Ist das Todo das einzige der Notiz (alle Todos, auch erledigte, stehen in seinem Teilbaum), wandert die ganze Notiz und verschwindet am alten Tag.
  - **Einzelnes Todo:** Sonst wandert das Todo samt Unterpunkten, mit der Themenzeile der Notiz darüber. Bei leerem Thema (`...`, `#schule`) wird keine Themenzeile kopiert. Geerbte Tags werden ausdrücklich an das Todo geschrieben, außer denen, die die mitgeschriebene Themenzeile schon trägt.
  - **Zusammenführen:** Gibt es am Zieltag **genau eine** Notiz mit gleichem Thema (normales Thema oder Tag-Thema), kommt das Todo unten an diese Notiz. Eine ganze Notiz wird so eingefügt: ihre Erläuterung unter die Erläuterung der Zielnotiz, vor deren ersten Listenpunkt (hat sie keinen: ans Ende), der übrige Inhalt unten an die Zielnotiz. Ohne Thema, mit reinem `...` oder bei mehreren passenden Notizen entsteht eine neue Notiz.
  - Verschieben auf denselben Tag wird abgelehnt.
  - **Gemeinsamer Tag (optional):** Hat die Notiz weitere Todos, bietet Merkweiser vor dem Verschieben einen Tag an. *Geändert am 2026-10-26 auf Nutzerwunsch (W7):* **nicht**, wenn das Todo schon einen Tag von Thema oder Überpunkt erbt (auch einen Projekttag); dieser geerbte Tag wird beim Verschieben ohnehin an das Todo geschrieben. Er wird an das Todo **und** an seinen Überpunkt geschrieben (Eltern-Punkt bzw. Themenzeile). Hat die Notiz kein Thema und steht das Todo auf oberster Ebene, wird `#tag` als neue Themenzeile eingefügt (Tag-Thema). Vorhandene Tags werden nicht verdoppelt. Ein Projekttag wird nur geschrieben, wenn Todo und Überpunkt noch kein anderes Projekt haben; Projekte werden nie ersetzt.
  - Ältere Notizen `Verschoben aus [[…]]` sind gewöhnliche Notizen mit diesem Thema.
- **Notiz verschieben** (W7, 2026-10-26): Die ganze Notiz wandert unverändert, wie beim alleinigen Todo: Gibt es am Zieltag **genau eine** Notiz mit gleichem Thema, wird zusammengeführt (Erläuterung vor deren ersten Punkt, übriger Inhalt unten), sonst entsteht eine neue Notiz. Am alten Tag verschwindet sie samt einer angrenzenden Lücke. Hat sich die Notiz inzwischen geändert oder steht sie doppelt in der Datei, wird nichts verschoben.
- **Konfliktdateien:** Syncthing legt bei gleichzeitigen Änderungen `NAME.sync-conflict-YYYYMMDD-HHMMSS-GERÄT.md` an.
  - Kann Merkweiser eine eigene Änderung nicht sicher schreiben, legt es eine Konfliktdatei derselben Form an, mit der Gerätekennung `MERKWEISER…`.
  - Hast du über einen Konflikt entschieden, die Auflösung ist aber noch nicht abgeschlossen, endet die Kennung auf `…MWENTSCHIEDEN`.
  - Merkweiser schreibt **nie** Konfliktmarker in deine Notizen.
- Hilfsdateien `.NAME.mw-*.tmp`/`.old`/`.partial` existieren nur während eines Schreibvorgangs. Trag `.*.mw-*` in die `.stignore` von Syncthing ein.

## Zeiterfassung im Frontmatter

Der Zeit-Tracker speichert Arbeitszeit in der Tagesdatei, flach und in ganzen Minuten:

```yaml
---
zeit_Orga: 90
zeit_Unterricht Mathe: 45
messung_start: 2026-10-22T08:15:00+02:00
messung_taetigkeit: Orga
---
```

- `zeit_<Tätigkeit>: <Minuten>` ist die Summe dieser Tätigkeit an diesem Tag.
- `messung_start` (Zeitpunkt mit Zeitzonen-Offset) und `messung_taetigkeit` bilden zusammen den Stempel einer laufenden Messung. Er steht in der Tagesdatei des Tages, an dem die Messung begann. Nur einer der beiden Schlüssel, doppelte Schlüssel oder ungültige Werte gelten als beschädigt; Merkweiser zeigt das an und verbucht nichts.
- Fehlen Tagesdatei oder Frontmatter, legt Merkweiser sie an. Wird das Frontmatter durch Merkweiser leer, entfernt er es wieder.
- **Tätigkeitsnamen** bestehen aus Buchstaben (auch Umlaute, Akzente, ß), Ziffern, `-`, `_` und einzelnen Leerzeichen, 1–40 Zeichen. Andere Zeichen (z. B. `:`, `#`, Anführungszeichen, Zeilenumbrüche) sind nicht erlaubt, damit das YAML gültig bleibt. Von Hand eingetragene Namen außerhalb dieser Regel zeigt Merkweiser nur an; du kannst sie in einen gültigen Namen umbenennen.
- **Sicher lesbar** muss das Frontmatter sein, bevor Merkweiser etwas einträgt: Jede Zeile ohne Einrückung ist `schlüssel: wert`, Listen (`- …`), eingerückte Blöcke und Mehrzeiler (`|`, `>`) sind erlaubt. Kommentare (`#`), Schlüssel in Anführungszeichen, doppelte Schlüssel, Tabulatoren am Zeilenanfang oder ein fehlendes schließendes `---` machen den Kopf „nicht sicher lesbar“: Dann trägt Merkweiser keine Zeit ein und meldet das, statt etwas umzuschreiben.

## Doppelte Notizen

Steht eine Notiz mit genau denselben Zeilen (Zeilenenden LF/CRLF zählen nicht, sonst keine Normalisierung) in mindestens zwei verschiedenen Tagesdateien, meldet Merkweiser sie unter *Einstellungen → Konflikte*. Du wählst, welche Fundstelle bleibt; die anderen werden gelöscht (mit Backup). Gleiche Notizen innerhalb derselben Datei werden nicht gemeldet.
