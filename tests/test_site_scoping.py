"""Site scoping is enforced inside the toolkit. Same-site access must work; cross-site must be refused."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from helpers import DATE, DOCK, SITES, STOCK, call, error_of, skus_of, stock_at
from kestrel_ops.server import build_server, resolve_site

PAIRS = [(site, row) for site in SITES for row in STOCK]


IDS = [f"{site}-{row['sku']}" for site, row in PAIRS]


@pytest.mark.parametrize("site,row", PAIRS, ids=IDS)
async def test_search_by_sku_same_site_works_cross_site_finds_nothing(make_client, site, row):
    _, env = await call(make_client(site), "search_products", query=row["sku"])
    if row["site"] == site:
        assert skus_of(env) == [row["sku"]]
        assert env["data"]["candidates"][0]["quantity"] == row["quantity"]
    else:
        assert env["data"]["resolution"] == "no_match"
        text = str(env)
        assert row["description"] not in text and row["bin"] not in text


@pytest.mark.parametrize("site,row", PAIRS, ids=IDS)
async def test_stock_adjustment_preview_same_site_ok_cross_site_refused(make_client, site, row):
    is_err, env = await call(
        make_client(site), "prepare_stock_adjustment",
        sku=row["sku"], counted_quantity=row["quantity"] + 1, reason="RECOUNT",
    )
    if row["site"] == site:
        assert not is_err and env["data"]["preview"]["current_quantity"] == row["quantity"]
    else:
        assert is_err and error_of(env)["code"] == "SKU_NOT_FOUND"


@pytest.mark.parametrize("site,row", PAIRS, ids=IDS)
async def test_move_same_site_ok_cross_site_refused(make_client, site, row):
    prefix = {"LEEDS-01": "A", "READING-02": "B", "GLASGOW-03": "C"}[site]
    is_err, env = await call(make_client(site), "move_stock", sku=row["sku"], to_bin=f"{prefix}-99-9")
    if row["site"] == site:
        assert not is_err and env["data"]["to_bin"] == f"{prefix}-99-9"
    else:
        assert is_err and error_of(env)["code"] == "SKU_NOT_FOUND"


async def test_other_sites_sku_is_indistinguishable_from_a_nonexistent_sku(leeds):
    _, other = await call(leeds, "move_stock", sku="SKU-8805", to_bin="A-01-1")  # Reading's item
    _, ghost = await call(leeds, "move_stock", sku="SKU-9999", to_bin="A-01-1")  # exists nowhere
    a, b = error_of(other), error_of(ghost)
    for key in ("code", "retryable", "parameter", "valid_values", "how_to_fix", "suggested_call", "problems"):
        assert a[key] == b[key]
    assert a["message"].replace("SKU-8805", "X") == b["message"].replace("SKU-9999", "X")
    for site in ("READING-02", "GLASGOW-03"):
        assert site not in str(other)


TOOL_CALLS = {
    "search_products": {"query": "pallet wrap"},
    "list_dock_slots": {"date": DATE},
    "list_exceptions": {},
    "book_dock_slot": {"date": DATE, "slot": "06:00", "carrier": "Acme Ltd"},
    "move_stock": {"sku": "SKU-8801", "to_bin": "A-12-9"},
    "raise_exception": {"category": "OTHER", "summary": "Dock door sticking open"},
    "close_exception": {"exception_id": "EXC-0001", "resolution_note": "Fixed the door hinge"},
    "reopen_exception": {"exception_id": "EXC-0001", "reason": "Hinge failed again today"},
    "prepare_stock_adjustment": {"sku": "SKU-8801", "counted_quantity": 200, "reason": "RECOUNT"},
    "prepare_dock_cancellation": {"date": DATE, "slot": "08:00", "reason": "CARRIER_NO_SHOW"},
    "confirm_action": {"confirmation_token": "CONF-0123456789abcdef"},
}


@pytest.mark.parametrize("tool", TOOL_CALLS)
async def test_a_caller_supplied_site_is_rejected_by_every_tool(leeds, tool):
    is_err, env = await call(leeds, tool, **TOOL_CALLS[tool], site="READING-02")
    err = error_of(env)
    assert is_err and err["code"] == "INVALID_ARGUMENTS"
    prob = next(p for p in err["problems"] if p["parameter"] == "site")
    assert "fixed to LEEDS-01" in prob["problem"]
    assert "READING-02" not in err["how_to_fix"] and "Remove `site`" in err["how_to_fix"]


@pytest.mark.parametrize("site", SITES)
async def test_dock_view_contains_only_this_sites_slots(make_client, site):
    _, env = await call(make_client(site), "list_dock_slots", date=DATE)
    expected = [(r["slot"], r["status"], r["carrier"]) for r in DOCK if r["site"] == site]
    got = [(s["slot"], s["status"], s["carrier"]) for s in env["data"]["slots"]]
    assert got == expected and len(got) == 6


async def test_a_booking_at_one_site_does_not_touch_another(leeds, reading):
    _, env = await call(leeds, "book_dock_slot", date=DATE, slot="06:00", carrier="Acme Ltd")
    assert env["ok"]
    _, rv = await call(reading, "list_dock_slots", date=DATE)
    assert next(s for s in rv["data"]["slots"] if s["slot"] == "06:00")["carrier"] == "Northbound Freight"
    _, lv = await call(leeds, "list_dock_slots", date=DATE)
    assert next(s for s in lv["data"]["slots"] if s["slot"] == "06:00")["carrier"] == "Acme Ltd"


async def test_exceptions_are_invisible_and_untouchable_from_other_sites(leeds, reading):
    _, made = await call(leeds, "raise_exception", category="DAMAGED", sku="SKU-8801",
                         summary="Two pallets of wrap crushed in bay 3")
    ticket = made["data"]["exception_id"]
    _, listing = await call(reading, "list_exceptions", status="all")
    assert listing["data"]["count"] == 0
    for tool, args in (("close_exception", {"resolution_note": "Cleared by Reading staff"}),
                       ("reopen_exception", {"reason": "Trying from the wrong site"})):
        is_err, env = await call(reading, tool, exception_id=ticket, **args)
        assert is_err and error_of(env)["code"] == "EXCEPTION_NOT_FOUND"
    is_err, env = await call(reading, "raise_exception", category="DAMAGED", sku="SKU-8801",
                             summary="Reading staff trying to use a Leeds SKU")
    assert is_err and error_of(env)["code"] == "SKU_NOT_FOUND"
    _, still = await call(leeds, "list_exceptions")
    assert still["data"]["count"] == 1 and still["data"]["exceptions"][0]["status"] == "open"


async def test_a_confirmation_token_is_bound_to_its_site_and_not_burned_by_a_stranger(leeds, reading):
    _, prep = await call(leeds, "prepare_stock_adjustment", sku="SKU-8801", counted_quantity=230, reason="RECOUNT")
    token = prep["data"]["confirmation_token"]
    is_err, env = await call(reading, "confirm_action", confirmation_token=token)
    assert is_err and error_of(env)["code"] == "CONFIRMATION_INVALID"
    is_err, env = await call(leeds, "confirm_action", confirmation_token=token)  # still usable by its owner
    assert not is_err and env["data"]["result"]["after"] == 230


def test_server_refuses_to_start_without_a_valid_site():
    for bad in (None, "", "PARIS-09", "leeds-01"):
        with pytest.raises(SystemExit):
            resolve_site(bad)
        with pytest.raises(SystemExit):
            build_server(bad)  # type: ignore[arg-type]
    assert resolve_site("READING-02") == "READING-02"


def test_the_stdio_entry_point_exits_non_zero_without_a_site():
    root = Path(__file__).resolve().parents[1]
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(root / "src")}
    proc = subprocess.run([sys.executable, "-m", "kestrel_ops"], env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0 and "KESTREL_SITE" in proc.stderr
