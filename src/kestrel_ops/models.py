"""Parameter models: the JSON schema the model sees is generated from these (spec section 4).

Closed value sets are enums/patterns in the schema, not prose validated afterwards.
Every model forbids unknown parameters, which is how a caller-supplied `site` is refused.
"""
from __future__ import annotations

import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

Slot = Literal["06:00", "08:00", "10:00", "12:00", "14:00", "16:00"]
StockReason = Literal["RECOUNT", "DAMAGE_WRITE_OFF", "FOUND_STOCK", "DATA_ENTRY_ERROR", "OTHER"]
CancelReason = Literal["CARRIER_NO_SHOW", "CARRIER_REQUEST", "BOOKED_IN_ERROR", "OTHER"]
Category = Literal["DAMAGED", "MISSING", "WRONG_ITEM", "OTHER"]
SKU_PATTERN = r"^SKU-\d{4}$"
Sku = Annotated[str, StringConstraints(pattern=SKU_PATTERN)]
ExceptionId = Annotated[str, StringConstraints(pattern=r"^EXC-\d{4}$")]


def _real_date(value: str) -> str:
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise PydanticCustomError(
            "invalid_date", "not a real calendar date", {"parameter": "date"}
        ) from None
    return value


IsoDate = Annotated[
    str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"), AfterValidator(_real_date)
]
Text = StringConstraints(strip_whitespace=True)


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchProductsArgs(_Args):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)] = Field(
        description='Product words or a SKU, e.g. "pallet wrap", "tape clear", "SKU-8801".'
    )


class ListDockSlotsArgs(_Args):
    date: IsoDate = Field(description="Date as YYYY-MM-DD. There is no default; do not guess the date.")
    status: Literal["available", "booked", "all"] = Field(default="all", description="Filter by slot status.")


class BookDockSlotArgs(_Args):
    date: IsoDate = Field(description="Date as YYYY-MM-DD.")
    slot: Slot = Field(description="Slot start time.")
    carrier: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)] = Field(
        description="Carrier name."
    )


class PrepareDockCancellationArgs(_Args):
    date: IsoDate = Field(description="Date as YYYY-MM-DD.")
    slot: Slot = Field(description="Slot start time of the booking to cancel.")
    reason: CancelReason = Field(description="Why the booking is being cancelled.")


class MoveStockArgs(_Args):
    sku: Sku = Field(description="SKU to move, from search_products.")
    to_bin: Annotated[str, StringConstraints(pattern=r"^([A-C]-\d{2}-\d|YARD-\d)$")] = Field(
        description="Destination bin at this site, e.g. A-12-5 or YARD-1."
    )


class PrepareStockAdjustmentArgs(_Args):
    sku: Sku = Field(description="SKU being corrected, from search_products.")
    counted_quantity: int = Field(
        ge=0, le=1_000_000, description="The quantity actually counted: the new TOTAL, not the difference."
    )
    reason: StockReason = Field(description="Why the count is being corrected.")


class ConfirmActionArgs(_Args):
    confirmation_token: Annotated[str, StringConstraints(pattern=r"^CONF-[A-Za-z0-9_-]{16}$")] = Field(
        description="Token from a prepare_* tool, used only after the user said yes to its preview."
    )


class RaiseExceptionArgs(_Args):
    category: Category = Field(description="Kind of exception.")
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=300)] = Field(
        description="A few words on what happened."
    )
    sku: Sku | None = Field(
        default=None, description="Related SKU. Required unless category is OTHER."
    )
    allow_duplicate: bool = Field(
        default=False,
        description="Set true only if the user confirms this is a separate issue from an open ticket.",
    )

    @model_validator(mode="after")
    def _sku_needed(self) -> "RaiseExceptionArgs":
        if self.category != "OTHER" and self.sku is None:
            raise PydanticCustomError(
                "sku_required",
                "sku is required when category is {category}. Find it with search_products.",
                {"category": self.category, "parameter": "sku"},
            )
        return self


class ListExceptionsArgs(_Args):
    status: Literal["open", "closed", "all"] = Field(default="open", description="Which tickets to list.")
    sku: Sku | None = Field(default=None, description="Only tickets for this SKU.")


class CloseExceptionArgs(_Args):
    exception_id: ExceptionId = Field(description="Ticket id from list_exceptions.")
    resolution_note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=300)] = Field(
        description="What was done to resolve it."
    )


class ReopenExceptionArgs(_Args):
    exception_id: ExceptionId = Field(description="Ticket id from list_exceptions.")
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=300)] = Field(
        description="Why it is being reopened."
    )


def _strip(node: Any) -> Any:
    """Remove pydantic's `title` noise and collapse Optional[...] to the non-null variant."""
    if isinstance(node, dict):
        node = {
            k: _strip(v)
            for k, v in node.items()
            if k != "title" and not (k == "default" and v is None)
        }
        # `title` as a property *name* is not used by any model, so the filter above is safe.
        if "anyOf" in node:
            non_null = [o for o in node["anyOf"] if o.get("type") != "null"]
            if len(non_null) == 1:
                merged = {k: v for k, v in node.items() if k != "anyOf"}
                merged.update(non_null[0])
                return merged
        return node
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def json_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = _strip(model.model_json_schema())
    schema.setdefault("properties", {})
    schema["additionalProperties"] = False
    return schema
