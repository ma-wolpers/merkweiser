# Merkweiser – Konzept

> **Herkunft:** Bereinigte Fassung des ursprünglichen Konzepts (Datei
> `plan Notizverwaltung.md` im Geschwister-Repo `../tools4school`; dort sind
> versehentlich zwei Fassungen ineinander geraten, maßgeblich ist die neue,
> die hier unverändert übernommen ist). Der Name „Merkweiser“ wurde am
> 2026-10-08 festgelegt. Alle seitdem getroffenen Entscheidungen und
> Präzisierungen stehen in [PLAN.md](PLAN.md); bei Abweichungen gilt PLAN.md.

## Konzept

Ein Programm, mit dem ich meine Notizen verwalten kann – mit Oberfläche sowohl für den Computer (Desktop-GUI, z. B. mit bw-gui/Contract) als auch für das Handy (als APK, analog zu Namensfit).

Die Notizen werden in Markdown geschrieben und die Todos sind direkt Bestandteil der Notizen.

Das Programm soll sowohl auf dem Computer als auch auf dem Handy laufen. Die Notizen sollen ausschließlich lokal gespeichert werden und z. B. über Syncthing zwischen Geräten synchronisiert werden können.

### Grundprinzip: Markdown bleibt die Wahrheit

Die Markdown-Dateien sind die **alleinige Quelle der Wahrheit**.

Die Anwendung ist eine bidirektionale Oberfläche auf diesen Dateien:

```text
Markdown-Dateien
      ↕
  Anwendung
      ↕
Benutzeroberfläche
```

Die Dateien müssen jederzeit auch außerhalb der Anwendung, insbesondere mit Obsidian, bearbeitet werden können.

Daraus folgen insbesondere:

* Die Anwendung darf keine für die Funktion notwendigen Informationen ausschließlich in einer separaten Datenbank speichern.
* Alles, was die Anwendung an Notizen und Todos benötigt, muss aus den Markdown-Dateien rekonstruiert werden können.
* Änderungen an den Dateien außerhalb der Anwendung sind normale und unterstützte Änderungen und müssen beim nächsten Einlesen berücksichtigt werden.
* Die Anwendung soll die Markdown-Dateien bei Änderungen möglichst minimal verändern und keine unnötige Formatierung oder Umstrukturierung vornehmen.
* Markdown-Inhalte, die die Anwendung nicht selbst interpretiert, sollen erhalten bleiben.
* Es gibt keine proprietäre Notiz-ID oder andere versteckte Identität, die zum Erkennen einer Notiz benötigt wird.

---

### Speicher

* Die Notizen liegen lokal auf dem Gerät, um Datenschutz zu gewährleisten.
* Die Notizen liegen in Markdown vor.
* Der Benutzer kann den Ordner festlegen, in dem die Notizen gespeichert werden.
* Die Dateien können mit anderen Programmen, insbesondere Obsidian, bearbeitet werden.
* Eine externe Synchronisation wie Syncthing wird nicht durch die Anwendung selbst bereitgestellt oder kontrolliert. Die Anwendung arbeitet einfach mit dem entsprechenden lokalen Ordner.
* Cloud-Speicherung und ein eigener Synchronisationsserver sind nicht Bestandteil des Programms.

#### Dateistruktur

Die Notizen sind nach dem Datum strukturiert und folgen standardmäßig einer entsprechenden Namensstruktur, z. B.:

```text
YYYY-MM-DD.md
```

Beispiel:

```text
2026-10-08.md
2026-10-09.md
2026-10-10.md
```

Eine Datei enthält alle Notizen dieses Tages.

Mehrere Notizen innerhalb derselben Tagesdatei werden durch mindestens eine Zeile mit `---` getrennt.

Beispiel:

```markdown
Notiz vom Vormittag

- Inhalt

---

Notiz vom Nachmittag

- Inhalt
```

Die Anwendung muss die Notizen nicht dauerhaft als eigene Objekte speichern. Eine Notiz ist vielmehr ein durch die Markdown-Struktur abgegrenzter Bereich einer Datei.

---

### Struktur einer Notiz

Eine Notiz besteht aus beliebig vielen:

* Themen
* Teilpunkten
* Todos
* verschachtelten Teilpunkten und Todos
* sonstigen Markdown-Inhalten

Alle diese Bestandteile können vorhanden sein, müssen es aber nicht.

Beispiel:

