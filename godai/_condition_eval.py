"""
Shared condition evaluator for THEMIS and APOLLON.

Evaluates policy/routing condition expressions from YAML config files
using a restricted Python eval.  Only comparison and logical operators
are available — all builtins are stripped.

Security model: YAML policy/routing files are administrator-controlled
trusted input.  The eval sandbox (``__builtins__: {}``) prevents access
to any Python built-in function, making arbitrary code execution
impossible even if a policy file were tampered with.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from godai.models.request import DataClass, TrustLevel


def build_eval_context(
    data_class_value: str,
    trust_level_value: int,
    action: str,
    explicit_consent: bool,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build the evaluation context dict passed to the restricted eval.

    Args:
        data_class_value: String value of the request's DataClass enum.
        trust_level_value: Integer value of the request's TrustLevel enum.
        action: Optional action string from request context.
        explicit_consent: Consent flag from request context.
        extra: Additional key-value pairs merged into the context.

    Returns:
        Dictionary of variables available inside condition expressions.
    """
    ctx: Dict[str, Any] = {
        "data_class": data_class_value,
        "trust_level": trust_level_value,
        "action": action,
        "explicit_consent": explicit_consent,
    }
    if extra:
        ctx.update(extra)
    return ctx


def evaluate_condition(condition: str, context: Dict[str, Any]) -> bool:
    """
    Safely evaluate a policy or routing condition expression string.

    Supported patterns (may be combined with ``and`` / ``or`` / ``not``):
      - ``data_class == SENSITIVE``
      - ``trust_level >= L2``
      - ``action == 'send_email'``
      - ``explicit_consent == true``
      - ``data_class == SENSITIVE and trust_level >= L2``

    Enum name substitutions performed before eval:
      - DataClass names  → their string values  (e.g. ``SENSITIVE`` → ``"SENSITIVE"``)
      - TrustLevel names → their integer values (e.g. ``L2`` → ``2``)

    Args:
        condition: Expression string from YAML config.
        context: Evaluation context produced by :func:`build_eval_context`.

    Returns:
        Boolean result of the expression.

    Raises:
        ValueError: If the expression cannot be parsed or evaluated.
    """
    expr = condition

    # Substitute DataClass enum names → quoted string literals
    for dc in DataClass:
        expr = re.sub(rf"\b{re.escape(dc.name)}\b", f'"{dc.value}"', expr)

    # Substitute TrustLevel enum names → integer literals
    for tl in TrustLevel:
        expr = re.sub(rf"\b{re.escape(tl.name)}\b", str(int(tl.value)), expr)

    # Normalise YAML-style boolean literals
    expr = re.sub(r"\btrue\b", "True", expr)
    expr = re.sub(r"\bfalse\b", "False", expr)

    try:
        # builtins stripped — only variable refs and operators available
        result = eval(expr, {"__builtins__": {}}, context)  # noqa: S307
        return bool(result)
    except Exception as exc:
        raise ValueError(
            f"Cannot evaluate condition {condition!r} → {expr!r}: {exc}"
        ) from exc
