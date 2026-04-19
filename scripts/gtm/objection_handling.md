# Einwand-Handling — FraPP + G.O.D.A.I.

Die 10 häufigsten Einwände und die exakten Antworten.

---

## E1 · "Wir haben das intern gebaut"

**Antwort:**
> "Wie lange hat das gedauert? Und habt ihr einen Penetrationstest-Bericht?"

Die meisten Teams sagen 6+ Monate und haben keinen formalen Test-Report.

> "Wir haben 275 automatisierte Tests, davon 30 reine OWASP-Angriffsvektoren —
> alle mit Protokoll. Das ist das Dokument das euer Auditor als Nachweis akzeptiert.
> Habt ihr das equivalent?"

**Wenn ja:** "Perfekt — dann habt ihr das Problem gelöst. Falls ihr irgendwann
skalieren wollt ohne das intern zu warten, meldet euch."

---

## E2 · "Zu teuer"

**Antwort:**
> "Was kostet euch ein Entwickler-Monat intern?"

Durchschnittlich 8.000–15.000 € (Gehalt + Overhead). Ein Jahr Starter = 1.788 €.

> "149 Euro im Monat ist weniger als ein Entwicklertag.
> Für das was ihr intern bauen müsst — JWT-Auth, SHA256-Kette, OWASP-sichere API,
> DSGVO-Endpunkte, Penetrationstest — rechnet mit 2–3 Monaten Entwicklungszeit.
> Das sind 16.000–45.000 Euro. Einmalig."

---

## E3 · "Wir brauchen das nicht / EU AI Act ist noch weit weg"

**Antwort:**
> "August 2026 ist in X Monaten. Wie lange braucht ihr für interne Genehmigungen
> und Beschaffungsprozesse?"

In regulierten Unternehmen: 3–6 Monate Beschaffung. Plus 2–3 Monate Integration.

> "Wenn ihr heute anfangt, habt ihr genau genug Zeit.
> Wenn ihr in 6 Monaten anfangt, nicht mehr."

**Für kleinere Teams:**
> "Stimmt — vielleicht gilt es nicht für euch. Für welche Kunden baut ihr?
> Falls die in der EU sind und reguliert: es gilt für sie, und sie fragen danach."

---

## E4 · "Schickt uns erst Unterlagen / einen Prospekt"

**Antwort:**
> "Ich schicke euch das Demo-Repo — ihr könnt in 15 Minuten selbst testen.
> Kein Prospekt ist besser als echter Code der läuft.
> git clone, pip install, uvicorn. Swagger-Docs zeigen alles."

Kein Prospekt. Immer Code.

---

## E5 · "Wir nutzen bereits [Guardrails AI / LangSmith / Langfuse]"

**Antwort:**
> "Die sind gut für Tracing und Output-Validierung. Was sie nicht haben:
> kryptografisch verkettete Audit-Logs (EU AI Act Art. 12),
> DSGVO-Endpunkte (Art. 15/17/20), und offline-Betrieb ohne Cloud-Abhängigkeit.
> Nutzt ihr die für Compliance-Nachweise — oder für Development-Observability?"

Die meisten nutzen sie für Dev-Observability. Das ist eine andere Kategorie.

---

## E6 · "Wir sind nicht in einer regulierten Branche"

**Antwort:**
> "Eure Kunden vielleicht. Healthcare, Finance, HR, öffentlicher Sektor —
> wenn die euer Produkt kaufen wollen, fragen sie nach eurem Compliance-Nachweis.
> Das ist kein internes Problem mehr, das ist ein Verkaufsargument."

---

## E7 · "Können wir das selbst hosten? Wir haben Datenschutz-Anforderungen"

**Antwort:**
> "Ja — Self-Hosted Lizenz, 15.000 Euro einmalig, Quellcode.
> Keine laufenden Gebühren, keine Cloud-Abhängigkeit, keine Daten verlassen euer Rechenzentrum.
> OllamaProvider läuft vollständig lokal — nicht mal das LLM braucht Internet."

---

## E8 · "Was ist wenn ihr als Unternehmen wegfallt?"

**Antwort:**
> "Self-Hosted Lizenz enthält den vollständigen Quellcode.
> Ihr seid nicht von uns abhängig — ihr könnt das System selbst warten,
> forken, und weiterentwickeln. Kein Vendor-Lock-in."

Für SaaS-Kunden:
> "Der Code ist vollständig in eurer Infrastruktur deployed. Bei uns liegt nur
> die Lizenz. Ihr habt immer Zugriff auf eure Daten und euer System."

---

## E9 · "Wir müssen das mit unserer IT-Security prüfen lassen"

**Antwort:**
> "Perfekt — ich schicke euch:
> 1. Den L4 Penetrationstest-Report (30/30 OWASP blockiert)
> 2. Den Architektur-Überblick (keine externen Calls in Produktion, kein Telemetry)
> 3. Das Demo-Repo zum selbst prüfen
>
> Wer ist euer Security-Kontakt? Ich kann ihm direkt eine technische Zusammenfassung schicken."

Immer den technischen Kontakt identifizieren. Security-Reviews laufen schneller
wenn der Reviewer direkt angesprochen wird.

---

## E10 · "Wie unterscheidet sich das von einer einfachen Logging-Library?"

**Antwort:**
> "Eine Logging-Library schreibt Logs. G.O.D.A.I. macht vier Dinge mehr:
>
> 1. Kryptografische Kette: jeder Eintrag enthält den Hash des vorherigen.
>    Manipulation ist mathematisch nachweisbar — nicht nur 'wir sagen es'.
>
> 2. Policy-Engine: Regeln in YAML, kein Code. Compliance-Officer kann
>    selbst Regeln ändern ohne Entwickler.
>
> 3. Generator ≠ Prüfer: die KI die antwortet, prüft nie ihre eigene Antwort.
>    Das ist EU AI Act Art. 14 — menschliche Aufsicht durch Design erzwungen.
>
> 4. DSGVO-Endpunkte: Auskunft, Löschung, Export out of the box.
>
> Eine Logging-Library gibt euch Logs. Das hier gibt euch den Audit-Report."

---

## Generelle Prinzipien

**Nie verteidigen — immer mit Fragen antworten.**
Jeder Einwand ist eine Information. Erst verstehen, dann antworten.

**Preis nie zuerst rechtfertigen.**
Wenn jemand fragt "wie teuer?", zuerst den Wert klar machen, dann den Preis nennen.

**Kein Custom-Deal unter 800 € für die ersten 10 Kunden.**
Günstige Preise für frühe Kunden senken den wahrgenommenen Wert dauerhaft.

**Demo immer anbieten, nie Prospekte.**
Code der läuft überzeugt mehr als jedes PDF.
