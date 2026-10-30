# Grounded service agent

**What I built.** A CLI agent that answers card questions from the 12-document policy corpus and the customer's account state. It uses hybrid retrieval (BM25 + embeddings with RRF), both supplied tools and a schema-validated answer in which every claim carries a citation checked in code. The principle is that the LLM explains and code decides: mandatory declines are decided and worded in code, the LLM never sees the internal score, and customer text is rendered from validated claims only. There is no approve path. Every failure ends in a defined message and one trace line. Details: [ARCHITECTURE](docs/ARCHITECTURE.md), [FAILURE_MODES](docs/FAILURE_MODES.md), [sample traces](docs/sample_traces.jsonl).

**Results.** 30 cases (12 seed, 18 mine). Three runs of the primary model: **29, 28, 28 of 30** (85/90). The fallback model: **24/30**. About $0.0014 per question, p50 2.9s, p95 9.7s. The remaining primary failures are EV-005 (all three runs) and EV-014 (two): both give the safe behaviour but a different status from the expected one, and I left those expectations unchanged. Per-case detail is in [eval/stability.md](eval/stability.md) and [eval/results.md](eval/results.md). The first runs scored 25–27/30; the increase came from fixes in [FAILURE_MODES](docs/FAILURE_MODES.md), and the prompt and some checks were tuned while looking at these same cases. One set of runs was discarded because the network failed mid-run (12/30); the eval now reports outages separately, but the gate does not yet exclude them.

**Deliberately not built.**
- **Streaming:** text must pass validation before the customer sees it, so streaming tokens would defeat the check.
- **Vector DB, API server, UI:** 12 documents fit in memory, and none of these is being assessed.
- **Response caching:** answers depend on live account state, so hits are rare and stale answers are dangerous.
- **LangChain/LangGraph:** the flow is one path with one retry. LangGraph is where I'd go for multi-turn memory or human pauses.
- **Multi-turn memory:** the brief is single-question.
- **OpenTelemetry/Langfuse:** a local JSONL file is enough here and keeps data on the machine.

**Next, with another day.**
1. A second-provider fallback, and raise the fallback model's score.
2. Close the wrong-fact gaps below with an entailment check.
3. Run the CI gate for real on a repeat-run basis, not a single run.
4. Tie rules to policy versions, so a changed document fails a test.

**What I would not trust, and how you'd find out.**
- **Citations prove presence, not support.** The check confirms the chunk was in context and the number appears in it, not that the claim follows. Figures from a card the customer doesn't hold are now rejected (I confirmed that gap with a scripted answer, then closed it), but only for numbers: "your card includes lounge access" citing the Signature section still passes for a Classic customer.
- **The score is flattering.** I wrote the cases and fixed against them, and 90 runs of 30 cases is small. Write 20 new cases without looking at the prompt.
- **False pass:** EV-029 passes while never telling the customer their actual fee of 500, because the validator forbids arithmetic.
- **Unsupported certainty:** EV-005 sometimes says the customer "is treated as" thin-file. We have no bureau data, so that can't be known, and the validator doesn't catch it.
- **Rules can go stale silently.** Change "6 months" in POL-CRD-001 and no test fails. Limit-request detection is also a keyword regex with LLM intent as backup, so a mixed question gets only the decline.
- **Guardrails over-block.** In earlier runs, EV-025 and one limit request reached the safe fallback through word and number false positives. Not seen in the final three runs, but not fixed. Safe, but unhelpful.
- **The fallback is weaker and shares a provider** with the primary, so an OpenAI outage takes out both.
- **Open policy gaps.** No POL-GOV-009 reason code fits a vulnerable-customer decline, so that decline carries none, and the source ID POL-CON-004 is shown to the customer. `sla_hours` assumes 24h per working day. The `AS_OF` default is my choice, picked so the contradiction bites.
- **Never exercised:** the GitHub Actions workflow has not run. Concurrency is untested. The injection demo covers three phrasings only. Traces store question text and `customer_id` unredacted, which a bank could not accept.

## Run it

```
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env                       # add OPENAI_API_KEY and both model names
python -m agent.cli CUST-2000 "Was my annual fee waived?" --trace
pytest -q                                    # fake LLM, no key
python -m eval.run_eval                      # real model, about $0.05, gate 80% (CI uses 85%)
python -m eval.break_demo                    # injection with the exclusion removed
```
