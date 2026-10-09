# Wie Merkweiser deine Notizen liest

Diese Seite ist die verbindliche Grammatik. Parser (`blocks.py`, `outline.py`, `inline.py`, `tags.py`) und Tests richten sich danach. Weicht der Code davon ab, ist das ein Fehler im Code.

Grundsatz: **Merkweiser liest deine Markdown-Dateien, schreibt sie aber nie neu.** Was es nicht versteht, bleibt Byte für Byte erhalten. Es ändert nur die Zeilen, die du in Merkweiser bearbeitest.

## Dateien

- Eine Tagesdatei heißt standardmäßig `YYYY-MM-DD.md`, z. B. `2026-10-08.md`. Das Muster ist einstellbar, solange Jahr, Monat und Tag darin eindeutig vorkommen.
- Der **ganze Dateiname** muss dem Muster entsprechen. `2026-10-08 Elternabend.md` ist also keine Tagesdatei und wird ignoriert.
- Merkweiser sucht auch in Unterordnern. Gibt es zu einem Datum mehrere Dateien, zeigt es alle an und markiert sie als **Dublette**. Neue Notizen landen in der einzigen vorhandenen Datei. Gibt es noch keine, entsteht eine neue im Notizordner. Gibt es mehrere, fragt Merkweiser nach.
- **Encoding:** Merkweiser liest und schreibt UTF-8 mit und ohne BOM. Andere Dateien zeigt es nur an und durchsucht sie, ändert sie aber nie, und markiert sie mit einem Hinweis.
- Zeilenenden (LF/CRLF, auch gemischt) und ein fehlender Schluss-Zeilenumbruch bleiben erhalten.

## Notizen und Trenner

- Eine Datei enthält beliebig viele Notizen.
- Ein **Trenner** ist eine Zeile `---`, vor der eine **Leerzeile** steht oder die am Notizanfang steht.

  ```markdown
  Notiz vom Vormittag
  - Inhalt

  ---

  Notiz vom Nachmittag
  ```

- `Text` direkt gefolgt von `---` (ohne Leerzeile dazwischen) ist eine **Überschrift** (Setext-H2), kein Trenner. So stellt es auch Obsidian dar.
- **Frontmatter:** Beginnt die Datei mit `---`, ist alles bis zur nächsten `---`- oder `...`-Zeile Frontmatter. Das ist keine Notiz und wird nie verändert.
- Merkweiser schreibt Trenner immer mit einer Leerzeile davor und danach.

## Codeblöcke

- Ein Codeblock beginnt mit mindestens drei Backticks oder Tilden und endet mit **demselben Zeichen in mindestens derselben Anzahl**. Eine kürzere Folge ```` ``` ```` innerhalb eines ```` ```` ````-Blocks schließt ihn also nicht.
- Im Codeblock gibt es keine Trenner, Tags, Todos oder Themen. Er bleibt unverändert.
- Ein nicht geschlossener Codeblock reicht bis zum Dateiende, wie in Obsidian.
- **GRENZE:** Mit vier Leerzeichen eingerückter Code ohne Backticks gilt nicht als Codeblock.

## Aufbau einer Notiz

Merkweiser ordnet jede Zeile einer Klasse zu (bei Überschneidung gewinnt die obere):

1. **Leerzeile**
2. **Überschrift:** `#`, `##` … mit Leerzeichen, oder Setext (Absatz mit `===`/`---` direkt darunter; **GRENZE:** mindestens 3 Zeichen). `#tag` ohne Leerzeichen ist ein Tag, keine Überschrift.
3. **Listenpunkt:** beginnt mit `-`, `*`, `+`, `1.` oder `1)`.
4. **Fortsetzung:** eine eingerückte Zeile direkt unter einem Listenpunkt; sie gehört zu diesem Punkt.
5. **Sonstiges:** Zitate `>`, Tabellen `|`, HTML `<`, Zeilen nur mit Bild bzw. Embed, eingerückter Text ohne Punkt. Sie bleiben erhalten, beginnen aber nie ein Thema.
6. **Absatz** auf Ebene 0 (ohne Einrückung).

### Themen

- Ein Absatz auf Ebene 0 beginnt ein **Thema**, wenn er der erste Absatz der Notiz bzw. unter einer Überschrift ist oder wenn seit dem letzten Thema mindestens ein Listenpunkt kam.
- Weitere Absätze *vor* dem ersten Listenpunkt sind **Erläuterung** und gehören noch zum Thema:

  ```markdown
  Elternabend #schule        ← Thema
  Vorher Raum klären.        ← Erläuterung (gehört zum Thema)
  - [ ] Beamer reservieren   ← erbt #schule
  weiteres Thema             ← neues Thema
  - [ ] Kopien               ← erbt #schule nicht
  ```

