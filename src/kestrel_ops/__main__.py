"""`python -m kestrel_ops` — stdio server bound to the site in KESTREL_SITE."""
from __future__ import annotations

import os

import anyio
from mcp.server.stdio import stdio_server

from .server import build_server, resolve_site


async def _run() -> None:
    site = resolve_site(os.environ.get("KESTREL_SITE"))  # exits non-zero if missing/invalid
    server = build_server(site)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    main()
