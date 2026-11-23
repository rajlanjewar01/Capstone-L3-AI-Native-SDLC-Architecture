# Kestrel Warehouse Ops MCP Toolkit

An MCP server that lets an agent answer stock and dock questions and raise exceptions for
warehouse staff at **one** site (LEEDS-01, READING-02 or GLASGOW-03). Built for L2 Agentic SDLC,
Case 04. Design reasoning: `spec.md`. What changed from Ops' wish-list: `CHANGES_FROM_REQUEST.md`.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"        # mcp 2.x, pydantic, pytest, pytest-asyncio
python -m pytest                 # 291 tests
```
Python 3.11+ (developed on 3.12). The MCP SDK is the 2.x API (`mcp>=2.3,<3`), pinned in `pyproject.toml`.

## Run / register
The site comes from the environment, never from a tool call, and the server refuses to start without it:
```bash
KESTREL_SITE=LEEDS-01 python -m kestrel_ops
```
**Claude Code:** the repo's `.mcp.json` registers a Leeds-bound server. Open the repo in Claude Code and
approve the project server, or:
```bash
claude mcp add kestrel-warehouse-leeds --env KESTREL_SITE=LEEDS-01 -- python -m kestrel_ops
```
(`docs/mcp-configs/` has Reading and Glasgow variants. Register **one** site per session: registering all
three in one host would give that agent three identities and defeat the scoping demo.)

## Tools (11)
| Class | Tools |
|---|---|
| Read-only | `search_products`, `list_dock_slots`, `list_exceptions` |
| Preview (changes nothing, issues a token) | `prepare_stock_adjustment`, `prepare_dock_cancellation` |
| Reversible writes | `book_dock_slot`, `move_stock`, `raise_exception`, `close_exception`, `reopen_exception` |
| Irreversible (needs a preview token) | `confirm_action` |

## Evidence
| Item | Where |
|---|---|
| Four commits in order | `git log --stat` (`01-spec` spec.md only -> `02-plan` -> `03-tasks` -> `04-implement`) |
| Passing pytest-asyncio output | `docs/pytest_output.txt` (re-run with `python -m pytest -v`) |
| Protocol transcript (scripted client over real stdio; **not an LLM**) | `demo/protocol_transcript.md` (`python demo/protocol_demo.py`) |
| Agent transcript (model chooses tools at runtime) | `demo/agent_demo.py` -> `demo/agent_transcript.md` (**you must run this**; see below) |
| Changes list | `CHANGES_FROM_REQUEST.md` |
| Reflection + effort statement | `REFLECTION.md` |

### Producing the runtime agent transcript (required deliverable, not yet done)
This repo was built without an API key or an agent host, so the **runtime transcript has not been captured**. Either:
1. `pip install -e ".[demo]" && ANTHROPIC_API_KEY=... python demo/agent_demo.py > demo/agent_transcript.md`
   (seven scenarios: ambiguous lookup that must trigger a clarifying question, unambiguous lookup,
   booked slot, ledger write with preview/confirm, cross-site refusal, invalid argument, out of stock), or
2. open the repo in Claude Code and ask the same questions by hand; save the session.

Read the transcript before submitting. If the model misbehaves (for example confirms without asking), keep that
in and say so in `REFLECTION.md`: the descriptions in `server.py` are the thing to tune.

## Layout
```
src/kestrel_ops/  models.py (schemas)  errors.py (error shape)  search.py  confirm.py (tokens)
                  store.py (stubbed data)  toolkit.py (all behaviour + site choke point)  server.py (MCP wiring)
tests/            surface, search, site scoping, confirmation, errors, invocation (+ real stdio run)
data/             the two provided files, unchanged
```

## Limitations
* Warehouse systems are **stubs over the two data files**; state is in memory per process and resets on restart.
  Two site-bound processes therefore do not share state (the tests share one `Warehouse` to check isolation).
* The data covers a single date (2026-04-08); dock tools never default to "today".
* Bin validation is a format-and-prefix check (no master bin list was provided).
