# SCRIPTOR – Anleitung, ganz einfach erklärt

Stell dir SCRIPTOR wie ein Schreibbüro im Computer vor. Du bist der Chef: Du sagst, was für
ein Buch du willst. Ein **Schreiber** schreibt es, eine strenge **Lektorin** prüft jedes
Kapitel, und ein **Türsteher** (das Programm) entscheidet: „gut genug“ oder „nochmal“.
Alles wird ordentlich in Ordnern abgelegt.

Das Büro arbeitet mit Claude (einer KI von Anthropic). Dafür brauchst du einen
**Schlüssel** (API-Key). Den Schlüssel bezahlst du nach Verbrauch.

---

## Schritt 1: Schlüssel besorgen (einmalig, ca. 5 Minuten)

> **Ohne Schlüssel, kostenlos, offline:** Statt Claude kannst du ein lokales Modell über
> Ollama nutzen. Dann überspringst du Schritt 1 und 3 und führst einmal
> `packaging\windows\ollama.ps1` aus (Details: `docs/FRAPP_DESKTOP.md`, Abschnitt „Ollama“).
> Ehrlich: Lokale Modelle schreiben spürbar schwächer und langsamer als Claude.

1. Öffne <https://console.anthropic.com> und lege ein Konto an.
2. Lade unter **Billing** Guthaben auf. Für den Anfang reichen 10–20 €.
3. Erstelle unter **API Keys** mit **Create Key** einen Schlüssel. Er beginnt mit `sk-ant-…`.
4. Kopier ihn irgendwohin, wo nur du ihn siehst. **Teil ihn mit niemandem.**

## Schritt 2: SCRIPTOR auf Windows holen

**Weg A: fertige App (ohne Python)**

1. Öffne auf GitHub das Repo `paegechambers-star/mvp`, Reiter **Actions**.
2. Links **FraPP Windows** wählen, oben den neuesten Lauf mit grünem Haken anklicken.
3. Ganz unten unter **Artifacts** auf **FraPP-windows** klicken. Das lädt eine ZIP-Datei.
4. Die ZIP entpacken (Rechtsklick → **Alle extrahieren**), z. B. nach `C:\Programme-Eigene\Scriptor`.
5. Im Ordner `FraPP` die Datei **FraPP.exe** doppelklicken.
6. Windows warnt eventuell („Der Computer wurde durch Windows geschützt“). Das liegt daran,
   dass die App nicht signiert ist. Klick auf **Weitere Informationen → Trotzdem ausführen**.

**Weg B: mit Python** (wenn Weg A nicht klappt)

1. Python **3.12** installieren. Nicht die neueste Version: Für 3.14/3.15 gibt es noch keine
   fertigen Pakete, dann scheitert die Installation mit „Microsoft Visual C++ 14.0 required“.
   - Hast du schon den neuen Python-Installationsmanager (der Befehl `py` funktioniert),
     tippst du in PowerShell: `py install 3.12`
   - sonst: <https://www.python.org/downloads/windows/> → Python 3.12.x → beim Installieren
     **„Add python.exe to PATH“** anhaken.
2. Auf GitHub im Repo den Branch `claude/ki-agent-ghostwriter-rqxyap` wählen, dann
   **Code → Download ZIP**, und die ZIP entpacken.
3. Im entpackten Ordner in die Adresszeile des Explorers `powershell` tippen und Enter drücken.
4. Diese Zeile einfügen und Enter drücken:
   ```powershell
   PowerShell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\install.ps1
   ```
5. Danach liegt auf dem Desktop eine Verknüpfung **FraPP**. Doppelklick, fertig.

## Schritt 3: Schlüssel eintragen (einmalig)

1. In SCRIPTOR oben auf **Einstellungen** klicken.
2. Den Schlüssel ins Feld **API-Key** einfügen und **Key speichern** klicken.
3. Oben rechts steht jetzt **API-Key: keyring** statt eines roten „API-Key fehlt“.

## Schritt 4: Dein erstes Buch (Übungsrunde: ein Bilderbuch, kostet wenig)

1. Links bei **Neues Buch** ausfüllen:
   - **Titel:** „Der kleine Leuchtturm“
   - **Buchart:** Bilderbuch (3–6 Jahre)
   - **Idee:** „Ein Leuchtturm hat Angst im Dunkeln und lernt, dass sein Licht anderen hilft.“
   - **Anlegen** klicken.
2. **1 · Bible entwickeln** klicken. Die Bible ist der Steckbrief des Buchs: Figuren,
   Regeln, Ton. Unten rechts siehst du, dass gearbeitet wird. Warte, bis dort **done** steht.
