"""Minimal MS Graph calendar client for one-way event polling.

Read-only: resolves the target calendar by display name and delta-syncs its
events. Never writes back to Outlook. Transport is injectable (httpx.Client)
so tests can drive it with a MockTransport.
"""
from __future__ import annotations

import httpx

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# MS Graph caps event lists; a generous page size keeps round-trips low.
_PAGE_SIZE = 100


class GraphError(Exception):
    """Base class for Graph client failures."""


class GraphRateLimited(GraphError):
    """429 from Graph. `retry_after` is the server's Retry-After in seconds."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class DeltaExpired(GraphError):
    """410 Gone — the stored delta link is stale; caller must full re-sync."""


class GraphClient:
    def __init__(
        self,
        access_token: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = GRAPH_BASE,
    ) -> None:
        self._token = access_token
        self._base = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=30.0)

    # -- low-level ---------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self._token}",
            # Ask Graph to return start/end in UTC so we can store naive-UTC.
            "Prefer": 'outlook.timezone="UTC"',
        }
        r = self._client.get(url, headers=headers, params=params)
        if r.status_code == 429:
            raise GraphRateLimited(int(r.headers.get("Retry-After", "60")))
        if r.status_code == 410:
            raise DeltaExpired()
        r.raise_for_status()
        return r.json()

    # -- calendar resolution ----------------------------------------------

    def resolve_calendar_id(self, display_name: str) -> str | None:
        """Return the id of the calendar whose displayName matches, else None."""
        url = f"{self._base}/me/calendars"
        params: dict | None = {"$select": "id,name"}
        while url:
            data = self._get(url, params=params)
            for cal in data.get("value", []):
                if cal.get("name") == display_name:
                    return cal.get("id")
            url = data.get("@odata.nextLink") or ""
            params = None  # nextLink is fully-qualified
        return None

    # -- delta sync --------------------------------------------------------

    def delta_events(
        self, calendar_id: str, delta_link: str | None = None
    ) -> tuple[list[dict], str]:
        """Fetch changed events since `delta_link` (or a full sync if None).

        Returns (events, next_delta_link). Follows @odata.nextLink pages and
        returns the final @odata.deltaLink to persist for the next run.
        Raises DeltaExpired on a 410 (stale link).
        """
        if delta_link:
            url = delta_link
            params: dict | None = None
        else:
            url = f"{self._base}/me/calendars/{calendar_id}/events/delta"
            params = {"$top": _PAGE_SIZE}

        events: list[dict] = []
        while True:
            data = self._get(url, params=params)
            params = None  # only the first request carries query params
            events.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")
            if next_link:
                url = next_link
                continue
            return events, data.get("@odata.deltaLink", "")
