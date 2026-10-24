"""
SCRIPTOR — KI-Ghostwriter und Arbeitsagent.

Module:
  genres       Bucharten als YAML (Policy = Data)
  project      Buchprojekt mit SSOT/WORK-Trennung und Register
  ghostwriter  Bible → Outline → Entwurf → Lektorat → Gate → Revision
  voice        Deterministische Stilometrie (Voice-Profil)
  agent        Tool-Loop-Agent über Claude
  llm          Claude-API-Backend + FakeLLM für Tests
  audit        SHA256-verkettetes Audit-Log
"""

__version__ = "0.1.0"
