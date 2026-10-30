import pytest

from agent import tools, upstream


@pytest.fixture(autouse=True)
def fast_tools(monkeypatch):
    monkeypatch.setenv("TOOL_LATENCY_S", "0")
    monkeypatch.setenv("TOOL_FAIL_RATE", "0")


def test_returns_a_copy_not_the_shared_record():
    tools.get_account_state("CUST-2000")["current_limit"] = 1
    assert tools.get_account_state("CUST-2000")["current_limit"] == 120000


def test_unknown_customer_is_not_retried(monkeypatch):
    assert upstream.fetch_account("CUST-9999") == upstream.AccountLookup("not_found", None, 1)


def test_one_timeout_then_success_recovers(monkeypatch):
    calls = iter([tools.UpstreamTimeout(), {"customer_id": "CUST-2000"}])

    def flaky(customer_id):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(tools, "get_account_state", flaky)
    lookup = upstream.fetch_account("CUST-2000")
    assert (lookup.status, lookup.attempts) == ("ok", 2)


def test_persistent_timeout_degrades_instead_of_raising(monkeypatch):
    monkeypatch.setenv("TOOL_FAIL_RATE", "1")
    assert upstream.fetch_account("CUST-2000") == upstream.AccountLookup("unavailable", None, 2)


def test_invalid_category_is_rejected_not_guessed():
    with pytest.raises(tools.InvalidCategory):
        tools.raise_service_request("CUST-2002", "FRAUD", "unknown merchant")


def test_valid_request_returns_contract_shape():
    sr = tools.raise_service_request("CUST-2002", "DISPUTES", "unknown merchant")
    assert sr["request_id"].startswith("SR-") and sr["queue"] == "DISPUTES" and sr["sla_hours"] == 48
