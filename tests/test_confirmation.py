"""Irreversible actions need a preview, then a single-use token. Previews change nothing."""
from __future__ import annotations

import pytest

from helpers import DATE, call, error_of

TOKEN_OK = "CONF-0123456789abcdef"


async def quantity(client, query="SKU-8801"):
    _, env = await call(client, "search_products", query=query)
    return env["data"]["candidates"][0]["quantity"]


async def prep(client, count=200, sku="SKU-8801", reason="RECOUNT"):
    is_err, env = await call(client, "prepare_stock_adjustment", sku=sku, counted_quantity=count, reason=reason)
    assert not is_err, env
    return env["data"]["confirmation_token"], env


async def test_prepare_shows_a_preview_and_changes_nothing(leeds, warehouse):
    token, env = await prep(leeds, 200)
    p = env["data"]["preview"]
    assert (p["current_quantity"], p["counted_quantity"], p["delta"]) == (240, 200, -40)
    assert "cannot be undone" in p["summary"] and "NOTHING HAS CHANGED" in env["guidance"]
    assert token.startswith("CONF-") and env["data"]["expires_in_seconds"] == 300
    assert await quantity(leeds) == 240 and warehouse.ledger == [] and warehouse.audit == []


async def test_confirm_applies_exactly_the_previewed_change_and_writes_the_ledger(leeds, warehouse):
    token, _ = await prep(leeds, 200)
    is_err, env = await call(leeds, "confirm_action", confirmation_token=token)
    assert not is_err and env["data"]["action"] == "stock_adjustment"
    assert await quantity(leeds) == 200
    (entry,) = warehouse.ledger
    assert (entry["before"], entry["after"], entry["delta"], entry["reason"]) == (240, 200, -40, "RECOUNT")
    assert warehouse.audit[-1]["tool"] == "confirm_action"


async def test_a_token_works_only_once(leeds):
    token, _ = await prep(leeds, 200)
    await call(leeds, "confirm_action", confirmation_token=token)
    is_err, env = await call(leeds, "confirm_action", confirmation_token=token)
    assert is_err and error_of(env)["code"] == "CONFIRMATION_INVALID"
    assert await quantity(leeds) == 200  # not applied twice


async def test_an_expired_token_is_refused_and_changes_nothing(leeds, clock):
    token, _ = await prep(leeds, 200)
    clock.advance(301)
    is_err, env = await call(leeds, "confirm_action", confirmation_token=token)
    assert is_err and error_of(env)["code"] == "CONFIRMATION_EXPIRED"
    assert await quantity(leeds) == 240


async def test_a_token_just_inside_the_window_still_works(leeds, clock):
    token, _ = await prep(leeds, 200)
    clock.advance(299)
    is_err, _ = await call(leeds, "confirm_action", confirmation_token=token)
    assert not is_err


async def test_a_well_formed_but_never_issued_token_is_refused(leeds):
    is_err, env = await call(leeds, "confirm_action", confirmation_token=TOKEN_OK)
    assert is_err and error_of(env)["code"] == "CONFIRMATION_INVALID"


async def test_a_malformed_token_is_a_schema_rejection(leeds):
    is_err, env = await call(leeds, "confirm_action", confirmation_token="yes")
    assert is_err and error_of(env)["code"] == "INVALID_ARGUMENTS"


async def test_stale_preview_is_refused_when_the_quantity_changed_in_between(leeds):
    first, _ = await prep(leeds, 200)
    second, _ = await prep(leeds, 210)
    assert (await call(leeds, "confirm_action", confirmation_token=second))[0] is False
    is_err, env = await call(leeds, "confirm_action", confirmation_token=first)
    err = error_of(env)
    assert is_err and err["code"] == "CONFIRMATION_STALE" and "240" in err["message"] and "210" in err["message"]
    assert err["suggested_call"]["tool"] == "prepare_stock_adjustment"
    assert await quantity(leeds) == 210