3. Den Reiter **Bible** öffnen und lesen. Gefällt dir etwas nicht, änderst du es direkt im
   Text, schreibst eine **Begründung** dazu und klickst **Commit**.
4. Zurück zur **Übersicht**, dann **2 · Outline erstellen**. Das ist der Kapitelplan.
5. **3 · Schreiben** klicken. Für jedes Kapitel passiert jetzt Folgendes:
   Entwurf → Lektorat → wenn nötig Überarbeitung.
6. In der Tabelle steht danach pro Kapitel **PASS** (grün, gut) oder **REVISE** (orange,
   braucht dich).

## Schritt 5: Selbst nachbessern

1. Bei einem Kapitel auf **Öffnen** klicken.
2. Links steht der Text, rechts das **Lektorat**: was nicht passt, mit Zitat und Vorschlag.
3. Du hast zwei Möglichkeiten:
   - **Selbst ändern:** im Text tippen, dann **Als neue Version speichern**. Alte Versionen
     bleiben erhalten (oben rechts umschalten).
   - **Ändern lassen:** unten eine Anweisung schreiben, z. B. „mehr Humor, kürzere Sätze“,
     dann **Überarbeiten**.

## Schritt 6: Fertig machen

1. Reiter **Material & Export**.
2. Zum Beispiel **klappentext** oder **expose** auswählen und **Erzeugen** klicken.
3. **Word (.docx)** klicken. Unter **Dateien** erscheint dein Manuskript zum Herunterladen.
4. Alles liegt außerdem in `Dokumente\Scriptor\books\<buchname>\export`.

---

## Extras

**Deine eigene Stimme.** Unter **Quellen & Stimme** 2–3 eigene Texte als `.txt` hochladen,
zusammen mindestens 2.000 Wörter. Dann **Stimme lernen**. Ab jetzt prüft die Lektorin auch,
ob es nach dir klingt.

**Memoir oder Sachbuch.** Erst unter **Quellen & Stimme** deine Notizen bzw.
Interview-Abschriften hochladen. Der Schreiber erfindet keine Fakten. Was fehlt, markiert er
als `[FRAGE AN AUTOR: …]`. Diese Stellen musst du vor der Veröffentlichung beantworten.

**Agent (einfach sagen, was du willst).** Oben auf **Agent** klicken und z. B. schreiben:
„Leg einen YA-Roman über eine Hackerin in Hamburg an, entwickle Bible und Outline.“
Der Haken **teure Werkzeuge erlauben** muss gesetzt sein, sonst darf der Agent nichts
Kostenpflichtiges tun.

**Plugins.** Neue Fähigkeiten nachrüsten (z. B. eine neue Buchart): Datei in den
Plugin-Ordner legen (steht unter **Plugins**), Haken setzen, speichern, App neu starten.
Gib nur Plugins frei, die du selbst geschrieben oder geprüft hast.

---

## Was kostet das? (grobe Schätzung, UNVERIFIED, hängt vom Modell und von der Länge ab)

| Buch | Aufwand |
|---|---|
| Bilderbuch | wenige Cent bis ca. 1 € |
| Kinderroman (18 Kapitel) | einige Euro |
| Roman/YA (30 Kapitel, mit Überarbeitungen) | grob 10–40 € |

Die echten Kosten siehst du in der Anthropic-Console unter **Usage**. Darum immer erst
**Von 1 bis 3** schreiben lassen und prüfen, bevor du das ganze Buch startest. Günstiger wird
es mit einem anderen Modell unter **Einstellungen → Modell**, dann aber mit weniger Qualität.

## Wenn etwas hakt

| Problem | Lösung |
|---|---|
| „Keine passende Python-Version gefunden“ oder „Microsoft Visual C++ 14.0 required“ | `py install 3.12`, dann das Installer-Skript erneut starten. Die alte Umgebung wird automatisch ersetzt |
| Rot: „API-Key fehlt“ | Schritt 3 wiederholen |
| Job zeigt **error** | Fehlermeldung unten rechts lesen. Häufig: Guthaben leer oder Key falsch |
| „Für book:… läuft bereits Job“ | Warten. Pro Buch arbeitet immer nur ein Job |
| Fenster öffnet nicht, nur Browser | Ist normal, wenn WebView2 fehlt. Funktioniert genauso |
| Kapitel bleibt REVISE | Lektorat lesen, selbst nachbessern oder Anweisung geben. Das Gate ist absichtlich streng |
