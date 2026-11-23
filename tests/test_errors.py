"""Every failure is one actionable shape the model can self-correct from (no ERR_4001)."""
from __future__ import annotations

import json

import pytest

from helpers import ALL_SLOTS, DATE, SITES, call, error_of
from kestrel_ops.toolkit import Toolkit

KEYS = {"code", "message", "retryable", "parameter", "received", "valid_values",
        "how_to_fix", "suggested_call", "problems"}


async def raise_ticket(client, **over):
    args = dict(category="DAMAGED", sku="SKU-8801", summary="Two pallets of wrap crushed in bay 3")
    args.update(over)
    return await call(client, "raise_exception", **args)


# Each entry triggers one catalogue code from a fresh Leeds session.
async def _sku_not_found(c): return await call(c, "move_stock", sku="SKU-9999", to_bin="A-01-1")
async def _bin_not_at_site(c): return await call(c, "move_stock", sku="SKU-8801", to_bin="B-01-1")
async def _same_bin(c): return await call(c, "move_stock", sku="SKU-8801", to_bin="A-12-3")
async def _no_change(c): return await call(c, "prepare_stock_adjustment", sku="SKU-8801", counted_quantity=240, reason="RECOUNT")
async def _date(c): return await call(c, "list_dock_slots", date="2026-04-09")
async def _booked(c): return await call(c, "book_dock_slot", date=DATE, slot="08:00", carrier="Acme Ltd")
async def _not_booked(c): return await call(c, "prepare_dock_cancellation", date=DATE, slot="06:00", reason="OTHER")
async def _exc_nf(c): return await call(c, "close_exception", exception_id="EXC-0042", resolution_note="Nothing to see here")
async def _conf_invalid(c): return await call(c, "confirm_action", confirmation_token="CONF-0123456789abcdef")
async def _invalid_args(c): return await call(c, "book_dock_slot", date=DATE, slot="25:00", carrier="Acme Ltd")
async def _unknown_tool(c): return await call(c, "lookup", query="pallet wrap")


async def _already_closed(c):
    _, made = await raise_ticket(c)
    i = made["data"]["exception_id"]
    await call(c, "close_exception", exception_id=i, resolution_note="Replaced the pallets")
    return await call(c, "close_exception", exception_id=i, resolution_note="Replaced the pallets")


async def _already_open(c):
    _, made = await raise_ticket(c)
    return await call(c, "reopen_exception", exception_id=made["data"]["exception_id"], reason="Not actually resolved")


async def _duplicate(c):
    await raise_ticket(c)
    return await raise_ticket(c)


CODES = {
    "SKU_NOT_FOUND": _sku_not_found, "BIN_NOT_AT_SITE": _bin_not_at_site, "SAME_BIN": _same_bin,
    "NO_CHANGE": _no_change, "DATE_NOT_SCHEDULED": _date, "SLOT_ALREADY_BOOKED": _booked,
    "SLOT_NOT_BOOKED": _not_booked, "EXCEPTION_NOT_FOUND": _exc_nf, "CONFIRMATION_INVALID": _conf_invalid,
    "INVALID_ARGUMENTS": _invalid_args, "UNKNOWN_TOOL": _unknown_tool, "ALREADY_CLOSED": _already_closed,
    "ALREADY_OPEN": _already_open, "DUPLICATE_OPEN_EXCEPTION": _duplicate,
}


@pytest.mark.parametrize("code", CODES)
async def test_every_error_has_the_one_documented_shape(leeds, code):
    is_err, env = await CODES[code](leeds)
    assert is_err is True and env["ok"] is False
    err = env["error"]
    assert KEYS <= set(err)
    assert err["code"] == code
    assert isinstance(err["retryable"], bool)
    assert len(err["message"]) > 15 and len(err["how_to_fix"]) > 15


@pytest.mark.parametrize("code", CODES)
async def test_errors_are_plain_english_and_leak_nothing(leeds, code):
    _, env = await CODES[code](leeds)
    text = json.dumps(env)
    assert "ERR_" not in text and "Traceback" not in text and ".py" not in text
    for other in ("READING-02", "GLASGOW-03"):
        assert other not in text  # errors never mention any other site


async def test_expired_and_stale_confirmations_have_the_shape_too(leeds, clock):
    _, prep = await call(leeds, "prepare_stock_adjustment", sku="SKU-8801", counted_quantity=200, reason="RECOUNT")
    clock.advance(400)
    _, env = await call(leeds, "confirm_action", confirmation_token=prep["data"]["confirmation_token"])
    assert KEYS <= set(error_of(env)) and error_of(env)["code"] == "CONFIRMATION_EXPIRED"
    assert "prepare_stock_adjustment" in error_of(env)["how_to_fix"] or "prepare_" in error_of(env)["how_to_fix"]