```markdown
Notiz-Thema (worum geht es?)

- teilpunkt

  - [ ] offenes todo des Teilpunkts

    - [ ] offenes teil-todo

- ==teilpunkt==

- [ ] offenes todo

  - [ ] offenes teil-todo

- [ ] ==offenes dringendes todo==

weiteres Thema zur gleichen Notiz

- [x] erledigtes todo

- [ ] todo mit tag #tagname
```

Dabei gilt:

* `- [ ]` bezeichnet ein offenes Todo.
* `- [x]` bezeichnet ein erledigtes Todo.
* Die Einrückung bestimmt die Verschachtelung.
* `==...==` markiert bei einem Todo ein dringendes Todo.
* `#tagname` markiert einen Tag.
* Markdown-Links, Bilder und sonstige Markdown-Inhalte sind erlaubt.
* Es ist nicht erforderlich, dass eine Notiz ein bestimmtes Mindestformat oder bestimmte Bestandteile enthält.

#### Tags und implizite Tags

Ein Tag kann an einem Thema angegeben werden:

```markdown
Notiz-Thema (worum geht es?) mit einem tag #tagname

- teilpunkt

- [ ] offenes todo

- [x] erledigtes todo

- [ ] todo mit zusätzlichem tag #anderertagname

anderes Thema zur gleichen Notiz ohne den Tag

- teilpunkt ohne den Tag
```

Ein an einem Thema angegebener Tag gilt implizit für die dazugehörigen nachfolgenden Teilpunkte und Todos.

Ein explizit am einzelnen Teilpunkt oder Todo angegebener Tag kommt zusätzlich zu den implizit übernommenen Tags hinzu.

Beginnt ein neues Thema ohne diesen Tag, endet die implizite Vererbung des vorherigen Tags.

Damit können beispielsweise alle folgenden Elemente automatisch mit `#tagname` gefiltert werden, obwohl der Tag nur einmal im Themenkopf steht.

---

## Funktionen

### 1. Notizen anzeigen, erstellen, bearbeiten und löschen

#### 1.a Notizen anzeigen

Die Anwendung zeigt die vorhandenen Notizen strukturiert an.

Dabei soll die Darstellung der in Markdown vorhandenen Struktur folgen:

* Themen
* Teilpunkte
* verschachtelte Teilpunkte
* Todos
* Erledigungsstatus
* Dringlichkeit
* Tags
* sonstige Markdown-Inhalte

Die Darstellung ist eine alternative Ansicht auf den vorhandenen Markdown-Inhalt und ersetzt diesen nicht.

Es soll möglich sein, entweder einzelne Tagesdateien oder daraus gefilterte Notizen anzuzeigen.

Beim Öffnen einer Datei werden immer die tatsächlich aktuell vorhandenen Markdown-Dateien gelesen. Änderungen, die z. B. zuvor in Obsidian vorgenommen wurden, werden dadurch automatisch berücksichtigt.

Markdown-Links und Bilder werden unterstützt und erhalten, aber nicht als Link- bzw. Bildvorschau dargestellt.

#### 1.b Notizen erstellen

Notizen werden immer in der Datei mit dem aktuellen Datum erstellt.

Falls keine Datei für das aktuelle Datum existiert, wird sie erstellt.

Falls bereits eine Datei existiert, wird die neue Notiz an das Ende der Datei angehängt.

Zwischen einer bereits vorhandenen Notiz und der neuen Notiz wird die erforderliche Trennlinie `---` eingefügt.

Die neu erstellte Notiz enthält nur die vom Benutzer eingegebenen Inhalte; es wird kein proprietärer Metadatenblock erzeugt.

#### 1.c Notizen bearbeiten

Notizen können innerhalb der Anwendung bearbeitet werden.

Bearbeitungen werden direkt in die zugehörige Markdown-Datei geschrieben.

Die Anwendung soll dabei möglichst genau die bestehende Markdown-Struktur erhalten und nur die tatsächlich geänderten Stellen verändern.

Insbesondere sollen:

* unbekannte Markdown-Inhalte erhalten bleiben,
* Links und Bilder erhalten bleiben,
* manuell in Obsidian vorgenommene Formatierungen erhalten bleiben,
* Einrückungen und sonstige vom Benutzer angelegte Struktur nicht unnötig verändert werden.

Eine Bearbeitung der Datei außerhalb der Anwendung, z. B. in Obsidian, darf nicht dazu führen, dass die Anwendung eine alte interne Version bevorzugt.

#### 1.d Notizen löschen

Eine Notiz kann aus einer Tagesdatei gelöscht werden.

Dabei wird ausschließlich der betreffende Notizbereich entfernt.

Die übrigen Notizen der Datei bleiben erhalten.

