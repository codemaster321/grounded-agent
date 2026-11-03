"""The two supplied tools, implemented to the fixed contract in data/tools.md.

These simulate upstream systems. They do not retry or recover; that is the
caller's job (see agent/upstream.py). Knobs are env vars so the contract's
function signatures stay exactly as specified:
  TOOL_FAIL_RATE  probability of UpstreamTimeout (default 1/12, per the contract)
  TOOL_LATENCY_S  simulated latency in seconds (default 0.4)
  TOOL_SEED       seed for the failure RNG, for reproducible eval runs
"""
import copy
import json
import os
import random
import time
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class CustomerNotFound(Exception):
    pass


class UpstreamTimeout(Exception):
    pass


class InvalidCategory(Exception):
    pass


# Queues named in POL-SVC-006. The policy states SLAs in hours or working days;
# the contract returns sla_hours, so working days are converted at 24h/day.
# That conversion is our assumption, so customer-facing text quotes the policy, not this number.
QUEUES = {
    "CARDS_URGENT": 4,
    "DISPUTES": 2 * 24,
    "SELFSERVE": 1 * 24,
    "CREDIT_OPS": 3 * 24,
    "PAYMENTS": 2 * 24,
    "COMPLAINTS": 5 * 24,
    "GENERAL": 1 * 24,
}

_accounts = json.loads((DATA_DIR / "accounts.json").read_text(encoding="utf-8"))
_seed = os.environ.get("TOOL_SEED")
_rng = random.Random(int(_seed) if _seed is not None else None)


def _simulate_upstream() -> None:
    time.sleep(float(os.environ.get("TOOL_LATENCY_S", 0.4)))
    if _rng.random() < float(os.environ.get("TOOL_FAIL_RATE", 1 / 12)):
        raise UpstreamTimeout("account service did not respond")


def get_account_state(customer_id: str) -> dict:
    _simulate_upstream()
    if customer_id not in _accounts:
        raise CustomerNotFound(customer_id)
    return copy.deepcopy(_accounts[customer_id])


def customer_exists(customer_id: str) -> bool:
    """For the web login only; not part of the supplied tool contract."""
    return customer_id in _accounts


def raise_service_request(customer_id: str, category: str, summary: str) -> dict:
    if customer_id not in _accounts:
        raise CustomerNotFound(customer_id)
    if category not in QUEUES:
        raise InvalidCategory(category)
    return {
        "request_id": f"SR-{uuid.uuid4().hex[:8].upper()}",
        "queue": category,
        "sla_hours": QUEUES[category],
    }
