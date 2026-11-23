"""The one error shape (spec section 3.4) and the codes in spec section 5."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

# One realistic example per parameter, used in INVALID_ARGUMENTS problems.
FIELD_EXAMPLES: dict[str, Any] = {
    "query": "pallet wrap",
    "date": "2026-04-08",
    "slot": "10:00",
    "carrier": "Northbound Freight",
    "sku": "SKU-8801",
    "to_bin": "A-12-5",
    "counted_quantity": 200,
    "reason": "RECOUNT",
    "category": "DAMAGED",
    "summary": "Two pallets of wrap crushed by forklift at bay 3",
    "exception_id": "EXC-0001",
    "resolution_note": "Replaced damaged pallets and re-counted bin",
    "confirmation_token": "CONF-abcdefghijklmnop",
    "status": "open",
    "allow_duplicate": False,
}


class ToolError(Exception):
    """Raised by handlers; converted to the error envelope by the server."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        parameter: str | None = None,
        received: Any = None,
        valid_values: list[Any] | None = None,
        how_to_fix: str = "",
        suggested_call: dict[str, Any] | None = None,
        problems: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.parameter = parameter
        self.received = received
        self.valid_values = valid_values
        self.how_to_fix = how_to_fix
        self.suggested_call = suggested_call
        self.problems = problems
        self.extra = extra or {}

    def to_envelope(self) -> dict[str, Any]:
        err: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "parameter": self.parameter,
            "received": self.received,
            "valid_values": self.valid_values,
            "how_to_fix": self.how_to_fix,
            "suggested_call": self.suggested_call,
            "problems": self.problems,
        }
        err.update(self.extra)
        return {"ok": False, "error": err}


def sku_not_found(sku: str, site: str) -> ToolError:
    """Identical for a nonexistent SKU and another site's SKU: no existence oracle."""
    return ToolError(
        "SKU_NOT_FOUND",
        f"No product {sku} at {site}.",
        parameter="sku",
        received=sku,
        how_to_fix=(
            "Use search_products with the product's name to find the right SKU at this site. "
            "Only this site's stock can be accessed."
        ),
        suggested_call={"tool": "search_products", "arguments": {"query": "<product words>"}},
    )


def _schema_prop(model: type[BaseModel], name: str) -> dict[str, Any]:
    prop = model.model_json_schema().get("properties", {}).get(name, {})
    if "anyOf" in prop:
        for opt in prop["anyOf"]:
            if opt.get("type") != "null":
                return opt
    return prop


def _describe_expected(prop: dict[str, Any]) -> str | None:
    if "enum" in prop:
        return "one of: " + ", ".join(map(str, prop["enum"]))
    if "pattern" in prop:
        return f"text matching {prop['pattern']}"
    bits = []
    if "minLength" in prop:
        bits.append(f"at least {prop['minLength']} characters")
    if "maxLength" in prop:
        bits.append(f"at most {prop['maxLength']} characters")
    if "minimum" in prop:
        bits.append(f"minimum {prop['minimum']}")
    if "maximum" in prop:
        bits.append(f"maximum {prop['maximum']}")
    if bits:
        return ", ".join(bits)
    if "type" in prop:
        return f"a value of type {prop['type']}"
    return None


def validation_to_tool_error(tool: str, model: type[BaseModel], exc: ValidationError, site: str) -> ToolError:
    """Translate pydantic errors into INVALID_ARGUMENTS with one actionable problem per field."""
    problems: list[dict[str, Any]] = []
    saw_site = False
    for err in exc.errors():
        loc = err.get("loc", ())
        param = str(loc[0]) if loc else None
        etype = err["type"]
        received = err.get("input")
        if not isinstance(received, (str, int, float, bool, type(None))):
            received = None  # do not echo whole dicts back
        prop = _schema_prop(model, param) if param and param in model.model_fields else {}
        problem: dict[str, Any] = {
            "parameter": param,
            "problem": err["msg"],
            "received": received,
            "expected": _describe_expected(prop),
            "valid_values": prop.get("enum"),
            "example": FIELD_EXAMPLES.get(param) if param else None,
        }
        if etype == "missing":
            problem["problem"] = "required parameter is missing"
            problem["received"] = None
        elif etype == "extra_forbidden":
            problem["problem"] = "not a parameter of this tool"
            problem["expected"] = "remove it"
            problem["example"] = None
            if param == "site":
                saw_site = True
                problem["problem"] = (
                    f"'site' is not a parameter. This session is fixed to {site} and every tool "
                    "only ever acts on that site."
                )
        elif etype in ("literal_error", "enum"):
            problem["problem"] = "not an allowed value"
        elif etype == "string_pattern_mismatch":
            problem["problem"] = "wrong format"
        elif etype in ("string_too_short", "string_too_long"):
            problem["problem"] = "wrong length"
        elif etype in ("greater_than_equal", "less_than_equal"):
            problem["problem"] = "out of range"
        elif etype.endswith("_type") or etype in ("int_parsing", "bool_parsing", "string_type"):
            problem["problem"] = "wrong type"
        elif etype in ("sku_required", "invalid_date"):
            param = problem["parameter"] = err.get("ctx", {}).get("parameter", param)
            problem["problem"] = err["msg"]
            problem["example"] = FIELD_EXAMPLES.get(param)
        problems.append(problem)

    names = ", ".join(sorted({p["parameter"] or "arguments" for p in problems}))
    fix = (
        f"Correct {names} and call {tool} again. Each entry in `problems` says what is wrong, "
        "what is allowed, and gives an example."
    )
    if saw_site:
        fix = (
            f"Remove `site` and call {tool} again: this session is fixed to {site}, and no tool can "
            "act on another site. " + fix
        )
    first = problems[0] if problems else {}
    return ToolError(
        "INVALID_ARGUMENTS",
        f"The call to {tool} was rejected: " + "; ".join(
            f"{p['parameter'] or 'arguments'}: {str(p['problem']).rstrip('.')}" for p in problems
        ) + ".",
        parameter=first.get("parameter"),
        received=first.get("received"),
        valid_values=first.get("valid_values"),
        how_to_fix=fix,
        problems=problems,
    )
