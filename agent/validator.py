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
PRODUCTS = ("Classic", "Signature")


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


def _other_product_figures(chunk: Chunk, product: str) -> set[float]:
    """Figures in this chunk that belong only to a card the customer does not hold."""
    others = [p for p in PRODUCTS if p != product]
    if any(p in chunk.section for p in others):
        return numbers(chunk.text)
    # A shared table, e.g. POL-FEE-007 lists both cards' waiver thresholds in one chunk.
    lines = chunk.text.splitlines()
    foreign = [line for line in lines if any(p in line for p in others)]
    shared = [line for line in lines if line not in foreign]
    return numbers("\n".join(foreign)) - numbers("\n".join(shared))


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
        product = ctx.account.get("card_product") if ctx.account else None
        if product:
            foreign = set().union(*(_other_product_figures(ctx.chunks[c], product) for c in claim.citations if c in ctx.chunks))
            # Naming the other card ("Signature waives it at 4,00,000") is a comparison, not a misquote.
            names_other_card = any(p.lower() in claim.text.lower() for p in PRODUCTS if p != product)
            if foreign & numbers(claim.text) and not names_other_card:
                errors.append(f"{label} gives a figure for a different card. This customer holds {product}: "
                              "use that card's figure.")

    # `uncovered` is shown to the customer too. It has no citations, so it can't carry new figures.
    if answer.uncovered and numbers(answer.uncovered) - question_numbers:
        errors.append("`uncovered` must only name the topic in a few words, with no figures.")

    message = " ".join([c.text for c in answer.claims] + [answer.uncovered or ""])
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

    # Off-topic means no ticket, so it must not hide a real request: no claims, no request raised.
    if answer.off_topic and (answer.claims or ctx.requests_raised or answer.status != "refuse"):
        errors.append("off_topic is only for questions unrelated to banking or this card: use status refuse, "
                      "no claims and no service request. Otherwise set off_topic to false.")

    if answer.status == "raise_request" and not ctx.requests_raised:
        errors.append("status is raise_request but raise_service_request was not called.")

    return errors
