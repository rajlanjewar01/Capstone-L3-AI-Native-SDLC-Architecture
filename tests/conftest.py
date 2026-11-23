from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp.client import Client

sys.path.insert(0, str(Path(__file__).parent))

from helpers import FakeClock  # noqa: E402
from kestrel_ops.server import build_server  # noqa: E402
from kestrel_ops.store import Warehouse  # noqa: E402


class SiteClient:
    """An MCP client for one site. Each call goes through a real in-memory MCP session
    (initialise -> request -> JSON-RPC response), so published schemas and result envelopes
    are exercised exactly as a host would see them. Sessions are opened per call because
    anyio cancel scopes cannot span pytest-asyncio fixture/test tasks."""

    def __init__(self, site: str, warehouse: Warehouse) -> None:
        self.site = site
        self._wh = warehouse

    async def call_tool(self, name, arguments=None):
        async with Client(build_server(self.site, self._wh)) as c:
            return await c.call_tool(name, arguments or {})

    async def list_tools(self):
        async with Client(build_server(self.site, self._wh)) as c:
            return await c.list_tools()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def warehouse(clock: FakeClock) -> Warehouse:
    """A fresh, isolated copy of the stub data for every test."""
    return Warehouse(clock=clock)


@pytest.fixture
def leeds(warehouse):
    return SiteClient("LEEDS-01", warehouse)


@pytest.fixture
def reading(warehouse):
    return SiteClient("READING-02", warehouse)


@pytest.fixture
def glasgow(warehouse):
    return SiteClient("GLASGOW-03", warehouse)


@pytest.fixture
def make_client(warehouse):
    """Factory: a client bound to any site, sharing the test's warehouse."""
    return lambda site: SiteClient(site, warehouse)
