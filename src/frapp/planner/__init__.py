"""
FraPP-Tagesplaner.

Planungsstandard (Pflichtformat):
  1. Zeitstempel Berlin (MEZ/MESZ) mit gekennzeichneter Methodik:
     PTB-Zeitserver (NTP), sonst ausdrücklich markierter Fallback (Systemuhr).
  2. Truth-Gate je Quelle: VERIFIED | UNVERIFIED | EMPTY-BUT-VERIFIED.
  3. Plan als 4D-Matrix: Time / Constraint (HARD|SOFT|FLOAT) / Domain / Source (+Certainty).

No-Citation = No-Assertion: Jede Zeile nennt ihre Quelle. Zeiten, die der Planer
vorschlägt (nicht aus einer Quelle stammen), sind als ASSUMPTION gekennzeichnet.
"""
