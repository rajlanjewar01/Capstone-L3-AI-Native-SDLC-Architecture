"""Lookup honesty: every plausible match is returned; one match is answered without a nag."""
from __future__ import annotations

import pytest

from helpers import STOCK, call, skus_of

CASES = [
    # site fixture name, query, expected SKUs, expected resolution
    ("leeds", "pallet wrap", ["SKU-8801", "SKU-8802"], "multiple_matches"),
    ("leeds", "strapping band", ["SKU-8803", "SKU-8804"], "multiple_matches"),
    ("leeds", "pallet", ["SKU-8801", "SKU-8802", "SKU-8815", "SKU-8816"], "multiple_matches"),
    ("leeds", "clear pallet wrap", ["SKU-8801"], "single_match"),
    ("leeds", "12mm strapping", ["SKU-8803"], "single_match"),
    ("leeds", "16 mm strapping band", ["SKU-8804"], "single_match"),
    ("leeds", "pallet euro", ["SKU-8816"], "single_match"),
    ("leeds", "void fill", ["SKU-8811"], "single_match"),  # unambiguous once scoped to Leeds
    ("leeds", "SKU-8801", ["SKU-8801"], "single_match"),
    ("leeds", "8802", ["SKU-8802"], "single_match"),
    ("leeds", "how many pallet wrap do we have", ["SKU-8801", "SKU-8802"], "multiple_matches"),
    ("reading", "corner protector", ["SKU-8805", "SKU-8806"], "multiple_matches"),
    ("reading", "tape", ["SKU-8812", "SKU-8813"], "multiple_matches"),
    ("reading", "tape clear", ["SKU-8812"], "single_match"),
    ("reading", "50mm corner protector", ["SKU-8805"], "single_match"),
    ("reading", "edge board", ["SKU-8807"], "single_match"),
    ("glasgow", "shrink film", ["SKU-8808", "SKU-8809"], "multiple_matches"),
    ("glasgow", "label roll", ["SKU-8814"], "single_match"),
    ("glasgow", "void fill", ["SKU-8810"], "single_match"),
]


@pytest.mark.parametrize("site,query,expected,resolution", CASES)
async def test_match_sets_and_resolution(request, site, query, expected, resolution):
    client = request.getfixturevalue(site)
    is_err, env = await call(client, "search_products", query=query)
    assert not is_err
    assert skus_of(env) == expected
    assert env["data"]["resolution"] == resolution
    assert env["data"]["match_count"] == len(expected)


@pytest.mark.parametrize("row", STOCK, ids=lambda r: r["sku"])
async def test_a_full_description_always_finds_exactly_that_item(make_client, row):
    """Never demands disambiguation where there is genuinely one match."""
    _, env = await call(make_client(row["site"]), "search_products", query=row["description"])
    assert skus_of(env) == [row["sku"]]
    assert env["data"]["resolution"] == "single_match"
    cand = env["data"]["candidates"][0]
    assert (cand["bin"], cand["quantity"], cand["unit"]) == (row["bin"], row["quantity"], row["unit"])


async def test_multiple_matches_tell_the_agent_what_differs_and_not_to_guess(leeds):
    _, env = await call(leeds, "search_products", query="pallet wrap")
    assert env["data"]["disambiguate_by"] == ["clear", "black"]
    assert "Do NOT pick one" in env["guidance"]


async def test_single_match_has_no_disambiguation_demand(leeds):
    _, env = await call(leeds, "search_products", query="void fill")
    assert env["data"]["disambiguate_by"] == []
    assert "answer directly" in env["guidance"]


async def test_out_of_stock_is_a_valid_answer_not_an_error(glasgow):
    is_err, env = await call(glasgow, "search_products", query="600mm shrink film")
    assert not is_err
    cand = env["data"]["candidates"][0]
    assert cand["sku"] == "SKU-8809" and cand["quantity"] == 0 and cand["in_stock"] is False
    assert cand["unit"] == "roll"


@pytest.mark.parametrize("site,query", [("leeds", "strapping 14mm"), ("reading", "corner protector 60mm"),
                                        ("glasgow", "shrink film 500mm"),
                                        ("leeds", "50mm pallet wrap"), ("glasgow", "40mm shrink film")])
async def test_numbers_never_fuzzy_match(request, site, query):
    """12 vs 16 and 50 vs 500 are one character apart; a wrong size must not be returned."""
    _, env = await call(request.getfixturevalue(site), "search_products", query=query)
    assert env["data"]["resolution"] == "no_match" and env["data"]["candidates"] == []


async def test_misspelling_is_labelled_approximate_even_for_a_single_item(glasgow, leeds):
    _, env = await call(glasgow, "search_products", query="labell roll")
    assert skus_of(env) == ["SKU-8814"]
    assert env["data"]["match_type"] == "approximate"
    assert env["data"]["resolution"] == "needs_confirmation"
    assert "confirm" in env["guidance"].lower()
    _, env2 = await call(leeds, "search_products", query="palet wrap")
    assert env2["data"]["resolution"] == "needs_confirmation" and len(env2["data"]["candidates"]) == 2


async def test_no_match_says_so_and_does_not_hint_at_other_sites(leeds):
    _, env = await call(leeds, "search_products", query="forklift")
    assert env["data"]["resolution"] == "no_match"
    assert "elsewhere" in env["guidance"] and "not suggest" in env["guidance"]


async def test_query_of_only_filler_words_matches_nothing(leeds):
    _, env = await call(leeds, "search_products", query="how many do we have")
    assert env["data"]["resolution"] == "no_match"