Überflüssige Trennlinien `---`, die durch das Löschen entstehen, sollen aufgeräumt werden, ohne den übrigen Markdown-Inhalt unnötig zu verändern.

---

## 2. Todos verwalten

Todos sind keine separaten Objekte neben den Notizen, sondern Bestandteil der Markdown-Dateien.

Ein Todo wird anhand der Markdown-Syntax erkannt:

```markdown
- [ ] offenes Todo
- [x] erledigtes Todo
```

Die Anwendung soll Todos unabhängig von ihrer ursprünglichen Notiz anzeigen und verwalten können.

#### Funktionen

* Todos aus allen Notizen anzeigen
* Todos nach Status filtern
* neues Todo zu einer Notiz hinzufügen
* Todo als erledigt/offen markieren
* Todo als dringend markieren
* Todo einem Projekt zuordnen
* Todo auf ein späteres Datum verschieben
* Todo wieder in seiner ursprünglichen Notiz bearbeiten

#### Dringlichkeit

Ein dringendes Todo wird durch `==...==` markiert:

```markdown
- [ ] ==dringendes Todo==
```

Das Markieren als dringend darf ausschließlich diese Markdown-Darstellung verändern und benötigt keinen zusätzlichen internen Zustand.

#### Erledigung

Das Erledigen eines Todos verändert die Checkbox:

```markdown
- [ ] Todo
```

wird zu:

```markdown
- [x] Todo
```

und umgekehrt.

#### Verschieben auf ein späteres Datum

Wird ein Todo auf ein anderes Datum verschoben, wird es aus seinem bisherigen Kontext entfernt und in den Markdown-Bestand des Zieldatums übernommen.

Die Aktion darf keine für Markdown unsichtbare oder ausschließlich intern gespeicherte Information erzeugen.

Die genaue Positionierung des verschobenen Todos innerhalb der Zieldatei wird so gewählt, dass der Inhalt weiterhin sinnvoll als Markdown-Notiz dargestellt werden kann.

#### Projekte

Todos können Projekten zugeordnet werden und danach nach Projekt gefiltert werden.

Die konkrete Markdown-Syntax für Projekte muss mit den übrigen Markdown-Regeln kompatibel sein und wird so gewählt, dass die Projektzugehörigkeit auch außerhalb der Anwendung eindeutig lesbar und bearbeitbar bleibt.

---

## 3. Notizen durchsuchen und filtern

Die Anwendung kann alle vorhandenen Markdown-Dateien durchsuchen.

Die Suche soll sowohl nach freiem Text als auch nach strukturellen Eigenschaften möglich sein.

Mögliche Filter:

* freier Suchtext
* Datum
* Zeitraum
* Tag
* impliziter Tag
* Projekt
* Todo offen/erledigt
* dringend/nicht dringend

Bei Tags muss die implizite Tag-Vererbung berücksichtigt werden.

Beispiel:

```markdown
Thema #uni

- Teilpunkt

- [ ] Todo
```

Das Todo muss bei einer Suche nach `#uni` gefunden werden, obwohl das Tag nicht direkt am Todo steht.

Die Suchfunktion arbeitet immer auf den tatsächlichen Markdown-Dateien und nicht auf einem davon unabhängigen Datenbestand.

Eine lokale Suchindexierung ist nur zulässig, wenn sie vollständig aus den Dateien rekonstruiert werden kann und niemals die Quelle der Wahrheit darstellt.

---

## 4. Einstellungen

#### Speicherort

Der Benutzer kann den Ordner auswählen, in dem die Markdown-Dateien liegen.

Die Anwendung arbeitet anschließend direkt mit diesem Ordner.

#### Dateinamensstruktur

Standardmäßig werden Tagesdateien nach folgendem Schema benannt:

```text
YYYY-MM-DD.md
```

Die Konfiguration der Namensstruktur soll grundsätzlich möglich sein, sofern sich daraus das Datum eindeutig ableiten lässt.

Die Anwendung darf dabei niemals zusätzliche Dateien oder Datenbanken benötigen, um den Zusammenhang zwischen Datei und Datum herzustellen.

#### Weitere mögliche Einstellungen

* Standardposition für neue Notizen
* Verhalten bei Änderungen während des Bearbeitens
* Einstellungen zur Konfliktbehandlung
* Sicherung/Versionierung vor automatischen Merges
* Darstellungsoptionen der Oberfläche

Einstellungen, die ausschließlich die Benutzeroberfläche betreffen, müssen den Markdown-Bestand nicht verändern.

---

