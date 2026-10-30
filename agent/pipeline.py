"""The agent: one customer question in, one validated response out.

Flow (see docs/ARCHITECTURE.md):
  account (code, with retry) -> hybrid retrieval -> hard rules (code)
  -> LLM with tools -> validator (one retry) -> message rendered by code from cited claims.
Every exit path, including failures, produces a customer message and one trace line.
"""
import json
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from agent import tools
from agent.config import as_of, models
from agent.corpus import Chunk
from agent.llm import LLMUnavailable, call_llm
from agent.prompting import PROMPT_VERSION, SYSTEM_PROMPT, TOOLS, build_user_message, visible_account
from agent.retrieval import HybridRetriever
from agent.rules import Finding, limit_increase_findings
from agent.schema import AgentAnswer, Claim
from agent.tracing import Trace
from agent.upstream import fetch_account
from agent.validator import Context, validate

MAX_LLM_CALLS = 5
MAX_REJECTIONS = 2  # the first rejected answer goes back to the LLM; the second ends in the safe fallback
ALWAYS_IN_CONTEXT = ["POL-SVC-006"]  # routing queues are needed whenever a request might be raised
LIMIT_REQUEST = re.compile(
    r"\blimit\b.*\b(increase|raise|higher|more|bigger|up)\b|\b(increase|raise|higher|bigger)\b.*\blimit\b", re.I
)

# Customer-facing SLAs as worded in POL-SVC-006 (the tool's sla_hours is a conversion; see tools.py).
SLA_TEXT = {
    "CARDS_URGENT": "4 hours", "DISPUTES": "2 working days", "SELFSERVE": "1 working day",
    "CREDIT_OPS": "3 working days", "PAYMENTS": "2 working days", "COMPLAINTS": "5 working days",
    "GENERAL": "1 working day",
}
ACCOUNT_UNAVAILABLE = ("I couldn't reach your account details just now, so I can only answer from our "
                       "general policies, not from your account.")
SAFE_FALLBACK = ("I'm not able to answer this reliably right now, so I've passed your question to a "
                 "colleague rather than guess.")
CUSTOMER_NOT_FOUND = ("I couldn't find a card account for you, so I can't answer questions about it. "
                      "Please contact us so we can verify your details.")


@dataclass
class AgentResult:
    status: str
    customer_message: str
    claims: list[Claim]
    reason_codes: list[str]
    service_requests: list[dict]
    cited_docs: list[str]
    path: str  # how the answer was produced: llm | rules | safe_fallback | customer_not_found
    trace: dict


@dataclass
class _Turn:
    customer_id: str
    question: str
    trace: Trace
    account: dict | None = None
    account_status: str = "unknown"
    findings: list[Finding] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    raised: list[dict] = field(default_factory=list)


