import json
from datetime import date

import pytest

from agent.rules import limit_increase_findings
from agent.tools import DATA_DIR

ACCOUNTS = json.loads((DATA_DIR / "accounts.json").read_text(encoding="utf-8"))
AS_OF = date(2026, 10, 30)


def rules_for(customer_id, today=AS_OF):
    return {(f.rule, f.outcome, f.reason_code) for f in limit_increase_findings(ACCOUNTS[customer_id], today)}


@pytest.mark.parametrize("customer_id, expected", [
    ("CUST-2003", {("open_dispute", "decline", "AA04")}),             # EV-002
    ("CUST-2006", {("vulnerable_customer", "decline", None)}),        # EV-003
    ("CUST-2001", {("recent_increase", "decline", "AA05")}),          # EV-004
    ("CUST-2005", {("possible_thin_file", "refer", "AA03")}),         # EV-005
    ("CUST-2008", {("rekyc_overdue", "decline", "AA06")}),            # EV-006
    ("CUST-2000", set()),
])
def test_seed_customers(customer_id, expected):
    assert rules_for(customer_id) == expected


def test_contradiction_only_matters_between_3_and_6_months():
    # CUST-2001 last increase 2026-06-19. 6-month bar lifts on 2026-12-19.
    assert ("recent_increase", "decline", "AA05") in rules_for("CUST-2001", date(2026, 12, 18))
    assert rules_for("CUST-2001", date(2026, 12, 20)) == set()
