"""Drive the toolkit with a real model so tool selection happens at runtime.

Needs:  pip install -e ".[demo]"   and   ANTHROPIC_API_KEY in the environment.
Run:    python demo/agent_demo.py > demo/agent_transcript.md

Each scenario launches its own `python -m kestrel_ops` stdio server (own site, fresh data), then
plays scripted Ops-style user turns to the model. The model chooses which tools to call; this
script only relays tool calls to the MCP server and prints everything.

Expected behaviour is listed per scenario so the transcript can be checked by eye:
see EXPECT below. (An honest transcript is one where the model misbehaves too: keep it.)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
SYSTEM = (
    "You are the forklift-terminal assistant for Kestrel warehouse staff. Be brief: they are wearing "
    "gloves. Use the tools; never invent stock figures. Today's dock schedule data is for 2026-04-08."
)

# (site, expectation, user turns)
SCENARIOS: list[tuple[str, str, list[str]]] = [
    ("LEEDS-01", "Search -> several matches -> ASK which one (no guess) -> answer 180 each for black.",
     ["How many pallet wrap have we got?", "The black one"]),
    ("LEEDS-01", "One match -> answer directly (420 box), no clarifying question.",
     ["Any void fill in stock?"]),
    ("LEEDS-01", "Booking refused (taken) -> offers free slots rather than overwriting.",
     ["Book the 08:00 dock on 2026-04-08 for Acme Ltd"]),
    ("LEEDS-01", "Preview first, ask for yes, only then confirm_action; quantity ends at 150.",
     ["The black pallet wrap count is wrong, I counted 150", "Yes, go ahead"]),
    ("LEEDS-01", "Cross-site refused: says it can only see Leeds; does not quote Reading numbers.",
     ["What's the stock of 75mm corner protector at Reading?"]),
    ("LEEDS-01", "Invalid argument -> self-corrects or asks; never claims success.",
     ["Book the 25:00 dock on 2026-04-08 for Acme Ltd"]),
    ("GLASGOW-03", "Ambiguous shrink film -> asks; then reports 0 rolls = out of stock (not an error).",
     ["How many shrink film?", "The 600"]),
]


def anthropic_tools(mcp_tools) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in mcp_tools]


async def run_turn(ai: AsyncAnthropic, mcp: Client, tools, messages: list[dict[str, Any]]) -> None:
    while True:
        resp = await ai.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM + "\n\n" + (mcp.instructions or ""),
            tools=tools, messages=messages,
        )
        messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
        for b in resp.content:
            if b.type == "text" and b.text.strip():
                print(f"**Agent:** {b.text.strip()}\n")
        if resp.stop_reason != "tool_use":
            return
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            r = await mcp.call_tool(b.name, b.input)
            text = r.content[0].text
            print(f"> **tool call** `{b.name}` {json.dumps(b.input)}  \n> isError={r.is_error}\n")
            print("```json\n" + json.dumps(json.loads(text), indent=1, ensure_ascii=False)[:1800] + "\n```\n")
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": text, "is_error": bool(r.is_error)})
        messages.append({"role": "user", "content": results})


async def main() -> None:
    ai = AsyncAnthropic()
    print(f"# Agent transcript (model: {MODEL})\n")
    for n, (site, expect, turns) in enumerate(SCENARIOS, 1):
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "kestrel_ops"],
            env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "KESTREL_SITE": site},
        )
        print(f"## Scenario {n} - {site}\n\n*Expected:* {expect}\n")
        async with Client(params) as mcp:
            tools = anthropic_tools((await mcp.list_tools()).tools)
            messages: list[dict[str, Any]] = []
            for turn in turns:
                print(f"**Ops:** {turn}\n")
                messages.append({"role": "user", "content": turn})
                await run_turn(ai, mcp, tools, messages)


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY to run the agent demo.")
    asyncio.run(main())
