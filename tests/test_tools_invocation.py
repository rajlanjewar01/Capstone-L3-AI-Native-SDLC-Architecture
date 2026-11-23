"""Happy paths through the real MCP protocol, plus a true stdio end-to-end run."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from helpers import DATE, call, error_of

ROOT = Path(__file__).resolve().parents[1]


async def test_dock_listing_counts_and_filters(leeds):
    _, env = await call(leeds, "list_dock_slots", date=DATE)
    d = env["data"]
    assert (d["available_count"], d["booked_count"], len(d["slots"])) == (4, 2, 6)
    assert d["available_dates"] == [DATE]
    _, booked = await call(leeds, "list_dock_slots", date=DATE, status="booked")
    assert [s["slot"] for s in booked["data"]["slots"]] == ["08:00", "12:00"]
    assert {s["carrier"] for s in booked["data"]["slots"]} == {"Northbound Freight"}


async def test_booking_a_free_slot_then_the_same_slot_again(leeds):
    is_err, env = await call(leeds, "book_dock_slot", date=DATE, slot="10:00", carrier="Acme Ltd")
    assert not is_err and env["data"] == {"date": DATE, "slot": "10:00", "carrier": "Acme Ltd", "status": "booked"}
    _, view = await call(leeds, "list_dock_slots", date=DATE, status="available")
    assert "10:00" not in {s["slot"] for s in view["data"]["slots"]}
    # even the same carrier asking again is a conflict, never a silent success
    is_err, again = await call(leeds, "book_dock_slot", date=DATE, slot="10:00", carrier="Acme Ltd")
    assert is_err and error_of(again)["code"] == "SLOT_ALREADY_BOOKED" and error_of(again)["booked_by"] == "Acme Ltd"


async def test_move_stock_changes_the_bin_and_nothing_else(leeds, warehouse):
    is_err, env = await call(leeds, "move_stock", sku="SKU-8801", to_bin="A-12-9")
    assert not is_err
    d = env["data"]
    assert (d["from_bin"], d["to_bin"], d["quantity"], d["unit"]) == ("A-12-3", "A-12-9", 240, "each")
    _, found = await call(leeds, "search_products", query="SKU-8801")
    cand = found["data"]["candidates"][0]
    assert (cand["bin"], cand["quantity"]) == ("A-12-9", 240)
    assert warehouse.ledger == []  # a move never touches the month-end ledger


async def test_move_is_reversible_and_warns_about_an_occupied_bin(leeds):
    _, env = await call(leeds, "move_stock", sku="SKU-8801", to_bin="A-12-4")  # holds SKU-8802
    assert any("SKU-8802" in w for w in env["data"]["warnings"])
    _, back = await call(leeds, "move_stock", sku="SKU-8801", to_bin="A-12-3")
    assert back["data"]["to_bin"] == "A-12-3"


async def test_yard_bins_are_valid_at_leeds(leeds):
    is_err, env = await call(leeds, "move_stock", sku="SKU-8815", to_bin="YARD-2")
    assert not is_err and env["data"]["from_bin"] == "YARD-1"


async def test_exception_lifecycle_raise_list_close_reopen(leeds):
    _, made = await call(leeds, "raise_exception", category="DAMAGED", sku="SKU-8801",
                         summary="Two pallets of wrap crushed in bay 3")
    ticket = made["data"]["exception_id"]
    assert ticket == "EXC-0001" and made["data"]["status"] == "open"
    _, openl = await call(leeds, "list_exceptions")
    assert [e["exception_id"] for e in openl["data"]["exceptions"]] == [ticket]
    _, closed = await call(leeds, "close_exception", exception_id=ticket, resolution_note="Replaced both pallets")
    assert closed["data"]["status"] == "closed"
    _, none_open = await call(leeds, "list_exceptions")
    assert none_open["data"]["count"] == 0
    _, all_ = await call(leeds, "list_exceptions", status="closed", sku="SKU-8801")
    assert all_["data"]["exceptions"][0]["resolution_note"] == "Replaced both pallets"
    _, re = await call(leeds, "reopen_exception", exception_id=ticket, reason="Pallets were not actually replaced")
    assert re["data"]["status"] == "open" and re["data"]["previous_resolution_note"] == "Replaced both pallets"


async def test_other_category_needs_no_sku(leeds):
    is_err, env = await call(leeds, "raise_exception", category="OTHER", summary="Dock door sticking open")
    assert not is_err and env["data"]["sku"] is None


async def test_state_changes_are_audited(leeds, warehouse):
    await call(leeds, "book_dock_slot", date=DATE, slot="10:00", carrier="Acme Ltd")
    await call(leeds, "move_stock", sku="SKU-8801", to_bin="A-12-9")
    assert [a["tool"] for a in warehouse.audit] == ["book_dock_slot", "move_stock"]
    assert all(a["site"] == "LEEDS-01" for a in warehouse.audit)


async def test_end_to_end_over_a_real_stdio_subprocess():
    """Launch `python -m kestrel_ops` exactly as an agent host would, with the site in the environment."""
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "kestrel_ops"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "KESTREL_SITE": "GLASGOW-03"},
    )
    async with Client(params) as c:
        tools = {t.name for t in (await c.list_tools()).tools}
        assert "search_products" in tools and "confirm_action" in tools
        res = await c.call_tool("search_products", {"query": "shrink film"})
        import json
        env = json.loads(res.content[0].text)
        assert env["site"] == "GLASGOW-03" and env["data"]["resolution"] == "multiple_matches"
        res2 = await c.call_tool("search_products", {"query": "pallet wrap"})  # a Leeds product
        assert json.loads(res2.content[0].text)["data"]["resolution"] == "no_match"
