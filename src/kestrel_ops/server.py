"""MCP server wiring.

One registry table drives the tool list (descriptions, schemas, annotations) so the class tag in
a description and the read/destructive hints cannot drift apart (spec section 3.2).
Arguments are validated here, not by the framework, so a bad call gets the spec's actionable
error object instead of a generic message.
"""
from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import mcp.types as t
from mcp.server import Server

from .errors import ToolError, validation_to_tool_error
from .models import (
    BookDockSlotArgs,
    CloseExceptionArgs,
    ConfirmActionArgs,
    ListDockSlotsArgs,
    ListExceptionsArgs,
    MoveStockArgs,
    PrepareDockCancellationArgs,
    PrepareStockAdjustmentArgs,
    RaiseExceptionArgs,
    ReopenExceptionArgs,
    SearchProductsArgs,
    json_schema,
)
from .store import SITES, Warehouse
from .toolkit import Toolkit

READ, PREVIEW, WRITE, IRREVERSIBLE = "READ", "PREVIEW", "WRITE", "IRREVERSIBLE"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: str
    description: str
    model: type


REGISTRY: tuple[ToolSpec, ...] = (
    ToolSpec(
        "search_products", READ,
        "[READ-ONLY] Find products at YOUR site by name or SKU and return stock for every match. "
        'Pass only the product words (for example "pallet wrap", "tape clear", "SKU-8801"), not the whole '
        "question. This returns EVERY plausible match and never picks a best one. Read `data.resolution`: "
        '"single_match" -> answer directly; "multiple_matches" -> do NOT choose for the user: ask which one '
        'they mean using `data.disambiguate_by` (e.g. "clear or black?"), or report each item if they asked '
        'about all of them; "needs_confirmation" -> spelling was only approximate, confirm the item with the '
        'user before relying on it; "no_match" -> nothing at this site, ask the user to rephrase. Always say '
        'the unit, and treat quantity 0 as "out of stock", not as an error. Only your own site\'s stock is '
        "visible; other sites cannot be queried.",
        SearchProductsArgs,
    ),
    ToolSpec(
        "list_dock_slots", READ,
        "[READ-ONLY] List dock slots at YOUR site for one date, with who has booked each. Use this before "
        "booking. Dates must be ISO (YYYY-MM-DD). If the date has no schedule the error lists the dates that do.",
        ListDockSlotsArgs,
    ),
    ToolSpec(
        "list_exceptions", READ,
        "[READ-ONLY] List exception tickets at YOUR site. Use this to find a ticket before closing or "
        "reopening it so the user never has to type an id.",
        ListExceptionsArgs,
    ),
    ToolSpec(
        "book_dock_slot", WRITE,
        "[CHANGES DATA - reversible] Book a free dock slot at YOUR site for a carrier. Fails with "
        "SLOT_ALREADY_BOOKED (never overwrites) if taken; the error lists free slots. Undo with "
        "prepare_dock_cancellation.",
        BookDockSlotArgs,
    ),
    ToolSpec(
        "move_stock", WRITE,
        "[CHANGES DATA - reversible] Move ALL stock of one SKU to a different bin at YOUR site. Location only: "
        "quantity is not changed. To change a quantity use prepare_stock_adjustment. Undo by moving it back. "
        "Get the SKU from search_products; do not ask the user to type it.",
        MoveStockArgs,
    ),
    ToolSpec(
        "raise_exception", WRITE,
        "[CHANGES DATA - reversible] Open an exception ticket at YOUR site for damaged, missing or wrong stock, "
        "or another problem. For DAMAGED, MISSING and WRONG_ITEM the SKU is required: find it with "
        "search_products and confirm which item with the user if there are several. Returns the ticket id. "
        "If an identical ticket is already open you get DUPLICATE_OPEN_EXCEPTION rather than a second ticket.",
        RaiseExceptionArgs,
    ),
    ToolSpec(
        "close_exception", WRITE,
        "[CHANGES DATA - reversible] Close an open exception at YOUR site with a note on what was done. "
        "Undo with reopen_exception.",
        CloseExceptionArgs,
    ),
    ToolSpec(
        "reopen_exception", WRITE,
        "[CHANGES DATA - reversible] Reopen a closed exception at YOUR site, for example if it was closed by "
        "mistake. The previous resolution note is kept in history.",
        ReopenExceptionArgs,
    ),
    ToolSpec(
        "prepare_stock_adjustment", PREVIEW,
        "[PREVIEW - changes nothing] Step 1 of 2 for correcting a counted quantity at YOUR site. Provide the "
        "quantity actually counted (the new total, not the difference). Returns a before/after preview and a "
        "confirmation_token. Corrections feed the month-end count and CANNOT be undone, only offset by "
        "another adjustment, so show the preview to the user, wait for an explicit yes, then call "
        "confirm_action. For moving stock between bins use move_stock instead.",
        PrepareStockAdjustmentArgs,
    ),
    ToolSpec(
        "prepare_dock_cancellation", PREVIEW,
        "[PREVIEW - changes nothing] Step 1 of 2 for cancelling a dock booking at YOUR site. Shows which "
        "carrier would lose the slot and returns a confirmation_token. Show the preview to the user and wait "
        "for an explicit yes, then call confirm_action. Cancelling cannot be reliably undone: the slot may be "
        "rebooked by someone else.",
        PrepareDockCancellationArgs,
    ),
    ToolSpec(
        "confirm_action", IRREVERSIBLE,
        "[CHANGES DATA - IRREVERSIBLE] Step 2 of 2: carry out an action previously prepared with "
        "prepare_stock_adjustment or prepare_dock_cancellation. Call ONLY after the user has seen the preview "
        "and explicitly said yes. A token works once, for 5 minutes, and only for the site that prepared it.",
        ConfirmActionArgs,
    ),
)
BY_NAME = {s.name: s for s in REGISTRY}


