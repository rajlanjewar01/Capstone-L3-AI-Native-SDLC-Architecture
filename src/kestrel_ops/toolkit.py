"""Tool behaviour. ``Toolkit`` is bound to ONE site; there is no way to pass a site to it per call.

Site scoping lives only in the four ``_site_*`` accessors below. Handlers never read
``Warehouse`` collections directly, so a handler cannot forget to filter by site.
"""
from __future__ import annotations

import re
from typing import Any

from . import search as search_mod
from .errors import ToolError, sku_not_found
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
)
from .store import SITES, DockSlot, ExceptionTicket, StockItem, Warehouse

LARGE_CHANGE_RATIO = 0.5  # spec section 6, assumption 3


def ok(data: dict[str, Any], guidance: str) -> dict[str, Any]:
    return {"data": data, "guidance": guidance}


class Toolkit:
    def __init__(self, warehouse: Warehouse, site: str) -> None:
        if site not in SITES:
            raise ValueError(f"site must be one of {SITES}, got {site!r}")
        self._wh = warehouse
        self.site = site

    # ------------------------------------------------------------------
    # THE site choke point: every read of warehouse data goes through here.
    # ------------------------------------------------------------------
    def _site_stock(self) -> list[StockItem]:
        return [i for i in self._wh.stock.values() if i.site == self.site]

    def _site_item(self, sku: str) -> StockItem:
        item = self._wh.stock.get(sku)
        if item is None or item.site != self.site:
            raise sku_not_found(sku, self.site)  # same answer for "missing" and "other site"
        return item

    def _site_slots(self, date: str | None = None) -> list[DockSlot]:
        return [
            s for s in self._wh.dock if s.site == self.site and (date is None or s.date == date)
        ]

    def _site_tickets(self) -> list[ExceptionTicket]:
        return [t for t in self._wh.exceptions if t.site == self.site]

    def _site_ticket(self, exception_id: str) -> ExceptionTicket:
        for t in self._site_tickets():
            if t.exception_id == exception_id:
                return t
        raise ToolError(
            "EXCEPTION_NOT_FOUND",
            f"No exception {exception_id} at {self.site}.",
            parameter="exception_id",
            received=exception_id,
            how_to_fix="Use list_exceptions to find the ticket at this site.",
            suggested_call={"tool": "list_exceptions", "arguments": {"status": "all"}},
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _available_dates(self) -> list[str]:
        return sorted({s.date for s in self._site_slots()})

    def _slot_row(self, date: str, slot: str) -> DockSlot:
        dates = self._available_dates()
        if date not in dates:
            raise ToolError(
                "DATE_NOT_SCHEDULED",
                f"{self.site} has no dock schedule for {date}.",
                parameter="date",
                received=date,
                valid_values=dates,
                how_to_fix=f"Use one of the scheduled dates: {', '.join(dates)}. Ask the user which date they mean if unsure.",
                suggested_call={"tool": "list_dock_slots", "arguments": {"date": dates[0]}} if dates else None,
                extra={"available_dates": dates},
            )
        for s in self._site_slots(date):
            if s.slot == slot:
                return s
        raise ToolError(  # not reachable with the provided data; kept so a bad schedule fails clearly
            "SLOT_NOT_FOUND",
            f"{self.site} has no {slot} slot on {date}.",
            parameter="slot",
            received=slot,
            valid_values=[s.slot for s in self._site_slots(date)],
            how_to_fix="Choose one of the listed slots.",
        )

    def _bin_formats(self) -> list[str]:
        return sorted({re.sub(r"\d", "n", i.bin) for i in self._site_stock()})

    def _bin_prefixes(self) -> set[str]:
        return {i.bin.split("-")[0] for i in self._site_stock()}

    # ------------------------------------------------------------------
    # read-only
    # ------------------------------------------------------------------
    async def search_products(self, a: SearchProductsArgs) -> dict[str, Any]:
        data = search_mod.search(self._site_stock(), a.query)
        return ok(data, search_mod.GUIDANCE[data["resolution"]])

    async def list_dock_slots(self, a: ListDockSlotsArgs) -> dict[str, Any]:
        dates = self._available_dates()
        if a.date not in dates:
            self._slot_row(a.date, "06:00")  # raises DATE_NOT_SCHEDULED with full detail
        slots = self._site_slots(a.date)
        shown = [s for s in slots if a.status == "all" or s.status == a.status]
        data = {
            "date": a.date,
            "slots": [{"slot": s.slot, "status": s.status, "carrier": s.carrier} for s in shown],
            "available_count": sum(1 for s in slots if s.status == "available"),
            "booked_count": sum(1 for s in slots if s.status == "booked"),
            "available_dates": dates,
        }
        return ok(data, "Report the free slots (or the booked ones with their carrier) as the user asked.")

    async def list_exceptions(self, a: ListExceptionsArgs) -> dict[str, Any]:
        if a.sku is not None:
            self._site_item(a.sku)  # same scoping rule as everywhere else
        rows = [
            t
            for t in self._site_tickets()
            if (a.status == "all" or t.status == a.status) and (a.sku is None or t.sku == a.sku)
        ]
        data = {
            "count": len(rows),
            "exceptions": [
                {
                    "exception_id": t.exception_id,
                    "category": t.category,
                    "sku": t.sku,
                    "summary": t.summary,
                    "status": t.status,
                    "resolution_note": t.resolution_note,
                }
                for t in rows
            ],
        }
        return ok(data, "Describe tickets by what they are about, not just their ids.")

    # ------------------------------------------------------------------
    # reversible writes
    # ------------------------------------------------------------------
    async def book_dock_slot(self, a: BookDockSlotArgs) -> dict[str, Any]:
        row = self._slot_row(a.date, a.slot)
        if row.status == "booked":
            free = [s.slot for s in self._site_slots(a.date) if s.status == "available"]
            raise ToolError(
                "SLOT_ALREADY_BOOKED",
                f"{self.site} {a.slot} on {a.date} is already booked by {row.carrier}.",
                parameter="slot",
                received=a.slot,
                valid_values=free,
                how_to_fix=(
                    "Choose one of the free slots in valid_values, or cancel the existing booking "
                    "with prepare_dock_cancellation first. Ask the user which they prefer."
                    if free
                    else "No free slots remain on this date; use list_dock_slots to check other dates."
                ),
                suggested_call=(
                    {"tool": "book_dock_slot", "arguments": {"date": a.date, "slot": free[0], "carrier": a.carrier}}
                    if free
                    else None
                ),
                extra={"booked_by": row.carrier},
            )
        row.status, row.carrier = "booked", a.carrier
        result = {"date": a.date, "slot": a.slot, "carrier": a.carrier, "status": "booked"}
        self._wh.record_audit(self.site, "book_dock_slot", a.model_dump(), result)
        return ok(result, f"Booked. To undo, use prepare_dock_cancellation for {a.slot} on {a.date}.")

    async def move_stock(self, a: MoveStockArgs) -> dict[str, Any]:
        item = self._site_item(a.sku)
        prefix = a.to_bin.split("-")[0]
        if prefix not in self._bin_prefixes():
            formats = self._bin_formats()
            raise ToolError(
                "BIN_NOT_AT_SITE",
                f"Bin {a.to_bin} is not a bin at {self.site}.",
                parameter="to_bin",
                received=a.to_bin,
                valid_values=formats,
                how_to_fix=f"Use a bin in this site's format: {', '.join(formats)} (n = a digit).",
            )
        if a.to_bin == item.bin:
            raise ToolError(
                "SAME_BIN",
                f"{a.sku} is already in {item.bin}.",
                parameter="to_bin",
                received=a.to_bin,
                how_to_fix="Choose a different destination bin; nothing needs to move.",
            )
        warnings = [
            f"{o.sku} ({o.description}) is already in {a.to_bin}."
            for o in self._site_stock()
            if o.bin == a.to_bin and o.sku != item.sku
        ]
        from_bin, item.bin = item.bin, a.to_bin
        result: dict[str, Any] = {
            "sku": item.sku,
            "description": item.description,
            "from_bin": from_bin,
            "to_bin": item.bin,
            "quantity": item.quantity,
            "unit": item.unit,
            "warnings": warnings,
        }
        self._wh.record_audit(self.site, "move_stock", a.model_dump(), result)
        return ok(result, f"Moved. Quantity unchanged. To undo, move it back to {from_bin}.")

    async def raise_exception(self, a: RaiseExceptionArgs) -> dict[str, Any]:
        if a.sku is not None:
            self._site_item(a.sku)
        if a.sku is not None and not a.allow_duplicate:
            for t in self._site_tickets():
                if t.status == "open" and t.category == a.category and t.sku == a.sku:
                    raise ToolError(
                        "DUPLICATE_OPEN_EXCEPTION",
                        f"{t.exception_id} is already open for {a.sku} ({a.category}): {t.summary}",
                        parameter="sku",
                        received=a.sku,
                        how_to_fix=(
                            "Tell the user this ticket already exists. Only if they confirm this is a "
                            "separate issue, repeat the call with allow_duplicate=true."
                        ),
                        extra={"existing_exception_id": t.exception_id},
                    )
        ticket = ExceptionTicket(
            exception_id=self._wh.next_exception_id(),
            site=self.site,
            category=a.category,
            sku=a.sku,
            summary=a.summary,
        )
        ticket.history.append({"event": "opened", "summary": a.summary})
        self._wh.exceptions.append(ticket)
        result = {
            "exception_id": ticket.exception_id,
            "category": ticket.category,
            "sku": ticket.sku,
            "summary": ticket.summary,
            "status": "open",
        }
        self._wh.record_audit(self.site, "raise_exception", a.model_dump(), result)
        return ok(result, f"Ticket {ticket.exception_id} opened. Close it with close_exception when resolved.")

    async def close_exception(self, a: CloseExceptionArgs) -> dict[str, Any]:
        t = self._site_ticket(a.exception_id)
        if t.status == "closed":
            raise ToolError(
                "ALREADY_CLOSED",
                f"{t.exception_id} is already closed (note: {t.resolution_note}).",
                parameter="exception_id",
                received=a.exception_id,
                how_to_fix="Nothing to do. Use reopen_exception only if the user says it was closed in error.",
            )
        t.status, t.resolution_note = "closed", a.resolution_note
        t.history.append({"event": "closed", "note": a.resolution_note})
        result = {"exception_id": t.exception_id, "status": "closed", "resolution_note": t.resolution_note}
        self._wh.record_audit(self.site, "close_exception", a.model_dump(), result)
        return ok(result, "Closed. It can be reopened with reopen_exception if needed.")

    async def reopen_exception(self, a: ReopenExceptionArgs) -> dict[str, Any]:
        t = self._site_ticket(a.exception_id)
        if t.status == "open":
            raise ToolError(
                "ALREADY_OPEN",
                f"{t.exception_id} is already open.",
                parameter="exception_id",
                received=a.exception_id,
                how_to_fix="Nothing to do: the ticket is already open. Use close_exception when it has been resolved.",
            )
        previous = t.resolution_note
        t.status, t.resolution_note = "open", None
        t.history.append({"event": "reopened", "reason": a.reason, "previous_resolution_note": previous})
        result = {"exception_id": t.exception_id, "status": "open", "previous_resolution_note": previous}
        self._wh.record_audit(self.site, "reopen_exception", a.model_dump(), result)
        return ok(result, "Reopened; the previous resolution note is kept in the ticket history.")

    # ------------------------------------------------------------------
    # irreversible actions: prepare (preview) then confirm_action
    # ------------------------------------------------------------------
    async def prepare_stock_adjustment(self, a: PrepareStockAdjustmentArgs) -> dict[str, Any]:
        item = self._site_item(a.sku)
        if a.counted_quantity == item.quantity:
            raise ToolError(
                "NO_CHANGE",
                f"{a.sku} already shows {item.quantity} {item.unit}; the counted quantity is the same.",
                parameter="counted_quantity",
                received=a.counted_quantity,
                how_to_fix="No adjustment is needed. If the user's count is different, re-check the number they gave.",
            )
        delta = a.counted_quantity - item.quantity
        warnings: list[str] = []
        if abs(delta) > LARGE_CHANGE_RATIO * max(item.quantity, 1):
            warnings.append(
                f"LARGE_CHANGE: this changes the quantity by {abs(delta)} ({delta:+d}), more than "
                f"{int(LARGE_CHANGE_RATIO * 100)}% of the current {item.quantity}. Check the count with the user."
            )
        preview = {
            "summary": (
                f"Change {item.sku} ({item.description}) at {self.site} from {item.quantity} to "
                f"{a.counted_quantity} {item.unit} ({delta:+d}). Reason: {a.reason}. "
                "This feeds the month-end count and cannot be undone."
            ),
            "sku": item.sku,
            "description": item.description,
            "unit": item.unit,
            "current_quantity": item.quantity,
            "counted_quantity": a.counted_quantity,
            "delta": delta,
            "reason": a.reason,
            "warnings": warnings,
        }
        pending = self._wh.confirmations.issue(
            self.site, "stock_adjustment", a.model_dump(), {"quantity": item.quantity}
        )
        return ok(
            {"preview": preview, "confirmation_token": pending.token, "expires_in_seconds": 300},
            "NOTHING HAS CHANGED YET. Show the preview to the user and wait for an explicit yes, "
            "then call confirm_action with the token.",
        )

    async def prepare_dock_cancellation(self, a: PrepareDockCancellationArgs) -> dict[str, Any]:
        row = self._slot_row(a.date, a.slot)
        if row.status != "booked":
            raise ToolError(
                "SLOT_NOT_BOOKED",
                f"{self.site} {a.slot} on {a.date} is not booked, so there is nothing to cancel.",
                parameter="slot",
                received=a.slot,
                how_to_fix="Check the slot with list_dock_slots; it is already free.",
                suggested_call={"tool": "list_dock_slots", "arguments": {"date": a.date, "status": "booked"}},
            )
        preview = {
            "summary": (
                f"Cancel the {a.slot} dock booking on {a.date} at {self.site} held by {row.carrier}. "
                f"Reason: {a.reason}. The slot becomes free and may be rebooked by someone else."
            ),
            "date": a.date,
            "slot": a.slot,
            "carrier": row.carrier,
            "reason": a.reason,
        }
        pending = self._wh.confirmations.issue(
            self.site, "dock_cancellation", a.model_dump(), {"carrier": row.carrier}
        )
        return ok(
            {"preview": preview, "confirmation_token": pending.token, "expires_in_seconds": 300},
            "NOTHING HAS CHANGED YET. Show the preview to the user and wait for an explicit yes, "
            "then call confirm_action with the token.",
        )

    async def confirm_action(self, a: ConfirmActionArgs) -> dict[str, Any]:
        pending = self._wh.confirmations.redeem(self.site, a.confirmation_token)  # single use
        args = pending.args
        if pending.action == "stock_adjustment":
            item = self._site_item(args["sku"])
            if item.quantity != pending.fingerprint["quantity"]:
                raise ToolError(
                    "CONFIRMATION_STALE",
                    f"{item.sku} changed from {pending.fingerprint['quantity']} to {item.quantity} since the preview.",
                    parameter="confirmation_token",
                    received=a.confirmation_token,
                    how_to_fix="Run prepare_stock_adjustment again so the user can confirm against the current quantity.",
                    suggested_call={"tool": "prepare_stock_adjustment", "arguments": args},
                )
            before = item.quantity
            item.quantity = args["counted_quantity"]
            entry = {
                "ledger_id": self._wh.next_ledger_id(),
                "site": self.site,
                "sku": item.sku,
                "before": before,
                "after": item.quantity,
                "delta": item.quantity - before,
                "reason": args["reason"],
            }
            self._wh.ledger.append(entry)
            result = {"action": "stock_adjustment", "result": entry}
        else:  # dock_cancellation
            row = self._slot_row(args["date"], args["slot"])
            if row.status != "booked" or row.carrier != pending.fingerprint["carrier"]:
                raise ToolError(
                    "CONFIRMATION_STALE",
                    f"The {args['slot']} booking on {args['date']} changed since the preview.",
                    parameter="confirmation_token",
                    received=a.confirmation_token,
                    how_to_fix="Run prepare_dock_cancellation again to see the current booking.",
                    suggested_call={"tool": "prepare_dock_cancellation", "arguments": args},
                )
            cancelled_carrier = row.carrier
            row.status, row.carrier = "available", None
            result = {
                "action": "dock_cancellation",
                "result": {
                    "date": args["date"],
                    "slot": args["slot"],
                    "cancelled_carrier": cancelled_carrier,
                    "reason": args["reason"],
                    "status": "available",
                },
            }
        self._wh.record_audit(self.site, "confirm_action", {"action": pending.action, **args}, result)
        return ok(result, "Done. Tell the user exactly what was changed.")
