"""Calling the account tool safely.

One retry with jittered backoff: at a 1-in-12 failure rate, two failures in a row
is ~1 in 144. More retries would add latency for the customer while the upstream
is struggling, so after the retry we stop and degrade (status="unavailable").
CustomerNotFound is not retried: it will not succeed on a second try.
"""
import random
import time
from dataclasses import dataclass
from typing import Literal

from agent import tools


@dataclass
class AccountLookup:
    status: Literal["ok", "unavailable", "not_found"]
    account: dict | None
    attempts: int


def fetch_account(customer_id: str, max_attempts: int = 2) -> AccountLookup:
    for attempt in range(1, max_attempts + 1):
        try:
            return AccountLookup("ok", tools.get_account_state(customer_id), attempt)
        except tools.CustomerNotFound:
            return AccountLookup("not_found", None, attempt)
        except tools.UpstreamTimeout:
            if attempt < max_attempts:
                time.sleep(random.uniform(0.1, 0.3))
    return AccountLookup("unavailable", None, max_attempts)
