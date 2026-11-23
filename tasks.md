# Tasks

Status: commit `03-tasks`. Ordered so each task is testable on its own. Checkboxes are
ticked in later commits as work lands.

## A. Foundation
- [ ] A1 Project skeleton: `pyproject.toml` (pinned deps, pytest `asyncio_mode=auto`, `src` layout), `.gitignore`
- [ ] A2 Copy `data/` files into the repo
- [ ] A3 `store.py`: load CSV (CRLF-safe) and JSONL into an isolated in-memory `Warehouse`; ledger, exceptions, audit log

## B. Contract
- [ ] B1 `models.py`: one pydantic model per tool exactly as spec §4 (enums, patterns, bounds, `extra="forbid"`, conditional SKU rule for `raise_exception`)
- [ ] B2 `errors.py`: `ToolError`, builders for every code in spec §5, `ValidationError` → `INVALID_ARGUMENTS` with `problems[]` (valid values, example, special text for `site`)
- [ ] B3 Tool registry table: name, tag, description text from spec, model, annotations

## C. Behaviour
- [ ] C1 `search.py` + `search_products` (exact terms, digit-exact, fuzzy fallback labelled, `disambiguate_by`, resolution values)
- [ ] C2 `list_dock_slots`, `book_dock_slot` (never overwrites; free-slot suggestions)
- [ ] C3 `confirm.py` (TTL, single-use, site-bound, state fingerprint, injectable clock)
- [ ] C4 `prepare_dock_cancellation`, `prepare_stock_adjustment`, `confirm_action` (+ ledger entry, audit)
- [ ] C5 `move_stock` (bin prefix rules derived from data, warning on occupied bin)
- [ ] C6 `raise_exception`, `list_exceptions`, `close_exception`, `reopen_exception` (duplicate guard)
- [ ] C7 Site choke point in `toolkit.py`; identical not-found for other-site records

## D. Server
- [ ] D1 `server.py`: list tools, dispatch, validate → handle → envelope, `INTERNAL_ERROR` fallback
- [ ] D2 `__main__.py`: read `KESTREL_SITE`, fail closed if missing/invalid, stdio run

## E. Tests (pytest-asyncio over a real MCP client session)
- [ ] E1 `test_tool_surface.py`
- [ ] E2 `test_search.py`
- [ ] E3 `test_site_scoping.py`
- [ ] E4 `test_confirmation.py`
- [ ] E5 `test_errors.py`
- [ ] E6 `test_tools_invocation.py`
- [ ] E7 Full run, save output to `docs/pytest_output.txt`

## F. Evidence and submission
- [ ] F1 `.mcp.json` for Claude Code (three sites)
- [ ] F2 `demo/protocol_transcript.md` (scripted stdio client; labelled as not an LLM)
- [ ] F3 `demo/agent_demo.py` and Ops-phrased question list incl. an ambiguous lookup that must trigger a clarifying question
- [ ] F4 `CHANGES_FROM_REQUEST.md` (table from spec §2, with final evidence)
- [ ] F5 `README.md` (setup, registration, run tests)
- [ ] F6 `REFLECTION.md` and declared-effort statement
- [ ] F7 Challenge-your-own-work checklist answered against the built system
