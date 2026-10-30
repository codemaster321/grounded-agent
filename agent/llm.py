"""One LLM call, with an explicit primary -> fallback chain.

The chain is written out rather than using LiteLLM's built-in `fallbacks=` so the trace
can record exactly which model answered and why the primary was skipped.
"""
import json
from dataclasses import dataclass, field

import litellm
import openai  # LiteLLM's exceptions subclass openai.APIError, for every provider

from agent.config import models

CALL_TIMEOUT_S = 30
REASONING_EFFORT = "low"


class LLMUnavailable(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict | None  # None if the model sent invalid JSON
    raw_arguments: str


@dataclass
class LLMTurn:
    assistant_message: dict
    tool_calls: list[ToolCall]
    model: str
    fallback_used: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    skipped: list[str] = field(default_factory=list)  # why earlier models in the chain failed


def call_llm(messages: list[dict], tools: list[dict]) -> LLMTurn:
    skipped = []
    for i, model in enumerate(models()):
        try:
            resp = litellm.completion(
                model=model, messages=messages, tools=tools, tool_choice="required", timeout=CALL_TIMEOUT_S,
                # Low reasoning effort cut a 21s call to a few seconds; the hard decisions are
                # made in code, so the model only needs to read and phrase. drop_params removes
                # it for models that don't support it (the fallback).
                reasoning_effort=REASONING_EFFORT, drop_params=True,
            )
        except openai.APIError as e:
            # Provider-side failures only (outage, rate limit, timeout, auth). A bug in our own
            # code would fail identically on every model, so it is not caught here: falling
            # back on it would hide the bug behind an "outage".
            skipped.append(f"{model}: {type(e).__name__}: {str(e)[:200]}")
            continue
        return _to_turn(resp, model, fallback_used=i > 0, skipped=skipped)
    raise LLMUnavailable("; ".join(skipped))


def _to_turn(resp, model: str, fallback_used: bool, skipped: list[str]) -> LLMTurn:
    msg = resp.choices[0].message
    calls = []
    for tc in msg.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments)
        except (json.JSONDecodeError, TypeError):
            args = None
        calls.append(ToolCall(tc.id, tc.function.name, args, tc.function.arguments))
    try:
        cost = litellm.completion_cost(completion_response=resp)
    except Exception:  # model missing from LiteLLM's price table
        cost = None
    return LLMTurn(
        assistant_message={
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.raw_arguments}}
                           for c in calls] or None,
        },
        tool_calls=calls,
        model=model,
        fallback_used=fallback_used,
        input_tokens=resp.usage.prompt_tokens,
        output_tokens=resp.usage.completion_tokens,
        cost_usd=cost,
        skipped=skipped,
    )