def annotations_for(kind: str) -> t.ToolAnnotations:
    if kind in (READ, PREVIEW):
        return t.ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
    return t.ToolAnnotations(
        readOnlyHint=False, destructiveHint=(kind == IRREVERSIBLE), idempotentHint=False, openWorldHint=False
    )


def resolve_site(value: str | None) -> str:
    """Fail closed: a missing or invalid site means the server does not start."""
    if value not in SITES:
        raise SystemExit(
            f"KESTREL_SITE must be set to one of {', '.join(SITES)} (got {value!r}). "
            "Refusing to start: every tool is scoped to one site and none can be chosen per call."
        )
    return value


def _result(envelope: dict[str, Any], is_error: bool) -> t.CallToolResult:
    return t.CallToolResult(
        content=[t.TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))],
        is_error=is_error,
    )


def build_server(site: str, warehouse: Warehouse | None = None) -> Server:
    site = resolve_site(site)
    toolkit = Toolkit(warehouse or Warehouse(), site)

    async def on_list_tools(ctx: Any, params: Any) -> t.ListToolsResult:
        return t.ListToolsResult(
            tools=[
                t.Tool(
                    name=s.name,
                    description=s.description,
                    inputSchema=json_schema(s.model),
                    annotations=annotations_for(s.kind),
                )
                for s in REGISTRY
            ]
        )

    async def on_call_tool(ctx: Any, params: t.CallToolRequestParams) -> t.CallToolResult:
        try:
            spec = BY_NAME.get(params.name)
            if spec is None:
                raise ToolError(
                    "UNKNOWN_TOOL",
                    f"There is no tool called {params.name!r}.",
                    parameter="name",
                    received=params.name,
                    valid_values=list(BY_NAME),
                    how_to_fix="Use one of the listed tool names.",
                )
            try:
                args = spec.model.model_validate(params.arguments or {})
            except Exception as exc:  # pydantic.ValidationError
                from pydantic import ValidationError

                if isinstance(exc, ValidationError):
                    raise validation_to_tool_error(spec.name, spec.model, exc, site) from None
                raise
            out = await getattr(toolkit, spec.name)(args)
            return _result({"ok": True, "site": site, **out}, False)
        except ToolError as err:
            return _result(err.to_envelope(), True)
        except Exception as exc:  # never leak a trace to the model
            error_id = uuid.uuid4().hex[:8]
            print(f"[kestrel-ops] INTERNAL_ERROR {error_id}: {exc!r}", file=sys.stderr)
            return _result(
                ToolError(
                    "INTERNAL_ERROR",
                    "The toolkit hit an unexpected problem.",
                    retryable=True,
                    how_to_fix=f"Retry once. If it fails again, report error_id {error_id} to IT.",
                    extra={"error_id": error_id},
                ).to_envelope(),
                True,
            )

    return Server(
        "kestrel-warehouse-ops",
        version="0.1.0",
        instructions=(
            f"You assist warehouse staff at {site}. Every tool acts on {site} only; there is no way to "
            "choose another site. Staff wear gloves: find SKUs yourself with search_products rather than "
            "asking them to type codes. If search returns several matches, ask which one. Never call "
            "confirm_action until the user has seen a preview and said yes."
        ),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )
