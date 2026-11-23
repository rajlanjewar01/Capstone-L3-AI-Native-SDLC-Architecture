"""The published interface: names, schemas, closed sets, read/write distinguishability."""
from __future__ import annotations

import pytest

from helpers import ALL_SLOTS, DOCK

EXPECTED = {
    "search_products", "list_dock_slots", "list_exceptions", "book_dock_slot", "move_stock",
    "raise_exception", "close_exception", "reopen_exception", "prepare_stock_adjustment",
    "prepare_dock_cancellation", "confirm_action",
}
READ_ONLY = {"search_products", "list_dock_slots", "list_exceptions",
             "prepare_stock_adjustment", "prepare_dock_cancellation"}
REVERSIBLE_WRITES = {"book_dock_slot", "move_stock", "raise_exception", "close_exception", "reopen_exception"}


async def tools_by_name(client):
    return {t.name: t for t in (await client.list_tools()).tools}


async def test_exactly_the_designed_tools_exist(leeds):
    assert set(await tools_by_name(leeds)) == EXPECTED


async def test_no_tool_accepts_a_site_parameter_and_all_reject_extras(leeds):
    for name, tool in (await tools_by_name(leeds)).items():
        schema = tool.input_schema
        assert "site" not in schema["properties"], name
        assert schema["additionalProperties"] is False, name


async def test_slot_enum_in_schema_equals_the_data(leeds):
    data_slots = sorted({r["slot"] for r in DOCK})
    assert data_slots == ALL_SLOTS
    tools = await tools_by_name(leeds)
    for name in ("book_dock_slot", "prepare_dock_cancellation"):
        assert tools[name].input_schema["properties"]["slot"]["enum"] == data_slots


async def test_closed_value_sets_are_enums_in_the_schema(leeds):
    tools = await tools_by_name(leeds)
    props = lambda n: tools[n].input_schema["properties"]  # noqa: E731
    assert props("raise_exception")["category"]["enum"] == ["DAMAGED", "MISSING", "WRONG_ITEM", "OTHER"]
    assert "RECOUNT" in props("prepare_stock_adjustment")["reason"]["enum"]
    assert "CARRIER_NO_SHOW" in props("prepare_dock_cancellation")["reason"]["enum"]
    assert props("list_dock_slots")["status"]["enum"] == ["available", "booked", "all"]
    assert props("list_exceptions")["status"]["enum"] == ["open", "closed", "all"]
    # identifiers are pattern-constrained, not free text
    assert props("move_stock")["sku"]["pattern"] == r"^SKU-\d{4}$"
    assert "pattern" in props("confirm_action")["confirmation_token"]
    # counts are bounded integers
    qty = props("prepare_stock_adjustment")["counted_quantity"]
    assert qty["type"] == "integer" and qty["minimum"] == 0


async def test_read_only_and_state_changing_tools_are_distinguishable(leeds):
    tools = await tools_by_name(leeds)
    for name in READ_ONLY:
        assert tools[name].annotations.read_only_hint is True, name
        assert tools[name].description.startswith(("[READ-ONLY]", "[PREVIEW")), name
    for name in REVERSIBLE_WRITES:
        a = tools[name].annotations
        assert a.read_only_hint is False and a.destructive_hint is False, name
        assert tools[name].description.startswith("[CHANGES DATA - reversible]"), name
    confirm = tools["confirm_action"]
    assert confirm.annotations.read_only_hint is False
    assert confirm.annotations.destructive_hint is True
    assert confirm.description.startswith("[CHANGES DATA - IRREVERSIBLE]")


async def test_only_one_tool_can_apply_an_irreversible_change(leeds):
    destructive = [n for n, t in (await tools_by_name(leeds)).items() if t.annotations.destructive_hint]
    assert destructive == ["confirm_action"]


async def test_preview_tools_point_at_the_confirmation_step(leeds):
    tools = await tools_by_name(leeds)
    for name in ("prepare_stock_adjustment", "prepare_dock_cancellation"):
        assert "confirm_action" in tools[name].description
        assert "explicit yes" in tools[name].description


async def test_search_description_tells_the_model_not_to_guess(leeds):
    d = (await tools_by_name(leeds))["search_products"].description
    assert "never picks a best one" in d and "multiple_matches" in d and "quantity 0" in d
