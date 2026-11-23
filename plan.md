# Implementation Plan

Status: commit `02-plan`. Implements `spec.md` as written; any deviation found during the
build is recorded as a later commit that edits `spec.md` and says why.

## 1. Stack
* Python 3.11+ (built and tested on 3.12), MCP Python SDK (`mcp`, low-level `Server` with explicit `on_list_tools` / `on_call_tool`), `pydantic` v2 for parameter models, `pytest` + `pytest-asyncio` for the suite.
* **Low-level server, not auto-generated tools.** The framework would reject bad arguments *before* my code runs, with a generic message. The spec requires an actionable error object for schema violations too, so I publish the JSON schema (generated from the pydantic models) and validate in my own handler.
* Stdio transport; the host launches one server process per terminal with `KESTREL_SITE` set.

## 2. Module layout (`src/kestrel_ops/`)

| Module | Responsibility |
|---|---|
| `models.py` | One pydantic model per tool (`extra="forbid"`), enums/patterns as in spec §4; helper to export JSON schema |
| `errors.py` | `ToolError` exception + builders for every code in spec §5; pydantic `ValidationError` → `INVALID_ARGUMENTS` translation (valid values/example per field) |
| `store.py` | `Warehouse`: in-memory stub loaded from `data/` (stock, dock, exceptions, ledger, audit log). Pure data, **no site logic** |
| `search.py` | Tokenisation, exact-term matching, digit-exact rule, fuzzy fallback, `disambiguate_by` |
| `confirm.py` | Token issue / redeem with TTL, single-use, site binding, state fingerprint; injectable clock |
| `toolkit.py` | `Toolkit(warehouse, site)`: one async handler per tool. **Every access goes through `self.site`** — the only place site scoping lives |
| `server.py` | Builds the MCP `Server`: tool list (descriptions, schemas, annotations), dispatch, result envelope, startup site check |
| `__main__.py` | `python -m kestrel_ops` entry point, reads `KESTREL_SITE` |

## 3. Key design decisions for the build
1. **Site scoping at one choke point.** `Toolkit` exposes private helpers `_stock_for_site()`, `_slots_for_site()`, `_exceptions_for_site()`; handlers never touch `Warehouse` collections directly. Tests assert that for every SKU/site pair the right thing happens (same-site ok, cross-site refused).
2. **Not-found equals other-site.** `SKU_NOT_FOUND` text and shape are identical for a nonexistent SKU and another site's SKU (no existence oracle).
3. **Confirmation tokens** are random (`secrets.token_urlsafe`), stored server-side with `{action, args, site, state_fingerprint, issued_at}`; redeemed once. State fingerprint for an adjustment is current quantity; for a cancellation is the booked carrier.
4. **Errors are data, not exceptions leaking.** Handlers raise `ToolError`; `server.py` converts to the §3.4 shape. Any other exception becomes `INTERNAL_ERROR` with an opaque `error_id` and is logged to stderr only.
5. **Annotations from one table.** A single registry maps tool → (class tag, description, model, annotations) so description tags and `readOnlyHint`/`destructiveHint` cannot drift apart; a test checks the table against spec §3.2.
6. **Audit log.** Every state change appends `{ts, site, tool, args, result}` in memory (and to `KESTREL_AUDIT_LOG` if set).
7. **Data is stubbed, not mocked away:** the real CSV/JSONL files are loaded (handles CRLF), copied per `Warehouse` instance so tests are isolated.

## 4. Test strategy (pytest-asyncio, through the real MCP protocol)
Tests connect an in-memory MCP `Client` to the server, so they exercise the published schemas, annotations and JSON result envelope, not just Python functions.

| File | Covers |
|---|---|
| `test_tool_surface.py` | 11 tools exist; no `site` property anywhere; `additionalProperties:false`; enums present in schema and equal to the data's closed sets; annotations match tags |
| `test_search.py` | Every within-site near-duplicate pair returns both; unambiguous cases return one (`void fill`, `label roll`, `clear pallet wrap`, `SKU-8801`); out-of-stock; digits never fuzzy; typo → `needs_confirmation`; no match |
| `test_site_scoping.py` | Parametrised over all 3 sites × all 16 SKUs: same-site allowed, cross-site refused; search never leaks other sites' rows; `site` parameter rejected; tokens/exceptions/dock isolated; server refuses to start without a valid site |
| `test_confirmation.py` | Prepare changes nothing; confirm applies; single-use; expiry; stale; wrong site; unprepared token; no-change; ledger entry |
| `test_errors.py` | Shape for every code; invalid-argument problems list; error → `suggested_call` → success (self-correction) |
| `test_tools_invocation.py` | Happy-path for dock list/book/cancel, move, raise/list/close/reopen |

## 5. Demo and evidence
* `.mcp.json` registering the server with Claude Code (one entry per site).
* `demo/protocol_transcript.md`: scripted stdio session using the real MCP client — protocol evidence, **not** an LLM transcript.
* `demo/agent_demo.py`: drives the server with a real model (Anthropic API tool use) using Ops-style questions; the run output is the runtime-selection transcript. It needs an API key, which I do not have in the build environment, so the learner runs it and attaches the output (or uses Claude Code with `.mcp.json`).

## 6. Risks
* The installed MCP SDK (2.x) has a different low-level API from 1.x; pin the version in `pyproject.toml` and note it in the README.
* Fuzzy matching could reintroduce confident wrong answers; mitigated by the digit-exact rule and by labelling every fuzzy result `needs_confirmation`.
