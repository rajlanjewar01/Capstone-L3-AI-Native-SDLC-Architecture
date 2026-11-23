from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from mcp.client import Client

DATA = Path(__file__).resolve().parents[1] / "data"
SITES = ("LEEDS-01", "READING-02", "GLASGOW-03")

with open(DATA / "stock_snapshot.csv", newline="", encoding="utf-8") as _fh:
    STOCK = [dict(r, quantity=int(r["quantity"])) for r in csv.DictReader(_fh)]
with open(DATA / "dock_schedule.jsonl", encoding="utf-8") as _fh:
    DOCK = [json.loads(line) for line in _fh if line.strip()]

DATE = "2026-04-08"
ALL_SLOTS = ["06:00", "08:00", "10:00", "12:00", "14:00", "16:00"]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def call(client: Client, name: str, **args: Any) -> tuple[bool, dict[str, Any]]:
    """Call a tool through the MCP protocol; return (is_error, parsed JSON envelope)."""
    result = await client.call_tool(name, args)
    return bool(result.is_error), json.loads(result.content[0].text)


def error_of(env: dict[str, Any]) -> dict[str, Any]:
    assert env["ok"] is False, env
    return env["error"]


def skus_of(env: dict[str, Any]) -> list[str]:
    return [c["sku"] for c in env["data"]["candidates"]]


def stock_at(site: str) -> list[dict[str, Any]]:
    return [r for r in STOCK if r["site"] == site]
