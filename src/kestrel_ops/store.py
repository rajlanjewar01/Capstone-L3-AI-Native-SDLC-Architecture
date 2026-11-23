"""In-memory stub of the warehouse systems, loaded from the provided data files.

This module is pure data: it knows nothing about which site a caller belongs to.
All site scoping lives in ``toolkit.py`` (the single choke point).
"""
from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SITES = ("LEEDS-01", "READING-02", "GLASGOW-03")

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass
class StockItem:
    sku: str
    description: str
    site: str
    bin: str
    quantity: int
    unit: str


@dataclass
class DockSlot:
    site: str
    date: str
    slot: str
    status: str  # "available" | "booked"
    carrier: str | None


@dataclass
class ExceptionTicket:
    exception_id: str
    site: str
    category: str
    sku: str | None
    summary: str
    status: str = "open"  # "open" | "closed"
    resolution_note: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


class Warehouse:
    """Isolated, mutable copy of the stub data. One instance per test/process."""

    def __init__(
        self,
        data_dir: Path | str | None = None,
        audit_path: Path | str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        data = Path(data_dir or os.environ.get("KESTREL_DATA_DIR") or DEFAULT_DATA_DIR)
        self.clock = clock
        self.stock: dict[str, StockItem] = {}
        self.dock: list[DockSlot] = []
        self.exceptions: list[ExceptionTicket] = []
        self.ledger: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self._audit_path = Path(audit_path or os.environ["KESTREL_AUDIT_LOG"]) if (
            audit_path or os.environ.get("KESTREL_AUDIT_LOG")
        ) else None
        self._exception_seq = 0
        self._ledger_seq = 0
        # Imported lazily to avoid a circular import at module load.
        from .confirm import ConfirmationStore

        self.confirmations = ConfirmationStore(clock)
        self._load(data)

    # -- loading -----------------------------------------------------------
    def _load(self, data: Path) -> None:
        # newline="" so the CRLF line endings in the CSV do not leak into values.
        with open(data / "stock_snapshot.csv", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                item = StockItem(
                    sku=row["sku"].strip(),
                    description=row["description"].strip(),
                    site=row["site"].strip(),
                    bin=row["bin"].strip(),
                    quantity=int(row["quantity"]),
                    unit=row["unit"].strip(),
                )
                self.stock[item.sku] = item
        with open(data / "dock_schedule.jsonl", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    self.dock.append(
                        DockSlot(r["site"], r["date"], r["slot"], r["status"], r["carrier"])
                    )

    # -- ids and logs ------------------------------------------------------
    def next_exception_id(self) -> str:
        self._exception_seq += 1
        return f"EXC-{self._exception_seq:04d}"

    def next_ledger_id(self) -> str:
        self._ledger_seq += 1
        return f"LED-{self._ledger_seq:04d}"

    def record_audit(self, site: str, tool: str, args: dict[str, Any], result: dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "site": site,
            "tool": tool,
            "args": args,
            "result": result,
        }
        self.audit.append(entry)
        if self._audit_path:
            with open(self._audit_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
