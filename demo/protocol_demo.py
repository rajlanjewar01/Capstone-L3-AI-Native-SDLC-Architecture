"""Scripted protocol walk-through over a REAL stdio subprocess (python -m kestrel_ops).

This is NOT an LLM transcript. It shows the exact tool calls an agent should make for
Ops-style questions and what the toolkit returns. For the runtime agent transcript run
demo/agent_demo.py (needs an API key) or use Claude Code with .mcp.json.

Usage: python demo/protocol_demo.py > demo/protocol_transcript.md
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]

STEPS = {
    "LEEDS-01": [
        ("Ops: \"How many pallet wrap have we got?\"  (two products match -> agent must ask, not guess)",
         "search_products", {"query": "pallet wrap"}),
        ("Ops: \"The clear one.\"  (agent re-uses the SKU from the previous result)",
         "search_products", {"query": "clear pallet wrap"}),
        ("Ops: \"Any void fill?\"  (only one match at Leeds -> answer directly, no nagging)",
         "search_products", {"query": "void fill"}),
        ("Ops: \"Book the 8 o'clock dock for Acme.\"  (already taken -> actionable error)",
         "book_dock_slot", {"date": "2026-04-08", "slot": "08:00", "carrier": "Acme Ltd"}),
        ("Agent self-corrects using the error's suggested_call (first free slot)",
         "book_dock_slot", {"date": "2026-04-08", "slot": "06:00", "carrier": "Acme Ltd"}),
        ("Ops: \"The black wrap count is actually 150.\"  (irreversible -> preview only, nothing changes)",
         "prepare_stock_adjustment", {"sku": "SKU-8802", "counted_quantity": 150, "reason": "RECOUNT"}),
        ("Ops: \"What does Reading have of corner protector?\"  (cross-site: refused as not found)",
         "search_products", {"query": "corner protector"}),
        ("Agent tries SKU-8805 directly (a Reading SKU)",
         "move_stock", {"sku": "SKU-8805", "to_bin": "A-01-1"}),
        ("Agent tries to pass a site parameter",
         "list_dock_slots", {"date": "2026-04-08", "site": "READING-02"}),
        ("Deliberately invalid argument (slot 25:00, wrong date format)",
         "book_dock_slot", {"date": "08/04/2026", "slot": "25:00", "carrier": "Acme Ltd"}),
    ],
    "GLASGOW-03": [
        ("Ops (Glasgow): \"How many 600 shrink film?\"  (out of stock is an answer, not an error)",
         "search_products", {"query": "600mm shrink film"}),
    ],
}


def pretty(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except ValueError:
        return text


async def run_site(site: str, steps) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "kestrel_ops"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "KESTREL_SITE": site},
    )
    print(f"\n## Session bound to {site}\n")
    async with Client(params) as c:
        tools = (await c.list_tools()).tools
        print(f"Tools published ({len(tools)}): " + ", ".join(t.name for t in tools) + "\n")
        pending_token = None
        for caption, tool, args in steps:
            res = await c.call_tool(tool, args)
            body = pretty(res.content[0].text)
            if tool == "prepare_stock_adjustment":
                pending_token = json.loads(res.content[0].text)["data"]["confirmation_token"]
            print(f"### {caption}\n\n`{tool}` {json.dumps(args)}  ->  isError={res.is_error}\n\n```json\n{body}\n```\n")
        if pending_token:
            q = (await c.call_tool("search_products", {"query": "SKU-8802"})).content[0].text
            print("### Quantity is still 180 after the preview (nothing changed yet)\n")
            print(f"```json\n{pretty(q)}\n```\n")
            print("### User says yes -> confirm_action\n")
            r = await c.call_tool("confirm_action", {"confirmation_token": pending_token})
            print(f"`confirm_action` -> isError={r.is_error}\n\n```json\n{pretty(r.content[0].text)}\n```\n")
            print("### Reusing the same token is refused (single use)\n")
            r = await c.call_tool("confirm_action", {"confirmation_token": pending_token})
            print(f"`confirm_action` -> isError={r.is_error}\n\n```json\n{pretty(r.content[0].text)}\n```\n")


async def main() -> None:
    print("# Protocol transcript (scripted client, NOT an LLM)\n")
    print("Real stdio subprocess per site (`KESTREL_SITE` in the environment). Date of data: 2026-04-08.")
    for site, steps in STEPS.items():
        await run_site(site, steps)


if __name__ == "__main__":
    asyncio.run(main())