- Eine Notiz darf beliebig viele Themen haben. Listenpunkte vor dem ersten Thema gehören zu einem unsichtbaren Thema ohne Tags.
- **GRENZE:** Eine nicht eingerückte Textzeile **direkt** unter einem Listenpunkt (ohne Leerzeile) beginnt bei Merkweiser ein neues Thema, so wie im Konzeptbeispiel. Obsidian stellt sie als Fortsetzung des Punkts dar. Soll sie zum Punkt gehören, rücke sie ein.

### Überschriften

Eine Überschrift der Stufe *h* gilt bis zur nächsten Überschrift der Stufe ≤ *h* bzw. bis zum Notizende. Sie beendet das aktuelle Thema, ihre Tags gelten aber für alles darunter.

### Einrückung

- Die Einrückung bestimmt die Verschachtelung. Eltern eines Punkts ist der nächste Punkt darüber mit kleinerer Einrückung im selben Thema.
- **Tabs** springen zur nächsten Spalte, die ein Vielfaches von 4 ist (Tabstopps 4, 8, 12 …). Tabs und Leerzeichen dürfen gemischt werden; verglichen wird die errechnete Spalte. Die Zeichen selbst bleiben unverändert.
- **GRENZE:** Ein eingerückter Punkt ohne passenden Elternpunkt wird flach unter dem Thema angezeigt; seine Einrückung bleibt in der Datei erhalten.

## Todos

| Schreibweise | Bedeutung |
|---|---|
| `- [ ] Text` | offenes Todo |
| `- [x] Text` oder `- [X] Text` | erledigtes Todo. Merkweiser schreibt `[x]`; ein vorhandenes `[X]` bleibt beim Bearbeiten stehen. |
| `- [ ] ==Text==` | **dringend**: Der Inhalt beginnt mit einer `==…==`-Markierung. |
| `- [-] Text`, andere Zeichen | **GRENZE:** wird als normaler Listenpunkt behandelt und bleibt unverändert. |

## Tags und Projekte

- Ein **Tag** ist `#name` wie in Obsidian. Rein numerische Tags (`#2026`) gelten nicht als Tags. In Inline-Code, Link-URLs und `[[Wikilinks]]` wird nicht nach Tags gesucht.
- Ein **Projekt** ist ein verschachtelter Tag mit einstellbarem Präfix, standardmäßig `#projekt/<name>`, z. B. `#projekt/umzug`.
  - „Projekt setzen“ ersetzt **alle** Projekt-Tags direkt in der Todo-Zeile durch genau eines, bzw. entfernt sie.
  - Geerbte Projekte wirken zusätzlich und werden als „geerbt“ angezeigt.
- **Vererbung:** Ein Eintrag hat seine eigenen Tags, die seines Elternpunkts (entlang der Einrückung), die des aktuellen Themas (inklusive Erläuterung) und die aller umschließenden Überschriften. Ein neues Thema beendet die Themen-Vererbung.
- **Suche:** Tag- und Projektfilter prüfen diese *effektiven* Tags. Mehrere Tags werden standardmäßig mit UND verknüpft; ODER lässt sich umschalten.

## Was Merkweiser selbst schreibt

- **Neue Notiz:** Sie wird an die Tagesdatei von heute angehängt, mit Trenner. Es entsteht kein Metadatenblock.
- **Todo verschieben:** Das Todo wandert samt Unterpunkten in die Zieldatei, unter die Notiz mit dem Thema `Verschoben aus [[YYYY-MM-DD]]`. Gibt es diese Notiz schon, wird sie wiederverwendet. Geerbte Tags werden dabei ausdrücklich an das Todo geschrieben, damit Filter weiter greifen.
- **Konfliktdateien:** Syncthing legt bei gleichzeitigen Änderungen `NAME.sync-conflict-YYYYMMDD-HHMMSS-GERÄT.md` an.
  - Kann Merkweiser eine eigene Änderung nicht sicher schreiben, legt es eine Konfliktdatei derselben Form an, mit der Gerätekennung `MERKWEISER…`.
  - Hast du über einen Konflikt entschieden, die Auflösung ist aber noch nicht abgeschlossen, endet die Kennung auf `…MWENTSCHIEDEN`.
  - Merkweiser schreibt **nie** Konfliktmarker in deine Notizen.
- Hilfsdateien `.NAME.mw-*.tmp`/`.old`/`.partial` existieren nur während eines Schreibvorgangs. Trag `.*.mw-*` in die `.stignore` von Syncthing ein.
