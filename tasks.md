# Tasks

Status: commit `03-tasks`. Ordered so each task is testable on its own. Checkboxes are
ticked in later commits as work lands.

## A. Foundation
- [x] A1 Project skeleton: `pyproject.toml` (pinned deps, pytest `asyncio_mode=auto`, `src` layout), `.gitignore`
- [x] A2 Copy `data/` files into the repo
- [x] A3 `store.py`: load CSV (CRLF-safe) and JSONL into an isolated in-memory `Warehouse`; ledger, exceptions, audit log

## B. Contract
- [x] B1 `models.py`: one pydantic model per tool exactly as spec §4 (enums, patterns, bounds, `extra="forbid"`, conditional SKU rule for `raise_exception`)
- [x] B2 `errors.py`: `ToolError`, builders for every code in spec §5, `ValidationError` → `INVALID_ARGUMENTS` with `problems[]` (valid values, example, special text for `site`)
- [x] B3 Tool registry table: name, tag, description text from spec, model, annotations

## C. Behaviour
- [x] C1 `search.py` + `search_products` (exact terms, digit-exact, fuzzy fallback labelled, `disambiguate_by`, resolution values)
- [x] C2 `list_dock_slots`, `book_dock_slot` (never overwrites; free-slot suggestions)
- [x] C3 `confirm.py` (TTL, single-use, site-bound, state fingerprint, injectable clock)
- [x] C4 `prepare_dock_cancellation`, `prepare_stock_adjustment`, `confirm_action` (+ ledger entry, audit)
- [x] C5 `move_stock` (bin prefix rules derived from data, warning on occupied bin)
- [x] C6 `raise_exception`, `list_exceptions`, `close_exception`, `reopen_exception` (duplicate guard)
- [x] C7 Site choke point in `toolkit.py`; identical not-found for other-site records

## D. Server
- [x] D1 `server.py`: list tools, dispatch, validate → handle → envelope, `INTERNAL_ERROR` fallback
- [x] D2 `__main__.py`: read `KESTREL_SITE`, fail closed if missing/invalid, stdio run

## E. Tests (pytest-asyncio over a real MCP client session)
- [x] E1 `test_tool_surface.py`
- [x] E2 `test_search.py`
- [x] E3 `test_site_scoping.py`
- [x] E4 `test_confirmation.py`
- [x] E5 `test_errors.py`
- [x] E6 `test_tools_invocation.py`
- [x] E7 Full run, save output to `docs/pytest_output.txt`

## F. Evidence and submission
- [x] F1 `.mcp.json` for Claude Code (three sites)
- [x] F2 `demo/protocol_transcript.md` (scripted stdio client; labelled as not an LLM)
- [~] F3 `demo/agent_demo.py` written and its tool-conversion step checked offline; the model-driven run needs an API key and has NOT been run yet (see README)
- [x] F4 `CHANGES_FROM_REQUEST.md` (table from spec §2, with final evidence)
- [x] F5 `README.md` (setup, registration, run tests)
- [~] F6 `REFLECTION.md` drafted; effort figures left for the submitter to fill in
- [x] F7 Challenge-your-own-work checklist answered against the built system
