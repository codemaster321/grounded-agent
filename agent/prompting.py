"""Builds what the LLM sees: the versioned system prompt and the per-request context.

PROMPT_VERSION = file name + content hash, logged on every trace, so any answer can be
traced back to the exact prompt text that produced it. Editing the file changes the hash
even if someone forgets to bump the file name.
"""
import hashlib
import json

from agent.corpus import MANIFEST, ROOT, Chunk
from agent.rules import Finding
from agent.schema import AgentAnswer
from agent.tools import QUEUES

PROMPT_FILE = ROOT / "prompts" / "system_v1.md"
SYSTEM_PROMPT = PROMPT_FILE.read_text(encoding="utf-8")
PROMPT_VERSION = f"{PROMPT_FILE.stem}@{hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8]}"

# Data minimisation: the LLM never sees these, so it cannot leak them (POL-GOV-009),
# whatever the prompt or an injection says.
HIDDEN_FIELDS = {"behavioural_score", "name"}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "raise_service_request",
            "description": "Create a service request for the current customer. The customer is set by the system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": list(QUEUES)},
                    "summary": {"type": "string", "description": "One line for the human agent. No internal scores."},
                },
                "required": ["category", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": "Submit the final answer. Call exactly once, last.",
            "parameters": AgentAnswer.model_json_schema(),
        },
    },
]


def _escape(text: str) -> str:
    # Stops a document or question from closing our tags early (e.g. a planted "</policy>").
    return text.replace("<", "&lt;")


def visible_account(account: dict) -> dict:
    return {k: v for k, v in account.items() if k not in HIDDEN_FIELDS}


def build_user_message(question: str, account: dict | None, findings: list[Finding], chunks: list[Chunk]) -> str:
    parts = []
    if account is None:
        parts.append('<account_state status="unavailable">The account system did not respond. '
                     "Nothing is known about this customer's account.</account_state>")
    else:
        parts.append(f'<account_state status="ok">\n{json.dumps(visible_account(account), indent=1)}\n</account_state>')

    if findings:
        lines = [f'- outcome={f.outcome} rule={f.rule} reason_code={f.reason_code} '
                 f'citations={list(f.citations)} fact="{f.fact}"' for f in findings]
        parts.append("<policy_findings>\n" + "\n".join(lines) + "\n</policy_findings>")

    docs_in_context = {c.doc_id for c in chunks}
    rules = [f"- {p['prevails']} prevails over {p['over']} on {p['topic']}."
             for p in MANIFEST["precedence"] if p["over"] in docs_in_context]
    if rules:
        parts.append("<precedence>\n" + "\n".join(rules) + "\n</precedence>")

    for c in chunks:
        parts.append(f'<policy id="{c.chunk_id}" version="{c.version}" effective="{c.effective}">\n'
                     f"{c.title}{' / ' + c.section if c.section else ''}\n{_escape(c.text)}\n</policy>")

    parts.append(f"<customer_question>{_escape(question)}</customer_question>")
    return "\n\n".join(parts)
