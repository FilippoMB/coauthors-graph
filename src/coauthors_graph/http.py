"""HTTP helpers shared by metadata-source clients."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
import random
import time

import requests


TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


class MetadataSession(requests.Session):
    """Share one source budget across pages, retries, and request spacing."""

    def __init__(self, *, budget: float = 300, minimum_interval: float = 0):
        super().__init__()
        self.deadline = time.monotonic() + budget
        self.minimum_interval = minimum_interval
        self.last_request = float("-inf")

    def _wait(self, seconds: float) -> None:
        if time.monotonic() + seconds >= self.deadline:
            raise requests.Timeout("Metadata source time budget exhausted")
        if seconds > 0:
            time.sleep(seconds)

    def get(self, url, **kwargs):
        timeout = kwargs.pop("timeout", (5, 30))
        for attempt in range(4):
            self._wait(
                max(0, self.minimum_interval - (time.monotonic() - self.last_request))
            )
            remaining = self.deadline - time.monotonic()
            self.last_request = time.monotonic()
            try:
                response = super().get(
                    url,
                    timeout=tuple(min(value, remaining) for value in timeout),
                    **kwargs,
                )
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 3:
                    raise
                self._wait(2**attempt + random.uniform(0, 1))
                continue
            if response.status_code not in TRANSIENT_STATUSES or attempt == 3:
                return response
            delay = retry_after_seconds(response.headers.get("Retry-After"))
            response.close()
            # Never retry earlier than the server permits. Long waits use saved data.
            if delay is not None and delay > 60:
                raise requests.Timeout(
                    "Server requested a retry beyond this refresh budget"
                )
            self._wait(max(delay or 0, 2**attempt + random.uniform(0, 1)))
        raise AssertionError("Unreachable retry state")


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return None


def retrying_session(*, minimum_interval: float = 0) -> MetadataSession:
    return MetadataSession(minimum_interval=minimum_interval)
