"""
Command risk classifier — distinguishes READ (auto-execute) from WRITE (requires confirmation).

This is a conservative keyword heuristic: when in doubt it returns WRITE.
The classifier runs inside DispatchBridge.enqueue() and is the hard gate
that prevents write operations from silently passing through from chat context.
"""

from __future__ import annotations

import re
from enum import Enum, auto


class CommandRisk(Enum):
    READ = auto()   # safe to auto-execute (show, list, status, explain, …)
    WRITE = auto()  # requires explicit desktop confirmation before execution


# Any payload matching one of these patterns is classified as WRITE.
# Patterns are intentionally broad — safer to over-flag than under-flag.
_WRITE_RE = re.compile(
    r"\b("
    # File / content mutation
    r"edit|modif|chang[ei]|updat[ei]|creat[ei]|delet[ei]|remov[ei]|overwrite|append|"
    r"writ[ei]|generat[ei]|replac[ei]|insert|add\s+(?:file|line|code|function|class)|"
    r"patch|refactor|rename|move|copy|"
    # Execution
    r"run|exec(?:ut[ei])?|launch|start|stop|restart|kill|shutdown|reboot|trigger|deploy|"
    r"build|compil[ei]|test\b|"                   # 'test' can be write (running test suite)
    # Package managers / system commands
    r"install|uninstall|upgrade|downgrade|"
    r"npm|pip|brew|apt(?:-get)?|yarn|cargo|poetry|pipenv|"
    # VCS
    r"git\s+(?:commit|push|reset|clean|rebase|merge|branch\s+-[Dd]|rm|add|stash)|"
    r"commit|push\s+(?:to|origin)|pull\s+request|"
    # Shell destructive
    r"rm\b|mv\b|cp\b|mkdir|touch|truncat[ei]|chmod|chown|ln\b|"
    # Network / external
    r"curl|wget|fetch|http\b|request|post\b|put\b|patch\b|send\b|upload|download|"
    r"deploy|publish|release|"
    # Sensitive domains
    r"pay|purchas[ei]|subscrib[ei]|account|password|secret|token|key\b|"
    r"money|bank|transact|invoic[ei]|charg[ei]|credit|"
    # Database
    r"drop\s+(?:table|database)|truncat[ei]\s+table|alter\s+table|migrat[ei]|"
    r"insert\s+into|update\s+\w+\s+set|delete\s+from"
    r")\b",
    re.IGNORECASE,
)


def classify(payload: str) -> CommandRisk:
    """Return WRITE if the payload matches any write-risk pattern, else READ."""
    return CommandRisk.WRITE if _WRITE_RE.search(payload) else CommandRisk.READ