async def test_internal_faults_are_opaque_but_retryable(leeds, monkeypatch):
    async def boom(self, a):
        raise RuntimeError("secret /srv/db/password.txt exploded")
    monkeypatch.setattr(Toolkit, "search_products", boom)
    is_err, env = await call(leeds, "search_products", query="pallet wrap")
    err = error_of(env)
    assert is_err and err["code"] == "INTERNAL_ERROR" and err["retryable"] is True
    assert "secret" not in json.dumps(env) and "password" not in json.dumps(env)
    assert err["error_id"] in err["how_to_fix"]


# ---- INVALID_ARGUMENTS gives the model what it needs to fix the call -----------------------------
async def test_a_bad_enum_value_lists_the_valid_values_and_an_example(leeds):
    _, env = await _invalid_args(leeds)
    err = error_of(env)
    (p,) = err["problems"]
    assert p["parameter"] == "slot" and p["received"] == "25:00"
    assert p["valid_values"] == ALL_SLOTS and p["example"] == "10:00"
    assert err["valid_values"] == ALL_SLOTS


async def test_every_mistake_is_reported_at_once(leeds):
    is_err, env = await call(leeds, "book_dock_slot", date="08/04/2026", slot="25:00")
    params = {p["parameter"] for p in error_of(env)["problems"]}
    assert is_err and params == {"date", "slot", "carrier"}  # bad format, bad enum, missing


@pytest.mark.parametrize("args,param", [
    ({"date": "2026-13-45", "slot": "08:00", "carrier": "Acme Ltd"}, "date"),
    ({"date": DATE, "slot": 8, "carrier": "Acme Ltd"}, "slot"),
    ({"date": DATE, "slot": "08:00", "carrier": "A"}, "carrier"),
    ({"date": DATE, "slot": "08:00", "carrier": ["Acme"]}, "carrier"),
])
async def test_bad_values_name_the_offending_parameter(leeds, args, param):
    is_err, env = await call(leeds, "book_dock_slot", **args)
    assert is_err and error_of(env)["problems"][0]["parameter"] == param
    assert error_of(env)["problems"][0]["expected"]


async def test_sku_must_look_like_a_sku(leeds):
    _, env = await call(leeds, "move_stock", sku="8801", to_bin="A-12-5")
    p = error_of(env)["problems"][0]
    assert p["parameter"] == "sku" and p["example"] == "SKU-8801" and "SKU-" in p["expected"]


async def test_missing_sku_for_damaged_says_how_to_get_one(leeds):
    is_err, env = await call(leeds, "raise_exception", category="DAMAGED", summary="Two pallets crushed in bay 3")
    p = error_of(env)["problems"][0]
    assert is_err and p["parameter"] == "sku" and "search_products" in p["problem"]
    ok, _ = await call(leeds, "raise_exception", category="OTHER", summary="Dock door sticking open")
    assert ok is False  # OTHER needs no SKU


# ---- the model can recover without a human -------------------------------------------------------
async def run_suggested(client, env):
    s = error_of(env)["suggested_call"]
    return await call(client, s["tool"], **s["arguments"])


async def test_slot_conflict_suggestion_succeeds_when_replayed(leeds):
    _, env = await _booked(leeds)
    is_err, replay = await run_suggested(leeds, env)
    assert not is_err and replay["data"]["slot"] in error_of(env)["valid_values"]
    assert replay["data"]["carrier"] == "Acme Ltd"


async def test_unscheduled_date_suggestion_succeeds_when_replayed(leeds):
    _, env = await _date(leeds)
    assert error_of(env)["valid_values"] == [DATE] == error_of(env)["available_dates"]
    is_err, replay = await run_suggested(leeds, env)
    assert not is_err and replay["data"]["date"] == DATE


async def test_stale_confirmation_suggestion_succeeds_when_replayed(leeds):
    t1 = (await call(leeds, "prepare_stock_adjustment", sku="SKU-8801", counted_quantity=200, reason="RECOUNT"))[1]["data"]["confirmation_token"]
    t2 = (await call(leeds, "prepare_stock_adjustment", sku="SKU-8801", counted_quantity=210, reason="RECOUNT"))[1]["data"]["confirmation_token"]
    await call(leeds, "confirm_action", confirmation_token=t2)
    _, env = await call(leeds, "confirm_action", confirmation_token=t1)
    is_err, replay = await run_suggested(leeds, env)
    assert not is_err and replay["data"]["preview"]["current_quantity"] == 210


async def test_duplicate_ticket_can_be_overridden_once_the_user_confirms(leeds):
    _, env = await _duplicate(leeds)
    assert error_of(env)["existing_exception_id"] == "EXC-0001"
    is_err, second = await raise_ticket(leeds, allow_duplicate=True)
    assert not is_err and second["data"]["exception_id"] == "EXC-0002"


async def test_bad_bin_lists_this_sites_formats(leeds, reading):
    _, env = await call(leeds, "move_stock", sku="SKU-8801", to_bin="B-01-1")
    assert error_of(env)["valid_values"] == ["A-nn-n", "YARD-n"]
    _, env2 = await call(reading, "move_stock", sku="SKU-8805", to_bin="YARD-1")
    assert error_of(env2)["valid_values"] == ["B-nn-n"]