class Agent:
    def __init__(self, retriever: HybridRetriever | None = None, llm=call_llm, top_k: int = 5):
        self.retriever = retriever or HybridRetriever()
        self.chunks_by_id = {c.chunk_id: c for c in self.retriever.chunks}
        self.llm = llm
        self.top_k = top_k

    def answer(self, customer_id: str, question: str) -> AgentResult:
        trace = Trace(customer_id, question, prompt_version=PROMPT_VERSION, as_of=str(as_of()), models=models())
        turn = _Turn(customer_id, question, trace)
        try:
            return self._answer(turn)
        except Exception as e:  # last line of defence: the customer never sees a stack trace
            trace.error(f"unhandled: {type(e).__name__}: {e}")
            return self._safe_fallback(turn, "unhandled_error")

    def _answer(self, t: _Turn) -> AgentResult:
        with t.trace.span("get_account_state") as span:
            lookup = fetch_account(t.customer_id)
            span.update(status=lookup.status, attempts=lookup.attempts)
        if lookup.status == "not_found":
            return self._result(t, "refuse", [], [], path="customer_not_found", notice=CUSTOMER_NOT_FOUND)
        t.account, t.account_status = lookup.account, lookup.status

        with t.trace.span("retrieve", top_k=self.top_k) as span:
            hits = self.retriever.search(t.question, self.top_k)
            span["hits"] = [{"id": h.chunk.chunk_id, "rrf": round(h.rrf_score, 4), "bm25_rank": h.bm25_rank,
                             "dense_rank": h.dense_rank} for h in hits]

        t.findings = limit_increase_findings(t.account, as_of()) if t.account else []
        # Rule citations are added even when retrieval missed them: the account, not the
        # question wording, is what makes them relevant.
        pinned = ALWAYS_IN_CONTEXT + [c for f in t.findings for c in f.citations if c in self.chunks_by_id]
        if t.findings:
            pinned.append("POL-GOV-009")
        context_ids = list(dict.fromkeys([h.chunk.chunk_id for h in hits] + pinned))
        t.chunks = [self.chunks_by_id[i] for i in context_ids]
        t.trace.record.update(context_chunks=context_ids, findings=[f.rule for f in t.findings])

        ctx = Context(
            question=t.question,
            chunks={c.chunk_id: c for c in t.chunks},
            account=visible_account(t.account) if t.account else None,
            findings=t.findings,
            limit_request_by_keyword=bool(LIMIT_REQUEST.search(t.question)),
            hidden_values=[str(t.account["behavioural_score"])] if t.account else [],
            requests_raised=t.raised,
        )
        # A mandatory decline has no discretion, so code states it too: no model call, no
        # wording to police, and an injection has nothing to work on.
        if ctx.limit_request_by_keyword and _declines(t.findings):
            return self._rule_decline(t)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(t.question, t.account, t.findings, t.chunks)},
        ]
        try:
            return self._agent_loop(t, ctx, messages)
        except LLMUnavailable:
            return self._safe_fallback(t, "llm_unavailable")

    def _agent_loop(self, t: _Turn, ctx: Context, messages: list[dict]) -> AgentResult:
        rejections = 0
        for step in range(MAX_LLM_CALLS):
            with t.trace.span("llm", step=step) as span:
                turn = self.llm(messages, TOOLS)
                span.update(model=turn.model, fallback_used=turn.fallback_used, input_tokens=turn.input_tokens,
                            output_tokens=turn.output_tokens, tool_calls=[c.name for c in turn.tool_calls])
                if turn.skipped:
                    span["skipped_models"] = turn.skipped
            t.trace.add_usage(turn.input_tokens, turn.output_tokens, turn.cost_usd)
            messages.append(turn.assistant_message)

            accepted = None
            # Run requests before the answer, so an answer saying "raise_request" can see the request exists.
            for call in sorted(turn.tool_calls, key=lambda c: c.name == "submit_answer"):
                if call.name == "raise_service_request":
                    result = self._raise_from_llm(t, call.arguments)
                elif call.name == "submit_answer":
                    answer, errors = self._check(call.arguments, ctx)
                    # The keyword check missed it but the model spotted a limit request.
                    if answer and _declines(t.findings) and (
                            answer.intent == "limit_increase" or answer.status == "decline_with_reason"):
                        return self._rule_decline(t)
                    if errors:
                        rejections += 1
                        t.trace.error(f"answer rejected ({rejections}/{MAX_REJECTIONS}): {errors}")
                        result = {"rejected": True, "errors": errors, "instruction": "Fix these and call submit_answer again."}
                    else:
                        accepted = answer
                        result = {"accepted": True}
                else:
                    result = {"error": f"Unknown tool {call.name!r}."}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})

            if accepted:
                return self._finish(t, accepted)
            if rejections >= MAX_REJECTIONS:
                return self._safe_fallback(t, "validation_failed")
            if not turn.tool_calls:
                messages.append({"role": "user", "content": "Finish by calling submit_answer."})
        return self._safe_fallback(t, "step_limit")

    def _check(self, arguments: dict | None, ctx: Context) -> tuple[AgentAnswer | None, list[str]]:
        if arguments is None:
            return None, ["submit_answer arguments were not valid JSON."]
        try:
            answer = AgentAnswer.model_validate(arguments)
        except ValidationError as e:
            return None, [f"Schema error at {'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        return answer, validate(answer, ctx)

    def _raise_from_llm(self, t: _Turn, arguments: dict | None) -> dict:
        if not arguments or "category" not in arguments:
            return {"error": "raise_service_request needs category and summary."}
        # Idempotent within a turn: a retried answer must not open a second ticket.
        existing = next((r for r in t.raised if r["queue"] == arguments["category"]), None)
        return existing or self._raise(t, arguments["category"], arguments.get("summary", ""))

    def _raise(self, t: _Turn, category: str, summary: str) -> dict:
        # customer_id comes from the session, never from the LLM's arguments.
        with t.trace.span("raise_service_request", category=category) as span:
            try:
                request = tools.raise_service_request(t.customer_id, category, summary)
            except tools.InvalidCategory:
                span["rejected"] = "InvalidCategory"
                return {"error": f"Invalid category {category!r}. Use one of {list(tools.QUEUES)}."}
            span["request_id"] = request["request_id"]
        t.raised.append(request)
        return request

    def _finish(self, t: _Turn, answer: AgentAnswer) -> AgentResult:
        # A gap in the corpus is always routed to a human, even if the LLM forgot to.
        if answer.uncovered and not t.raised:
            self._raise(t, "GENERAL", f"Question not covered by policy: {answer.uncovered}")
        return self._result(t, answer.status, answer.claims, answer.reason_codes, path="llm", uncovered=answer.uncovered)

    def _safe_fallback(self, t: _Turn, reason: str) -> AgentResult:
        t.trace.record["fallback_reason"] = reason
        if not t.raised:
            self._raise(t, "GENERAL", f"Assistant could not answer reliably ({reason}): {t.question[:200]}")
        return self._result(t, "raise_request", [], [], path="safe_fallback", notice=SAFE_FALLBACK)

    def _rule_decline(self, t: _Turn) -> AgentResult:
        declines = _declines(t.findings)
        claims = [Claim(text=f.fact, citations=list(f.citations)) for f in declines]
        codes = [f.reason_code for f in declines if f.reason_code]
        return self._result(t, "decline_with_reason", claims, codes, path="rules")

    def _result(self, t: _Turn, status: str, claims: list[Claim], reason_codes: list[str], path: str,
                uncovered: str | None = None, notice: str | None = None) -> AgentResult:
        message = render(claims, t.account_status, t.raised, uncovered, notice)
        cited_docs = sorted({c.split("#")[0] for cl in claims for c in cl.citations if not c.startswith("account.")})
        record = t.trace.finish(status=status, path=path, reason_codes=reason_codes, cited_docs=cited_docs,
                                service_requests=t.raised, customer_message=message)
        return AgentResult(status, message, claims, reason_codes, t.raised, cited_docs, path, record)


def _declines(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.outcome == "decline"]


def render(claims: list[Claim], account_status: str, requests: list[dict], uncovered: str | None,
           notice: str | None) -> str:
    """The customer message is assembled here from validated claims. The LLM writes no free text."""
    parts = []
    if account_status == "unavailable":
        parts.append(ACCOUNT_UNAVAILABLE)
    if notice:
        parts.append(notice)

    sources: list[str] = []
    sentences = []
    for claim in claims:
        refs = []
        for citation in claim.citations:
            if citation not in sources:
                sources.append(citation)
            refs.append(str(sources.index(citation) + 1))
        sentences.append(f"{claim.text} [{', '.join(refs)}]")
    if sentences:
        parts.append(" ".join(sentences))

    if uncovered:
        # Worded to fit both causes: a gap in the corpus, or account data we couldn't reach.
        parts.append(f"I can't answer this from the information I have: {uncovered.rstrip('.')}. "
                     "I won't guess, so a colleague will pick it up.")
    for r in requests:
        parts.append(f"I've raised request {r['request_id']} with our {r['queue']} team. "
                     f"They aim to respond within {SLA_TEXT[r['queue']]}.")
    if sources:
        labels = [f"[{i}] your account record ({s.removeprefix('account.')})" if s.startswith("account.") else f"[{i}] {s}"
                  for i, s in enumerate(sources, 1)]
        parts.append("Sources: " + "; ".join(labels))
    return "\n\n".join(parts)
