"""Product search: returns EVERY plausible match, never a 'best' one (spec C1).

Rules, each driven by the data (spec E2-E4):
* all query words must be present, as whole words or word-prefixes;
* words containing digits must match exactly ("12" must never match "16", "50" never "500");
* only if nothing matches exactly does a spelling-tolerant pass run, and anything it finds is
  labelled approximate and needs the user's confirmation even if it is a single item.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from .store import StockItem

STOPWORDS = frozenset(
    "the a an of for please some any do we have how many much is are there in on at stock with me".split()
)
UNIT_NOISE = frozenset({"mm"})


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+|\d+", text.lower())


def _variants(word: str) -> set[str]:
    out = {word}
    if len(word) > 3 and word.endswith("s"):
        out.add(word[:-1])  # bands -> band
    return out


def _exact_match(q: str, product_tokens: list[str]) -> bool:
    if q.isdigit():
        return q in product_tokens
    for v in _variants(q):
        for t in product_tokens:
            if t == v or (len(v) >= 3 and t.startswith(v)):
                return True
    return False


def _fuzzy_match(q: str, product_tokens: list[str]) -> bool:
    if q.isdigit() or len(q) < 4:
        return False  # numbers and very short words are never fuzzed
    alpha = [t for t in product_tokens if not t.isdigit()]
    return bool(difflib.get_close_matches(q, alpha, n=1, cutoff=0.8))


def _query_tokens(query: str) -> list[str]:
    return [t for t in tokens(query) if t not in STOPWORDS]


def _disambiguate_by(items: list[StockItem], query_tokens: list[str]) -> list[str]:
    sets = [set(tokens(i.description)) for i in items]
    shared = set.intersection(*sets) if sets else set()
    out: list[str] = []
    for item in items:
        for t in tokens(item.description):
            if t in shared or t in UNIT_NOISE or t in query_tokens or t in out:
                continue
            out.append(t)
    return out[:8]


def search(items: list[StockItem], query: str) -> dict[str, Any]:
    """`items` must already be restricted to the caller's site (done by the toolkit)."""
    q_tokens = _query_tokens(query)
    ordered = sorted(items, key=lambda i: i.sku)

    def haystack(i: StockItem) -> list[str]:
        return tokens(i.sku + " " + i.description)

    matches: list[StockItem] = []
    match_type = "none"
    if q_tokens:
        matches = [i for i in ordered if all(_exact_match(q, haystack(i)) for q in q_tokens)]
        if matches:
            match_type = "exact_terms"
        else:
            matches = [
                i
                for i in ordered
                if all(_exact_match(q, haystack(i)) or _fuzzy_match(q, haystack(i)) for q in q_tokens)
            ]
            if matches:
                match_type = "approximate"

    if match_type == "none":
        resolution = "no_match"
    elif match_type == "approximate":
        resolution = "needs_confirmation"
    elif len(matches) == 1:
        resolution = "single_match"
    else:
        resolution = "multiple_matches"

    return {
        "query": query,
        "match_type": match_type,
        "resolution": resolution,
        "match_count": len(matches),
        "candidates": [
            {
                "sku": i.sku,
                "description": i.description,
                "bin": i.bin,
                "quantity": i.quantity,
                "unit": i.unit,
                "in_stock": i.quantity > 0,
            }
            for i in matches
        ],
        "disambiguate_by": _disambiguate_by(matches, q_tokens) if len(matches) > 1 else [],
    }


GUIDANCE = {
    "single_match": "Exactly one product at this site matches. You can answer directly; state the quantity with its unit (and say out of stock if quantity is 0).",
    "multiple_matches": "More than one product matches. Do NOT pick one. Ask the user which they mean using disambiguate_by (e.g. 'clear or black?'), or report each item separately if they asked about all of them.",
    "needs_confirmation": "No exact match; these are the closest by spelling only. Ask the user to confirm the item before relying on it.",
    "no_match": "Nothing at this site matches. Ask the user to rephrase or give another word from the product name. Do not guess, and do not suggest the item is stocked elsewhere.",
}
