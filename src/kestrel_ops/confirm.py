"""Single-use, site-bound, expiring confirmation tokens for irreversible actions."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable

from .errors import ToolError

TTL_SECONDS = 300


@dataclass
class PendingAction:
    token: str
    action: str  # "stock_adjustment" | "dock_cancellation"
    site: str
    args: dict[str, Any]
    fingerprint: dict[str, Any]  # state observed at preview time
    issued_at: float


class ConfirmationStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._pending: dict[str, PendingAction] = {}

    def issue(self, site: str, action: str, args: dict[str, Any], fingerprint: dict[str, Any]) -> PendingAction:
        # token_urlsafe(12) -> exactly 16 URL-safe characters.
        token = "CONF-" + secrets.token_urlsafe(12)
        pending = PendingAction(token, action, site, args, fingerprint, self._clock())
        self._pending[token] = pending
        return pending

    def redeem(self, site: str, token: str) -> PendingAction:
        """Consume a token. Another site's token is indistinguishable from an unknown one
        and is NOT consumed (so a stray call cannot burn someone else's preview)."""
        pending = self._pending.get(token)
        if pending is None or pending.site != site:
            raise ToolError(
                "CONFIRMATION_INVALID",
                "That confirmation token is unknown, already used, or was not issued to this site.",
                parameter="confirmation_token",
                received=token,
                how_to_fix="Run the prepare_* tool again to get a fresh preview and token, show it to the user, then call confirm_action.",
            )
        del self._pending[token]  # single use, even if it turns out to be expired
        if self._clock() - pending.issued_at > TTL_SECONDS:
            raise ToolError(
                "CONFIRMATION_EXPIRED",
                f"That confirmation token is older than {TTL_SECONDS // 60} minutes.",
                parameter="confirmation_token",
                received=token,
                how_to_fix="Run the prepare_* tool again for a fresh preview, get the user's yes again, then call confirm_action with the new token.",
            )
        return pending
