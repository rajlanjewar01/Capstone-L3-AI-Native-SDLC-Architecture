# Kestrel Warehouse Ops MCP Toolkit — Interface Specification

Status: written **before any source code exists** (commit `01-spec`).
Inputs read first: `data/tool_specification.md` (Ops' wish-list), `data/stock_snapshot.csv`,
`data/dock_schedule.jsonl`, `starter/PROCESS.md`, the case brief.

This document is the design. Ops' document is a requirements list, not a design, and five
of its tools change shape here. Every change names the data or requirement that drove it.

---

## 1. What the data says (evidence used below)

| # | Finding | Source |
|---|---|---|
| E1 | 16 SKUs, each stocked at exactly **one** site: LEEDS-01 (8801–8804, 8811, 8815, 8816), READING-02 (8805–8807, 8812, 8813), GLASGOW-03 (8808–8810, 8814). | `stock_snapshot.csv` |
| E2 | Descriptions differ by **one word or one number**: 8801/8802 (clear/black), 8803/8804 (12mm/16mm), 8805/8806 (50mm/75mm), 8808/8809 (400mm/600mm), 8812/8813 (clear/printed), 8815/8816 (standard UK/euro), 8810/8811 (paper/air pillow). Six pairs sit inside a single site. | `stock_snapshot.csv` |
| E3 | A name is therefore **not a key**. "Pallet wrap" at Leeds matches two items; "tape" at Reading matches two; "pallet" at Leeds matches four (8801, 8802, 8815, 8816). | E2 |
| E4 | After site scoping some names *are* unambiguous: "void fill" is only 8811 at Leeds and only 8810 at Glasgow; "label roll" is only 8814; "edge board" is only 8807; "clear pallet wrap" is only 8801. A design that always demands disambiguation would nag the user here. | E1, E2 |
| E5 | SKU 8809 has quantity **0**. Out of stock is a valid answer, not an error. | `stock_snapshot.csv` |
| E6 | Units differ (`each`, `roll`, `bale`, `box`) so a bare number is misleading. | `stock_snapshot.csv` |
| E7 | Bin formats: `A-12-3` (aisle letter = site: A Leeds, B Reading, C Glasgow) and `YARD-1`/`YARD-2` (Leeds only). One SKU per bin; one bin per SKU. | `stock_snapshot.csv` |
| E8 | Dock schedule is **one date** (2026-04-08), six slots per site (06:00, 08:00, 10:00, 12:00, 14:00, 16:00): Leeds 08:00 and 12:00 booked, Reading 06:00 and 14:00 booked, Glasgow 10:00 booked. Only one carrier appears. | `dock_schedule.jsonl` |
| E9 | "Stock corrections feed the month-end count so they need to be right." | Ops notes |
| E10 | "Someone at Leeds could see Reading's numbers and quoted them to a customer. That shouldn't be possible." | Ops notes |
| E11 | "Don't make us type SKU codes… we're wearing gloves." "The old system just said `ERR_4001`." | Ops notes |

---

## 2. Changes from the requested design

Ops asked for 5 tools. This design has **11**, because three of the five were really
several operations with different risk, and a lookup cannot keep the promise it made.

| # | Requested | Problem | Design decision | Driven by |
|---|---|---|---|---|
| C1 | `lookup` ("get back where it is and how many") | Promises one answer from a name. Names are not unique (E2, E3), so a best-match lookup confidently returns the wrong pallet wrap. | `search_products` returns **every** plausible match, never a "best" one, with a machine-readable `resolution` (`single_match` / `multiple_matches` / `needs_confirmation` / `no_match`) and `disambiguate_by` words (e.g. `clear`, `black`) so the agent can ask one short question. One match → answered directly, no nag. | E2, E3, E4, E11 |
| C2 | `check_dock` (list + book + cancel in one tool) | One name that both reads and writes; a model choosing between them by argument guesses wrong, and a read-only call could mutate. Cancel strands a carrier's slot and is not safely undoable (the slot can be taken meanwhile). | Split in three: `list_dock_slots` (read-only), `book_dock_slot` (reversible write), `prepare_dock_cancellation` (preview) → `confirm_action`. | E8, PROCESS "distinguishable read vs write" |
| C3 | `stock_change` ("correct a count" and "move a bin… same kind of thing really") | Not the same kind of thing. A move changes **location** only (quantity conserved, reversible by moving back). A correction changes **quantity**, feeds the month-end count and cannot be undone — only offset by another adjustment. One tool means the model must pick risk level by guessing an argument. | `move_stock` (reversible write, no confirmation) and `prepare_stock_adjustment` → `confirm_action` (irreversible, two-step). | E7, E9 |
| C4 | `stock_change` takes a quantity change | A delta (`+5`) applied twice by an agent retry double-counts into the month-end figure. | Adjustment takes an **absolute counted quantity**, so a retry converges instead of compounding, plus a preview showing before/after/delta. | E9 |
| C5 | `raise_exception` ("category, a few words, which SKU") | Category was never defined; free-text categories fragment reporting. SKU "relates to" is not always true (e.g. a damaged dock door). | `category` is a closed enum; `sku` is required for `DAMAGED`, `MISSING`, `WRONG_ITEM`, optional for `OTHER`. Duplicate open ticket for the same category+SKU is refused unless the caller says it is intentional (retry safety). | Ops wording; agent retry behaviour |
| C6 | `close_exception` only | Closing is hard to unwind with no reverse operation; Ops did not ask for one. | Position taken: add `reopen_exception` so closing stays fast (no confirmation) because it is reversible. Also add `list_exceptions` — otherwise staff must type ticket IDs, against E11. | E11 |
| C7 | Nothing (site was a "note") | A `site` parameter would be a trusted input. | **No tool has a `site` parameter.** Site is bound to the session from server configuration (`KESTREL_SITE`), validated at startup, and applied inside every handler. Unknown extra parameters (including `site`) are rejected with an explanation. | E10 |
| C8 | Nothing (errors were a "note") | `ERR_4001` ends in a phone call. | Every failure returns one structured error object with `code`, `message`, `how_to_fix`, `retryable`, and where possible `valid_values` and a `suggested_call` the agent can issue verbatim. | E11 |

**Reversibility position (checklist question "did Ops ask for an operation whose reverse
they did not ask for?")**

| Operation | Reverse | Confirmation required? |
|---|---|---|
| `book_dock_slot` | `prepare_dock_cancellation` | No — reversible, low blast radius |
| `prepare_dock_cancellation` → apply | re-book (but slot may be taken; carrier is affected) | **Yes** |
| `move_stock` | move back | No — quantity untouched |
| stock adjustment | **none by design** (ledger is append-only; correct with another adjustment) | **Yes** |
| `raise_exception` | `close_exception` | No |
| `close_exception` | `reopen_exception` (added) | No |

---

## 3. Conventions shared by all tools

### 3.1 Site binding (enforced, not requested)
* The session's site comes from environment `KESTREL_SITE` ∈ {`LEEDS-01`, `READING-02`, `GLASGOW-03`}. If it is missing or invalid the server **refuses to start** (fail closed).
* No input schema contains a `site` property. Every schema has `additionalProperties: false`.
* Every data access is filtered by the session site inside the handler. A record at another site is reported exactly as a record that does not exist (`SKU_NOT_FOUND`, `EXCEPTION_NOT_FOUND`) — the toolkit never confirms that something exists elsewhere, and never returns another site's quantities, bins or slots.
* A confirmation token issued to one site is invalid for any other site.

### 3.2 Read vs write is visible in the interface
Each description starts with a class tag, and MCP annotations are set to match:

| Tag | Meaning | `readOnlyHint` | `destructiveHint` |
|---|---|---|---|
| `[READ-ONLY]` | Changes nothing | true | – |
| `[PREVIEW – changes nothing]` | Computes a preview and issues a confirmation token | true | – |
| `[CHANGES DATA – reversible]` | Writes, can be undone | false | false |
| `[CHANGES DATA – IRREVERSIBLE]` | Writes, cannot be undone; only reachable via a preview token | false | true |

### 3.3 Success envelope
```json
{ "ok": true, "site": "LEEDS-01", "data": { ... }, "guidance": "what to do / say next" }
```

### 3.4 Error shape (single, for every failure)
Returned as an MCP tool result with `isError: true` and this JSON as text:
```json
{
  "ok": false,
  "error": {
    "code": "SLOT_ALREADY_BOOKED",
    "message": "LEEDS-01 08:00 on 2026-04-08 is already booked by Northbound Freight.",
    "retryable": false,
    "parameter": "slot",
    "received": "08:00",
    "valid_values": ["06:00", "10:00", "14:00", "16:00"],
    "how_to_fix": "Choose one of the free slots, or cancel the existing booking with prepare_dock_cancellation.",
    "suggested_call": { "tool": "book_dock_slot", "arguments": { "date": "2026-04-08", "slot": "10:00", "carrier": "Northbound Freight" } },
    "problems": null
  }
}
```
* `code`: stable, from the catalogue in §5. `message`: plain English, no internal codes.
* `retryable`: true only if re-sending the **same** call could succeed (e.g. an expired token needs a new preview, so `false`; a transient internal fault is `true`).
* `parameter`/`received`/`valid_values`/`suggested_call` are present when they exist, otherwise `null`.
* `INVALID_ARGUMENTS` fills `problems`: a list of `{parameter, problem, received, expected, valid_values, example}`, one per bad field, so several mistakes are fixed in one retry.
* Never included: stack traces, file paths, or anything about other sites.

### 3.5 Confirmation protocol (irreversible actions only)
1. Agent calls a `prepare_*` tool. Nothing changes. The result contains `data.preview` (before/after in plain words), `data.confirmation_token` (`CONF-…`), `data.expires_in_seconds` (300) and `guidance`.
2. The agent **shows the preview to the user and waits for an explicit yes**.
3. Agent calls `confirm_action(confirmation_token)`. The action runs only if the token is valid, unexpired, unused, issued to this site, and the underlying record still matches what the preview showed.
4. Tokens are single-use and bound to the exact arguments, site and the state seen at preview time. State changed since preview → `CONFIRMATION_STALE`; the agent must prepare again.

A boolean `confirm=true` flag was rejected: a model can set it in the first call without a human ever seeing a preview. A token can only exist after a preview round-trip.

---

## 4. Tool catalogue

Parameter notation: `str[a..b]` = string with length bounds, `enum{…}` = closed set in the JSON
schema (not prose), `pattern` = regular expression in the schema.

### 4.1 `search_products` — `[READ-ONLY]`
**Description shown to the model:**
> [READ-ONLY] Find products at YOUR site by name or SKU and return stock for every match. Pass only the product words (for example "pallet wrap", "tape clear", "SKU-8801"), not the whole question. This returns EVERY plausible match and never picks a best one. Read `data.resolution`: "single_match" → answer directly; "multiple_matches" → do NOT choose for the user: ask which one they mean using `data.disambiguate_by` (e.g. "clear or black?"), or report each item if they asked about all of them; "needs_confirmation" → spelling was only approximate, confirm the item with the user before relying on it; "no_match" → nothing at this site, ask the user to rephrase. Always say the unit, and treat quantity 0 as "out of stock", not as an error. Only your own site's stock is visible; other sites cannot be queried.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `query` | `str[2..80]` | yes | Product words or a SKU (`SKU-8801` or `8801`). |

`data`: `{ query, match_type: enum{"exact_terms","approximate","none"}, resolution: enum{"single_match","multiple_matches","needs_confirmation","no_match"}, match_count, candidates: [{sku, description, bin, quantity, unit, in_stock}], disambiguate_by: [str] }`

Behaviour: all query words must appear (whole word or word-prefix) in the SKU or description. Words containing digits (`12mm`, `50`) must match **exactly** — 12 mm and 16 mm are one character apart (E2) and must never fuzzy-match each other. Only if no exact match exists, a spelling-tolerant pass runs and any result is labelled `approximate` / `needs_confirmation`, even if it is a single item. `disambiguate_by` lists the words that differ between candidates.

### 4.2 `list_dock_slots` — `[READ-ONLY]`
> [READ-ONLY] List dock slots at YOUR site for one date, with who has booked each. Use this before booking. Dates must be ISO (YYYY-MM-DD). If the date has no schedule the error lists the dates that do.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `date` | `str`, pattern `^\d{4}-\d{2}-\d{2}$` | yes | No "today" default: the agent must not guess the date. |
| `status` | `enum{"available","booked","all"}` | no (default `all`) | |

`data`: `{ date, slots: [{slot, status, carrier}], available_count, booked_count, available_dates: [str] }`

### 4.3 `book_dock_slot` — `[CHANGES DATA – reversible]`
> [CHANGES DATA – reversible] Book a free dock slot at YOUR site for a carrier. Fails with SLOT_ALREADY_BOOKED (never overwrites) if taken; the error lists free slots. Undo with prepare_dock_cancellation.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `date` | `str`, pattern `^\d{4}-\d{2}-\d{2}$` | yes | |
| `slot` | `enum{"06:00","08:00","10:00","12:00","14:00","16:00"}` | yes | Closed set from E8. |
| `carrier` | `str[2..60]` | yes | Free text (no closed carrier list exists in the data). |

`data`: `{ date, slot, carrier, status: "booked" }`. Booking an already-booked slot is **always** an error, even for the same carrier, so a stale view never looks like success.

### 4.4 `prepare_dock_cancellation` — `[PREVIEW – changes nothing]`
> [PREVIEW – changes nothing] Step 1 of 2 for cancelling a dock booking at YOUR site. Shows which carrier would lose the slot and returns a confirmation_token. Show the preview to the user and wait for an explicit yes, then call confirm_action. Cancelling cannot be reliably undone: the slot may be rebooked by someone else.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `date` | `str`, pattern `^\d{4}-\d{2}-\d{2}$` | yes | |
| `slot` | `enum{"06:00","08:00","10:00","12:00","14:00","16:00"}` | yes | |
| `reason` | `enum{"CARRIER_NO_SHOW","CARRIER_REQUEST","BOOKED_IN_ERROR","OTHER"}` | yes | Audit trail. |

`data`: `{ preview, confirmation_token, expires_in_seconds }`. Errors: `SLOT_NOT_BOOKED` if nothing to cancel.

### 4.5 `move_stock` — `[CHANGES DATA – reversible]`
> [CHANGES DATA – reversible] Move ALL stock of one SKU to a different bin at YOUR site. Location only: quantity is not changed. To change a quantity use prepare_stock_adjustment. Undo by moving it back. Get the SKU from search_products; do not ask the user to type it.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `sku` | `str`, pattern `^SKU-\d{4}$` | yes | |
| `to_bin` | `str`, pattern `^([A-C]-\d{2}-\d\|YARD-\d)$` | yes | Must belong to this site's bin prefix (derived from E7), else `BIN_NOT_AT_SITE`. |

`data`: `{ sku, description, from_bin, to_bin, quantity, unit }`, plus `warnings` if the destination already holds another SKU. Errors: `SKU_NOT_FOUND`, `BIN_NOT_AT_SITE`, `SAME_BIN`. Partial moves are not supported: the data holds one bin per SKU (E7).

### 4.6 `prepare_stock_adjustment` — `[PREVIEW – changes nothing]`
> [PREVIEW – changes nothing] Step 1 of 2 for correcting a counted quantity at YOUR site. Provide the quantity actually counted (the new total, not the difference). Returns a before/after preview and a confirmation_token. Corrections feed the month-end count and CANNOT be undone, only offset by another adjustment, so show the preview to the user, wait for an explicit yes, then call confirm_action. For moving stock between bins use move_stock instead.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `sku` | `str`, pattern `^SKU-\d{4}$` | yes | |
| `counted_quantity` | `int`, 0..1,000,000 | yes | Absolute total (C4). |
| `reason` | `enum{"RECOUNT","DAMAGE_WRITE_OFF","FOUND_STOCK","DATA_ENTRY_ERROR","OTHER"}` | yes | |

`data`: `{ preview: {sku, description, unit, current_quantity, counted_quantity, delta, reason, warnings}, confirmation_token, expires_in_seconds }`. `warnings` includes `LARGE_CHANGE` when |delta| exceeds 50% of current. Errors: `SKU_NOT_FOUND`, `NO_CHANGE` (count equals current).

### 4.7 `confirm_action` — `[CHANGES DATA – IRREVERSIBLE]`
> [CHANGES DATA – IRREVERSIBLE] Step 2 of 2: carry out an action previously prepared with prepare_stock_adjustment or prepare_dock_cancellation. Call ONLY after the user has seen the preview and explicitly said yes. A token works once, for 5 minutes, and only for the site that prepared it.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `confirmation_token` | `str`, pattern `^CONF-[A-Za-z0-9_-]{16}$` | yes | |

`data`: `{ action: enum{"stock_adjustment","dock_cancellation"}, result: {...} }`. Errors: `CONFIRMATION_INVALID`, `CONFIRMATION_EXPIRED`, `CONFIRMATION_STALE`.

### 4.8 `raise_exception` — `[CHANGES DATA – reversible]`
> [CHANGES DATA – reversible] Open an exception ticket at YOUR site for damaged, missing or wrong stock, or another problem. For DAMAGED, MISSING and WRONG_ITEM the SKU is required: find it with search_products and confirm which item with the user if there are several. Returns the ticket id. If an identical ticket is already open you get DUPLICATE_OPEN_EXCEPTION rather than a second ticket.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `category` | `enum{"DAMAGED","MISSING","WRONG_ITEM","OTHER"}` | yes | Category list is a design assumption (see §6). |
| `summary` | `str[10..300]` | yes | |
| `sku` | `str`, pattern `^SKU-\d{4}$` | conditional | Required unless category is `OTHER`. |
| `allow_duplicate` | `bool` (default false) | no | Set true only if the user confirms a genuinely separate issue. |

`data`: `{ exception_id, category, sku, summary, status: "open" }`. Errors: `SKU_NOT_FOUND`, `DUPLICATE_OPEN_EXCEPTION` (returns `existing_exception_id`), `INVALID_ARGUMENTS` (missing sku).

### 4.9 `list_exceptions` — `[READ-ONLY]`
> [READ-ONLY] List exception tickets at YOUR site. Use this to find a ticket before closing or reopening it so the user never has to type an id.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `status` | `enum{"open","closed","all"}` | no (default `open`) | |
| `sku` | `str`, pattern `^SKU-\d{4}$` | no | |

`data`: `{ count, exceptions: [{exception_id, category, sku, summary, status, resolution_note}] }`

### 4.10 `close_exception` — `[CHANGES DATA – reversible]`
> [CHANGES DATA – reversible] Close an open exception at YOUR site with a note on what was done. Undo with reopen_exception.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `exception_id` | `str`, pattern `^EXC-\d{4}$` | yes | |
| `resolution_note` | `str[10..300]` | yes | |

Errors: `EXCEPTION_NOT_FOUND`, `ALREADY_CLOSED`.

### 4.11 `reopen_exception` — `[CHANGES DATA – reversible]`
> [CHANGES DATA – reversible] Reopen a closed exception at YOUR site, for example if it was closed by mistake. The previous resolution note is kept in history.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `exception_id` | `str`, pattern `^EXC-\d{4}$` | yes | |
| `reason` | `str[10..300]` | yes | |

Errors: `EXCEPTION_NOT_FOUND`, `ALREADY_OPEN`.

---

## 5. Error code catalogue

| Code | When | `retryable` | `how_to_fix` content |
|---|---|---|---|
| `INVALID_ARGUMENTS` | Schema violation: missing, wrong type/pattern/enum/length, or **unknown parameter** (including `site`) | false | Per-field `problems` with valid values/example; for `site`: "this session is fixed to <SITE>; omit it" |
| `SKU_NOT_FOUND` | SKU not at this site (identical response for nonexistent and other-site SKUs) | false | Use `search_products` with the description |
| `BIN_NOT_AT_SITE` | Bin prefix not used at this site | false | Valid prefixes listed |
| `SAME_BIN` | Destination equals current bin | false | Choose a different bin |
| `NO_CHANGE` | Counted quantity equals current | false | Nothing to adjust |
| `DATE_NOT_SCHEDULED` | No dock schedule for date | false | `available_dates`, `suggested_call` |
| `SLOT_ALREADY_BOOKED` | Slot taken | false | Free slots + `suggested_call` |
| `SLOT_NOT_BOOKED` | Cancel on a free slot | false | State is already free |
| `EXCEPTION_NOT_FOUND` | Not at this site / no such id | false | Use `list_exceptions` |
| `ALREADY_CLOSED` / `ALREADY_OPEN` | State no-op | false | Current state shown |
| `DUPLICATE_OPEN_EXCEPTION` | Same category+SKU already open | false | `existing_exception_id`; set `allow_duplicate` only if user confirms |
| `CONFIRMATION_INVALID` | Unknown, used, or other-site token | false | Run the `prepare_*` step again |
| `CONFIRMATION_EXPIRED` | Older than 5 min | false | Run `prepare_*` again |
| `CONFIRMATION_STALE` | Record changed since preview | false | Run `prepare_*` again; shows what changed |
| `INTERNAL_ERROR` | Unexpected fault | true | "Retry once; if it persists report to IT with `error_id`" (no trace) |

---

## 6. Assumptions to confirm with Ops (not in the data)

1. Exception categories (`DAMAGED`, `MISSING`, `WRONG_ITEM`, `OTHER`) are my proposal; Ops named only damaged and missing.
2. Adjustment reasons and cancellation reasons are my proposal, to give the month-end audit trail something to group on.
3. "Large change" threshold of 50% is a starting value.
4. Bin ownership by prefix (A/B/C/YARD) is inferred from E7; the real bin master list was not supplied.
5. The warehouse systems are stubbed over the two data files; state is in memory for the life of the process.