async def test_no_change_is_reported_not_previewed(leeds):
    is_err, env = await call(leeds, "prepare_stock_adjustment", sku="SKU-8801", counted_quantity=240, reason="RECOUNT")
    assert is_err and error_of(env)["code"] == "NO_CHANGE"


async def test_large_changes_carry_a_warning(leeds):
    _, env = await prep(leeds, 20)
    assert any(w.startswith("LARGE_CHANGE") for w in env["data"]["preview"]["warnings"])
    _, small = await prep(leeds, 230)
    assert small["data"]["preview"]["warnings"] == []


async def test_counting_up_from_zero_is_previewable(glasgow):
    _, env = await call(glasgow, "prepare_stock_adjustment", sku="SKU-8809", counted_quantity=12, reason="FOUND_STOCK")
    assert env["data"]["preview"]["delta"] == 12


@pytest.mark.parametrize("bad", [-1, 1_000_001, "12", 12.5, True])
async def test_counted_quantity_is_a_bounded_integer(leeds, bad):
    is_err, env = await call(leeds, "prepare_stock_adjustment", sku="SKU-8801", counted_quantity=bad, reason="RECOUNT")
    assert is_err and error_of(env)["code"] == "INVALID_ARGUMENTS"


async def test_reason_must_come_from_the_closed_set(leeds):
    is_err, env = await call(leeds, "prepare_stock_adjustment", sku="SKU-8801", counted_quantity=200, reason="boss said so")
    err = error_of(env)
    assert is_err and err["problems"][0]["valid_values"] == [
        "RECOUNT", "DAMAGE_WRITE_OFF", "FOUND_STOCK", "DATA_ENTRY_ERROR", "OTHER"]


# ---- dock cancellation ---------------------------------------------------
async def test_cancellation_previews_the_carrier_then_frees_the_slot(leeds):
    _, env = await call(leeds, "prepare_dock_cancellation", date=DATE, slot="08:00", reason="CARRIER_NO_SHOW")
    assert env["data"]["preview"]["carrier"] == "Northbound Freight"
    _, view = await call(leeds, "list_dock_slots", date=DATE, status="booked")
    assert {s["slot"] for s in view["data"]["slots"]} == {"08:00", "12:00"}  # untouched by the preview
    token = env["data"]["confirmation_token"]
    is_err, done = await call(leeds, "confirm_action", confirmation_token=token)
    assert not is_err and done["data"]["result"]["cancelled_carrier"] == "Northbound Freight"
    _, after = await call(leeds, "list_dock_slots", date=DATE, status="available")
    assert "08:00" in {s["slot"] for s in after["data"]["slots"]}
    assert (await call(leeds, "book_dock_slot", date=DATE, slot="08:00", carrier="Acme Ltd"))[0] is False


async def test_cancelling_a_free_slot_is_an_error(leeds):
    is_err, env = await call(leeds, "prepare_dock_cancellation", date=DATE, slot="06:00", reason="OTHER")
    assert is_err and error_of(env)["code"] == "SLOT_NOT_BOOKED"


async def test_cancellation_token_goes_stale_if_the_booking_already_changed(leeds):
    t1 = (await call(leeds, "prepare_dock_cancellation", date=DATE, slot="08:00", reason="CARRIER_NO_SHOW"))[1]["data"]["confirmation_token"]
    t2 = (await call(leeds, "prepare_dock_cancellation", date=DATE, slot="08:00", reason="CARRIER_NO_SHOW"))[1]["data"]["confirmation_token"]
    assert (await call(leeds, "confirm_action", confirmation_token=t1))[0] is False
    is_err, env = await call(leeds, "confirm_action", confirmation_token=t2)
    assert is_err and error_of(env)["code"] == "CONFIRMATION_STALE"


async def test_reason_for_cancellation_is_a_closed_set(leeds):
    is_err, env = await call(leeds, "prepare_dock_cancellation", date=DATE, slot="08:00", reason="felt like it")
    assert is_err and "CARRIER_NO_SHOW" in error_of(env)["problems"][0]["valid_values"]
