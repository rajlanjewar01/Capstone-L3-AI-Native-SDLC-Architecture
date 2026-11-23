# Changes from the requested design

Ops asked for **5 tools**. The toolkit has **11**. Each change names the data or requirement
that drove it and the test that proves it. (Full reasoning: `spec.md` section 2.)

| # | Ops asked for | Built instead | Why (evidence) | Proved by |
|---|---|---|---|---|
| 1 | `lookup`: "get back where it is and how many" from a rough name | `search_products`: returns **every** plausible match with `resolution` and `disambiguate_by`; never a best match | Names are not keys: 8801/8802 differ only by clear/black, and six pairs sit inside one site (`stock_snapshot.csv`). A best-match lookup would confidently return the wrong pallet wrap. | `test_search.py::test_match_sets_and_resolution` |
| 1b | (same) | A single match is answered directly, with no disambiguation demanded | After scoping, "void fill" is one item at Leeds (8811) and one at Glasgow (8810); an always-ask design nags where there is one answer | `test_search.py` cases `void fill`, `label roll`, `clear pallet wrap`; `test_a_full_description_always_finds_exactly_that_item` (all 16 SKUs) |
| 1c | (same) | Numbers must match **exactly**; misspellings are labelled `approximate` / `needs_confirmation` | 12mm vs 16mm, 50 vs 500, 400 vs 600 are one character apart | `test_numbers_never_fuzzy_match`; mutation check (see REFLECTION) |
| 1d | (same) | Quantity 0 and units are returned as data | SKU-8809 is at 0 (out of stock is an answer); units differ (each/roll/bale/box) | `test_out_of_stock_is_a_valid_answer_not_an_error` |
| 2 | `check_dock`: list **and** book **and** cancel in one tool | `list_dock_slots` (read-only), `book_dock_slot` (reversible), `prepare_dock_cancellation` -> `confirm_action` | One name for reading and writing makes the model choose risk by argument; cancelling frees a carrier's slot someone else can take, so it is not safely undoable | `test_tool_surface.py` (annotations), `test_confirmation.py` cancellation tests |
| 3 | `stock_change`: correct a count **and** move bins, "the same kind of thing really" | `move_stock` (location only, reversible) and `prepare_stock_adjustment` -> `confirm_action` (quantity, irreversible) | A move conserves quantity and can be undone; a correction "feeds the month-end count" (Ops notes) and cannot | `test_move_stock_changes_the_bin_and_nothing_else` (ledger untouched); `test_confirm_applies_...` (ledger entry) |
| 4 | (implied) a quantity change | Adjustment takes the **absolute counted quantity**, with before/after/delta preview and a `LARGE_CHANGE` warning | A delta applied twice by an agent retry double-counts into month-end | `test_stale_preview_is_refused_...`, `test_large_changes_carry_a_warning` |
| 5 | Nothing about confirmation | Irreversible actions need a **preview token** (single-use, 5 min, site-bound, state-bound) | A `confirm=true` flag can be set without a human seeing anything; a token cannot exist before a preview | `test_confirmation.py` (single use, expiry, stale, wrong site) |
| 6 | `raise_exception`: "category, a few words, which SKU" | `category` is an enum; `sku` required for DAMAGED/MISSING/WRONG_ITEM; duplicate open ticket refused unless `allow_duplicate` | Category list was undefined; retries would open duplicates | `test_missing_sku_for_damaged_...`, `test_duplicate_ticket_can_be_overridden_...` |
| 7 | `close_exception` only | + `reopen_exception`, + `list_exceptions` | Ops asked for an operation with no reverse: I added the reverse so closing stays fast (no confirmation). `list_exceptions` because staff should not type ticket ids ("don't make us type SKU codes"). | `test_exception_lifecycle_raise_list_close_reopen` |
| 8 | "Someone at Leeds could see Reading's numbers" (a note) | No tool has a `site` parameter; the site is bound from `KESTREL_SITE`, validated at startup (fails closed) and applied in a single choke point; other-site records look exactly like nonexistent ones | A `site` parameter is a trusted input. An existence oracle would still leak that Reading stocks something. | `test_site_scoping.py`: 48 site x SKU pairs per tool, `site` rejected on all 11 tools, indistinguishable errors, startup refusal |
| 9 | "Say something that makes sense, not `ERR_4001`" (a note) | One structured error: `code`, `message`, `retryable`, `how_to_fix`, `valid_values`, `suggested_call`, per-field `problems` | A model can only recover if the error says what a correct call looks like | `test_errors.py`: shape for every code; replaying `suggested_call` succeeds |

## What I did not change (and why)
* **Dock booking has no confirmation.** It is reversible with the cancellation flow and low-risk; Ops asked for speed.
* **Carrier is free text.** The data has one carrier ("Northbound Freight"); inventing a closed list would be fiction.
* **No partial bin moves.** The data holds one bin per SKU.

## Assumptions to confirm with Ops
Exception categories, adjustment/cancellation reason lists, the 50% large-change threshold and the bin-prefix
rule are my proposals (spec section 6).