## 5. Automatisches Merging von Notizen

Die Anwendung soll mit Markdown-Dateien arbeiten können, die über Syncthing oder eine andere externe Dateisynchronisation verändert wurden.

Dabei können Konflikte entstehen, wenn dieselbe Datei auf mehreren Geräten unabhängig verändert wurde.

### Grundprinzip

Die Anwendung versucht, Änderungen möglichst auf Markdown-/Text-Ebene zusammenzuführen.

Sie muss dafür keine Notizen anhand einer künstlichen ID wiedererkennen.

Stattdessen wird die tatsächliche Struktur und der Textinhalt der Dateien verwendet.

Beispiel:

Ausgangsversion:

```markdown
Notiz

- [ ] Aufgabe A
```

Gerät 1:

```markdown
Notiz

- [ ] Aufgabe A
- [ ] Aufgabe B
```

Gerät 2:

```markdown
Notiz

- [ ] Aufgabe A
- [ ] Aufgabe C
```

kann automatisch zusammengeführt werden zu:

```markdown
Notiz

- [ ] Aufgabe A
- [ ] Aufgabe B
- [ ] Aufgabe C
```

### Konflikte

Wenn zwei Änderungen nicht eindeutig zusammengeführt werden können, darf die Anwendung niemals stillschweigend eine der Änderungen verwerfen.

Stattdessen muss sie den Konflikt sichtbar machen.

Mögliche Konfliktbehandlung:

* Konflikt in der Oberfläche anzeigen
* beide Versionen nachvollziehbar darstellen
* eine manuelle Entscheidung ermöglichen
* vor dem Merge eine Sicherung der ursprünglichen Datei anlegen

Das Ziel ist:

> Lieber ein sichtbarer Konflikt als unbemerkter Datenverlust.

### Externe Änderungen

Auch Änderungen, die nicht über Syncthing, sondern direkt in Obsidian oder einem anderen Editor vorgenommen wurden, müssen erkannt werden.

Wenn eine Datei während der Benutzung der Anwendung verändert wurde, muss die Anwendung die externe Änderung berücksichtigen und darf nicht einfach ihre alte interne Version darüber speichern.

---

## Nicht enthalten

Die Anwendung enthält zunächst ausdrücklich nicht:

* Cloud-Speicherung
* eigenen externen Synchronisationsdienst
* Benutzerkonten
* serverseitige Datenhaltung
* Markdown-Link-Vorschauen
* Bildvorschauen
* eine proprietäre Datenbank als Quelle der Wahrheit
* eine zwingend erforderliche proprietäre Markdown-Syntax
* eine künstliche Identität für Notizen, die außerhalb der Anwendung nicht existiert

---

## Plattformen

Die Anwendung soll auf zwei Plattformen verfügbar sein:

### Desktop

Eine Desktop-GUI, vorgesehen auf Basis von bw-gui/Contract.

### Android

Eine Android-App als APK, analog zum Ansatz von Namensfit.

Beide Oberflächen greifen auf dieselbe fachliche Logik zurück:

```text
                 gemeinsame Core-Logik
                 ┌───────────────────┐
                 │ Markdown lesen    │
                 │ Markdown schreiben │
                 │ Notizen erkennen  │
                 │ Todos erkennen    │
                 │ Tags              │
                 │ Suche/Filter      │
                 │ Merge             │
                 └─────────┬─────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
         Desktop-GUI               Android-App
```

Die Core-Logik kennt keine Cloud und keine plattformspezifische Datenhaltung.

---

## Leitprinzipien

1. **Markdown-Dateien sind die Wahrheit.**
2. **Die Anwendung ist vollständig bidirektional.**
3. **Alles, was die Anwendung kann, muss auch auf Markdown-Ebene nachvollziehbar sein.**
4. **Obsidian und andere Markdown-Editoren bleiben gleichberechtigte Werkzeuge.**
5. **Es gibt keine versteckte Notiz-ID und keine notwendige proprietäre Datenbank.**
6. **Externe Änderungen werden akzeptiert und eingelesen.**
7. **Automatische Merges dürfen niemals stillschweigend Daten verlieren.**
8. **Die Anwendung soll vorhandenes Markdown so wenig wie möglich verändern.**

## Wichtigste Designentscheidung

Die Anwendung ist **kein System, das Markdown-Dateien exportiert**.

Sie ist ein Programm, das **direkt auf einem vom Benutzer kontrollierten Markdown-Bestand arbeitet**.

Die Dateien könnten jederzeit ohne die Anwendung weiterverwendet werden.
