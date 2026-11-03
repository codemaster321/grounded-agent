"""The structured answer the LLM must submit.

The customer never sees free text from the LLM: the message is rendered by code from
`claims`, so every factual sentence they read has passed the citation check.
"""
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["answer", "decline_with_reason", "raise_request", "refuse"]
Intent = Literal[
    "limit_increase", "fees", "dispute_or_fraud", "card_block", "product_terms",
    "complaint", "statement", "score_or_data_disclosure", "other",
]
ReasonCode = Literal["AA01", "AA02", "AA03", "AA04", "AA05", "AA06"]


class Claim(BaseModel):
    text: str = Field(description="One plain-language factual sentence shown to the customer.")
    citations: list[str] = Field(
        description="Ids that support this sentence: a policy id exactly as given (e.g. POL-FEE-007, POL-CRD-001#3) "
                    "or an account field as account.<field> (e.g. account.card_year_spend)."
    )


class AgentAnswer(BaseModel):
    intent: Intent
    status: Status
    claims: list[Claim]
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    uncovered: str | None = Field(
        default=None,
        description="If the policies do not cover the question or part of it, name that part in a few words. Otherwise null.",
    )
    off_topic: bool = Field(
        default=False,
        description="True only if the question has nothing to do with banking, cards or this customer's account "
                    "(weather, jokes, general chat). A card or banking question the policies don't cover is NOT off-topic.",
    )
