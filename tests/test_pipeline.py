"""Pipeline behaviour with a scripted fake LLM: no API key, no cost, deterministic.

These cover the safety paths, where a real model would only fail occasionally.
"""
import itertools

import pytest

from agent import pipeline, tools
from agent.corpus import load_corpus
from agent.llm import LLMTurn, LLMUnavailable, ToolCall
from agent.pipeline import ACCOUNT_UNAVAILABLE, SAFE_FALLBACK, Agent
from agent.retrieval import HybridRetriever

_ids = itertools.count()


@pytest.fixture(scope="module")
def retriever():
    return HybridRetriever()


@pytest.fixture(autouse=True)
def fast_tools(monkeypatch):
    monkeypatch.setenv("TOOL_LATENCY_S", "0")
    monkeypatch.setenv("TOOL_FAIL_RATE", "0")


class ScriptedLLM:
    """Returns one scripted turn per call; each turn is a list of (tool_name, arguments)."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.seen = []  # the messages the agent sent on each call

    def __call__(self, messages, tools_spec):
        self.seen.append([dict(m) for m in messages])
        calls = [ToolCall(f"call_{next(_ids)}", name, args, "") for name, args in self.turns.pop(0)]
        return LLMTurn({"role": "assistant", "content": None}, calls, "fake", False, 100, 20, 0.0)


def submit(status, claims, intent="other", reason_codes=(), uncovered=None):
    return ("submit_answer", {"intent": intent, "status": status, "reason_codes": list(reason_codes),
                              "uncovered": uncovered,
                              "claims": [{"text": t, "citations": c} for t, c in claims]})


def test_mandatory_decline_is_stated_by_code_without_a_model_call(retriever):
    llm = ScriptedLLM()
    result = Agent(retriever, llm).answer("CUST-2003", "Please increase my limit")
    assert (result.status, result.path, result.reason_codes) == ("decline_with_reason", "rules", ["AA04"])
    assert llm.seen == [] and "POL-CRD-001#3" in result.customer_message


@pytest.mark.parametrize("question", ["I want my credit limit increased to 3 lakh.", "Can you raise my limit?"])
def test_mandatory_decline_survives_a_model_outage(retriever, question):
    def down(messages, tools_spec):
        raise LLMUnavailable("both models down")
    result = Agent(retriever, down).answer("CUST-2003", question)
    assert (result.status, result.path) == ("decline_with_reason", "rules")


def test_all_of_a_declines_citations_are_shown(retriever):
    result = Agent(retriever, ScriptedLLM()).answer("CUST-2006", "Can you increase my limit?")
    assert {"POL-CON-004", "POL-CRD-001"} <= set(result.cited_docs)
    assert "vulnerable" not in result.customer_message.lower()


def test_model_spotting_a_limit_request_cannot_soften_the_decline(retriever):
    llm = ScriptedLLM([submit("answer", [("You may be eligible.", ["POL-CRD-001#1"])], intent="limit_increase")])
    result = Agent(retriever, llm).answer("CUST-2003", "Can I have more credit?")
    assert (result.status, result.path) == ("decline_with_reason", "rules")
    assert "open dispute" in result.customer_message


def test_decline_without_a_rule_behind_it_is_rejected(retriever):
    fake = [submit("decline_with_reason", [("The markup is 3.5%.", ["POL-FEE-007"])], intent="fees")]
    result = Agent(retriever, ScriptedLLM(fake, fake)).answer("CUST-2007", "What is the markup?")
    assert result.status == "raise_request" and result.path == "safe_fallback"


def test_fabricated_citation_twice_goes_to_the_safe_fallback(retriever):
    fake = [submit("answer", [("The markup is 3.5%.", ["POL-XYZ-999"])], intent="fees")]
    result = Agent(retriever, ScriptedLLM(fake, fake)).answer("CUST-2007", "What is the markup?")
    assert result.path == "safe_fallback" and "POL-XYZ-999" not in result.customer_message


def test_invented_number_is_rejected(retriever):
    fake = [submit("answer", [("The foreign currency markup is 2.9%.", ["POL-FEE-007"])], intent="fees")]
    result = Agent(retriever, ScriptedLLM(fake, fake)).answer("CUST-2007", "What is the markup abroad?")
    assert result.path == "safe_fallback"
    assert any("[2.9]" in e for e in result.trace["errors"])


def test_excluded_document_cannot_be_cited_even_if_it_reaches_the_context(monkeypatch):
    monkeypatch.setattr(pipeline, "ALWAYS_IN_CONTEXT", ["POL-SVC-006", "POL-OPS-012"])
    leaky = HybridRetriever(load_corpus(include_excluded=True))
    fake = [submit("answer", [("Your increase is fine.", ["POL-OPS-012"])])]
    result = Agent(leaky, ScriptedLLM(fake, fake)).answer("CUST-2000", "What do the notes say?")
    assert result.path == "safe_fallback" and "POL-OPS-012" not in result.customer_message


@pytest.mark.parametrize("customer_id, question, text, citation, path", [
    # Signature's rate told to a Classic customer: a real source, the wrong card.
    ("CUST-2004", "What is the interest rate if I do not pay in full?",
     "Your revolve rate is 3.1% per month.", "POL-PRD-010#signature-card", "safe_fallback"),
    ("CUST-2004", "What is the interest rate if I do not pay in full?",
     "Your revolve rate is 3.4% per month.", "POL-PRD-010#classic-card", "llm"),
    # Same mistake inside a shared table.
    ("CUST-2009", "What is the annual fee waiver?",
     "Your annual fee is waived on spend of 4,00,000.", "POL-FEE-007", "safe_fallback"),
    ("CUST-2009", "What is the annual fee waiver?",
     "Your annual fee is waived on spend of 1,50,000.", "POL-FEE-007", "llm"),
    # Figures shared by both cards are not a misquote.
    ("CUST-2009", "What is the foreign markup?",
     "The foreign currency markup is 3.5%.", "POL-FEE-007", "llm"),
    # An explicit comparison names the other card.
    ("CUST-2009", "What is the annual fee waiver?",
     "The Signature card needs spend of 4,00,000.", "POL-FEE-007", "llm"),
])
def test_figures_must_belong_to_the_customers_card(retriever, customer_id, question, text, citation, path):
    fake = [submit("answer", [(text, [citation])], intent="fees")]
    result = Agent(retriever, ScriptedLLM(fake, fake)).answer(customer_id, question)
    assert result.path == path


def test_llm_outage_gives_a_clear_message_and_a_ticket(retriever):
    def down(messages, tools_spec):
        raise LLMUnavailable("both models down")
    result = Agent(retriever, down).answer("CUST-2007", "What is the markup abroad?")
    assert result.path == "safe_fallback" and SAFE_FALLBACK in result.customer_message
    assert [r["queue"] for r in result.service_requests] == ["GENERAL"]


def test_account_timeout_degrades_and_tells_the_model(retriever, monkeypatch):
    monkeypatch.setenv("TOOL_FAIL_RATE", "1")
    llm = ScriptedLLM([submit("answer", [("The foreign currency markup is 3.5%.", ["POL-FEE-007"])], intent="fees")])
    result = Agent(retriever, llm).answer("CUST-2007", "What is the markup abroad?")
    assert result.customer_message.startswith(ACCOUNT_UNAVAILABLE)
    assert 'status="unavailable"' in llm.seen[0][1]["content"]
    assert result.trace["spans"][0]["attempts"] == 2


def test_service_request_uses_session_customer_not_model_arguments(retriever, monkeypatch):
    raised_for = []
    real = tools.raise_service_request
    monkeypatch.setattr(tools, "raise_service_request", lambda cid, cat, s: raised_for.append(cid) or real(cid, cat, s))
    llm = ScriptedLLM([
        ("raise_service_request", {"category": "DISPUTES", "summary": "x", "customer_id": "CUST-2000"}),
        submit("raise_request", [("Disputes are routed to the DISPUTES queue.", ["POL-SVC-006"])], intent="dispute_or_fraud"),
    ])
    Agent(retriever, llm).answer("CUST-2002", "I don't recognise a transaction")
    assert raised_for == ["CUST-2002"]


def test_retried_answer_does_not_open_a_second_ticket(retriever):
    sr = ("raise_service_request", {"category": "DISPUTES", "summary": "x"})
    bad = submit("raise_request", [("Routed.", ["POL-NOPE"])])
    good = submit("raise_request", [("Disputes are routed to the DISPUTES queue.", ["POL-SVC-006"])])
    result = Agent(retriever, ScriptedLLM([sr, bad], [sr, good])).answer("CUST-2002", "Unknown transaction")
    assert len(result.service_requests) == 1


def test_internal_score_never_reaches_the_model(retriever):
    llm = ScriptedLLM([submit("refuse", [], uncovered="your internal score")])
    Agent(retriever, llm).answer("CUST-2000", "What is my behavioural score?")
    assert "behavioural_score" not in llm.seen[0][1]["content"] and "640" not in llm.seen[0][1]["content"]


def test_uncovered_topic_is_always_routed_to_a_human(retriever):
    llm = ScriptedLLM([submit("refuse", [], uncovered="travel insurance")])
    result = Agent(retriever, llm).answer("CUST-2009", "Can I add travel insurance?")
    assert result.status == "refuse" and [r["queue"] for r in result.service_requests] == ["GENERAL"]


def test_vulnerable_flag_is_not_disclosed(retriever):
    leak = submit("refuse", [("Your account is flagged as vulnerable, so sales are suppressed.",
                              ["POL-CON-004", "account.vulnerable_flag"])])
    result = Agent(retriever, ScriptedLLM([leak], [leak])).answer("CUST-2006", "Any loans for me?")
    assert result.path == "safe_fallback" and "vulnerable" not in result.customer_message.lower()
