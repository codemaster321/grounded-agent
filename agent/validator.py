"""Checks an AgentAnswer before the customer sees it. Returns a list of errors; empty = pass.

The errors are written for the LLM: on the first failure they go back to it as the tool
result, so it can correct itself once. A second failure goes to the safe fallback.
"""
import re
from dataclasses import dataclass

from agent.corpus import MANIFEST, Chunk
from agent.rules import Finding
from agent.schema import AgentAnswer

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# "approved reason codes" is POL-GOV-009's own wording, not an approval (false positive found by EV-011).
_APPROVAL = re.compile(r"\b(approved(?!\s+reason)|actioned|has been (increased|raised)|have (increased|raised))\b", re.I)
_SALES = re.compile(r"\b(offer|upgrade|apply for|personal loan|eligible for)\b", re.I)


@dataclass
class Context:
    question: str
    chunks: dict[str, Chunk]  # chunk_id -> chunk: the only policy ids that may be cited
    account: dict | None  # fields the LLM was shown; None when the account tool failed
    findings: list[Finding]
    limit_request_by_keyword: bool
    hidden_values: list[str]  # values the LLM was never shown and that must never appear
    requests_raised: list[dict]


def numbers(text: str) -> set[float]:
    # "1,50,000" (Indian grouping) and "150,000" both become 150000.0
    return {float(n.replace(",", "")) for n in _NUMBER.findall(text)}


def _source_text(citation: str, ctx: Context) -> str | None:
    # A non-policy document can't support a claim even if it reaches the context.
    if citation in ctx.chunks and citation.split("#")[0] not in MANIFEST["excluded"]:
        return ctx.chunks[citation].for_search()
    if citation.startswith("account.") and ctx.account is not None:
        field = citation.removeprefix("account.")
        if field in ctx.account:
            value = ctx.account[field]
            # utilisation 0.38 may be said as "38%"
            return f"{value} {value * 100:g}" if isinstance(value, float) else str(value)
    return None


def validate(answer: AgentAnswer, ctx: Context) -> list[str]:
    errors = []
    question_numbers = numbers(ctx.question)

    if not answer.claims and not answer.uncovered:
        errors.append("The answer has no claims and no `uncovered` topic, so there is nothing to tell the customer.")

    for i, claim in enumerate(answer.claims):
        label = f"Claim {i + 1} ({claim.text[:60]!r})"
        if not claim.citations:
            errors.append(f"{label} has no citation. Every factual sentence needs at least one.")
            continue
        sources = []
        for citation in claim.citations:
            text = _source_text(citation, ctx)
            if text is None:
                errors.append(f"{label} cites {citation!r}, which is not one of the policies or account fields provided.")
            else:
                sources.append(text)
        supported = question_numbers.union(*(numbers(s) for s in sources))
        unsupported = numbers(claim.text) - supported
        if sources and unsupported:
            errors.append(f"{label} states {sorted(unsupported)}, which do not appear in its cited sources. "
                          "Only restate figures from the cited policy or account field; do not calculate new ones.")

    message = " ".join(c.text for c in answer.claims)
    if _APPROVAL.search(message):
        errors.append("The answer says something was approved or actioned. This assistant cannot approve or action anything.")
    for value in ctx.hidden_values:
        if re.search(rf"\b{re.escape(value)}\b", message):
            errors.append("The answer contains an internal value that must never be disclosed.")
    if ctx.account and ctx.account.get("vulnerable_flag"):
        if _SALES.search(message):
            errors.append("This customer is flagged vulnerable (POL-CON-004): remove all sales and product suggestions.")
        # The flag is set internally by the Conduct team; disclosing it belongs in a human conversation.
        if re.search(r"\bvulnerab", message, re.I):
            errors.append("Do not tell the customer they are flagged vulnerable.")

    # Mandatory declines are stated by code before this runs (pipeline._rule_decline), so a
    # decline reaching here has no rule behind it.
    if answer.status == "decline_with_reason":
        errors.append("No mandatory decline applies. This assistant cannot decline at its own discretion: "
                      "explain the policy and raise a CREDIT_OPS request for a human decision instead.")

    if answer.status == "raise_request" and not ctx.requests_raised:
        errors.append("status is raise_request but raise_service_request was not called.")

    return errors
