# Reflection

> **DRAFT: edit this so it is in your own words and matches what you actually did and understand.**
> You will be asked questions about this submission. Facts below were checked against the repo;
> the effort figures and the agent-transcript observations are yours to fill in.

## Declared effort
* **AI assistance:** the spec, plan, tasks, code, tests and documents in this repository were produced in one
  working session with Claude (Anthropic) acting as the implementer, from the case brief and data files.
* **My own contribution:** ______ (e.g. reviewed spec.md against the data, ran the agent demo, edited this file).
* **Time I spent:** ______ hours. **Agent host used for the runtime transcript:** ______ (Claude Code / other).
* **Not done by the build session:** the model-driven runtime transcript (no API key or agent host was available).

## What I would tell Ops
Five tools became eleven because three of them were doing several jobs with different risk. The lookup could not
keep its promise: 8801 and 8802 differ only by "clear"/"black", and six pairs of near-identical items sit inside
a single site, so a name is not a key. The toolkit therefore returns every plausible match and says whether the
agent may answer or must ask. Corrections cannot be undone, so they take a preview and a token; moves, bookings and
tickets can be undone, so they stay one fast call.

## The decisions I would defend
1. **No `site` parameter at all** (not "a parameter I check"). Ops' Leeds/Reading incident came from a trusted
   input; the fix is that there is no input to trust. Cross-site records look exactly like nonexistent ones, so the
   toolkit is not an oracle either.
2. **Token, not a `confirm=true` flag.** A flag can be set in the first call with no human involved.
3. **Absolute counted quantity, not a delta.** Agents retry; a delta applied twice corrupts the month-end figure.
4. **Per-tool read/write distinction in both the text and the annotations**, generated from one table so they cannot drift.
5. **Own validation, published schema.** The framework would reject bad arguments before my code with a generic
   message; validating myself lets every failure carry `valid_values`, an example and, where possible, a call to replay.

## What the tests caught or proved
* The suite found one weak error message of mine (`ALREADY_OPEN` said only "Nothing to do.").
* **Mutation check** (I deliberately broke the code and re-ran the suite): ignoring the site in `_site_item` -> 66 failures;
  search across all sites -> 38 failures; token not single-use -> 1 failure; token not site-bound -> 1 failure;
  numbers allowed to prefix-match -> initially **survived**, which exposed a missing test ("50mm" must not match "500mm");
  I added it and the mutation is now caught. One mutation (fuzzy matching digits) is equivalent code because the
  fuzzy pass already excludes digit tokens.
* 291 tests pass; the run is in `docs/pytest_output.txt`.

## Checklist: "challenge your own work"
* *Read the stock file before designing lookup?* Yes; the design table E1-E11 in `spec.md` records what it showed.
* *Does lookup ever return one item when more than one is plausible?* Not on exact terms (all matches returned). A
  misspelling returns the closest items but labelled `needs_confirmation`, even for a single hit.
* *Does it demand disambiguation where there is one match?* No: `void fill` at Leeds, `label roll`, and every item's
  full description return `single_match` (`test_a_full_description_always_finds_exactly_that_item`, all 16 SKUs).
* *Irreversible or ledger-feeding operations?* Stock adjustment (month-end) and dock cancellation. Both are two-step.
* *Any tool that is really two or three?* `check_dock` (list/book/cancel) and `stock_change` (correct/move).
* *Closed value sets in the schema?* Slots, reasons, categories, statuses are enums; ids are patterns (`test_tool_surface.py`).
* *Is site scoping enforceable?* It is in one choke point inside the toolkit; `site` is rejected on all 11 tools.
* *Can the agent fix a failed call from the error alone?* `suggested_call` replays successfully for slot conflict,
  unscheduled date and stale confirmation (`test_errors.py`).
* *Operation whose reverse Ops did not ask for?* Close ticket -> I added `reopen_exception`. Stock correction has no
  reverse by design (append-only ledger; correct with another adjustment).

## Weaknesses I know about
* **Agent behaviour is untested here.** Tool descriptions are what steer a model; whether it really asks before
  confirming must be checked in the transcript (`demo/agent_demo.py`).
* **A token is not proof a human said yes.** It forces a preview round-trip, but a careless agent could still call
  `confirm_action` straight after. A host with elicitation/approval UI would be a stronger guard.
* **Assumed lists:** exception categories, reasons, the 50% warning threshold (spec section 6).
* **State is in memory** and per process; a real backend would need transactions for the stale-preview check.
* **Search is token matching**, tuned to 16 SKUs; a real catalogue would need a proper index and more careful ranking.
