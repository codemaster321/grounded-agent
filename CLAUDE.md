# Grounded service agent

A banking card-service agent. Principle: **the LLM explains, code decides.** Read
`docs/ARCHITECTURE.md` before changing the flow.

## Where changes go

| Change | File |
|---|---|
| New mandatory decline or referral | `agent/rules.py` + `tests/test_rules.py` |
| New policy document | `data/policy_corpus/` (needs the standard header line; indexed automatically) |
| Exclude a document, or say one overrides another | `agent/corpus_manifest.json` |
| New tool | `agent/tools.py`, `TOOLS` in `agent/prompting.py`, dispatch in `pipeline._agent_loop` |
| LLM behaviour | `prompts/system_v1.md` (version hash updates itself) |
| New safety check on answers | `agent/validator.py` + `tests/test_pipeline.py` |
| Models | `.env` (`PRIMARY_MODEL`, `FALLBACK_MODEL`) |
| Web API: login, chat, history, rate limits | `api/main.py` + `tests/test_api.py` |
| Web pages and styling | `web/` (Next.js; screen only, no decisions or checks here) |

## Rules that must keep holding

- `customer_id` comes from the session, never from LLM arguments. In the web API, the session cookie is the only source.
- The LLM never receives `HIDDEN_FIELDS` (`agent/prompting.py`).
- There is no approve path. Outcomes are answer, decline (only from `rules.py`), refer, refuse.
- Customer text is rendered by `pipeline.render` from validated claims. No free LLM text.
- Every exit path gives a customer message and writes one trace line.
- Do not edit `data/`: the tool contracts and corpus are supplied.

## Verify

```
.venv/Scripts/python -m pytest -q        # fake LLM, ~20s, no key
.venv/Scripts/python -m eval.run_eval    # real model, ~3 min, costs about $0.07
```

The model is non-deterministic: compare several eval runs, not one. Check a trace in
`traces/traces.jsonl` when behaviour looks wrong. `eval.run_eval` overwrites `eval/results.*`;
ask before running it. Restart the backend after Python changes, and rebuild the website after
`web/` changes.
